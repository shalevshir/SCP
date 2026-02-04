"""Execution Service main entry point."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI

from scp_shared.admin import KillSwitchRepository
from scp_shared.alerts import AlertLevel, AlertType, send_alert
from scp_shared.common import get_logger, mask_connection_url
from scp_shared.common.types import Candle
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer, CandleFeatureSynchronizer, SyncAckPublisher
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage, SignalMessage
from scp_shared.metrics import create_metrics_router, infrastructure

from execution_svc.broker import BaseBroker, create_broker
from execution_svc.config import ExecutionConfig
from execution_svc import metrics as exec_metrics
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.sync_coordinator import ExecutionSyncCoordinator
from execution_svc.trade_manager import TradeManager, is_valid_candle
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository

logger = get_logger(__name__)

# Load configuration
config = ExecutionConfig()

# Global shutdown event
shutdown_event = asyncio.Event()

# Global references for reset endpoint (populated in process_streams)
_trade_manager: Optional[TradeManager] = None
_broker: Optional[BaseBroker] = (
    None  # BaseBroker instance (PaperBroker or IBPaperBroker)
)
_sm_manager: Optional[StateMachineManager] = None
_synchronizer: Optional[CandleFeatureSynchronizer] = None

# Global kill switch state (populated in lifespan)
_kill_switch_repo: Optional[KillSwitchRepository] = None
_is_killed: bool = False


async def process_streams(
    redis_client: redis.Redis,
    db_pool: DatabasePool,
) -> None:
    """Main processing loop: consume signals and candles, manage trades.

    Args:
        redis_client: Redis client
        db_pool: Database pool
    """
    global _trade_manager, _broker, _sm_manager, _is_killed, _kill_switch_repo

    logger.info("Starting execution processing loop")

    # Initialize components
    # Note: Broker will be passed in from lifespan (already created and connected)
    # This function will be refactored to receive broker as parameter
    broker = _broker
    if broker is None:
        raise RuntimeError("Broker not initialized. This should not happen.")
    sm_manager = StateMachineManager(db_pool)
    trade_repo = TradeRepository(db_pool, point_value=config.point_value)
    trade_publisher = TradePublisher(redis_client)
    # HARDCODED: Force max_active_trades=1 for debugging (matching backtest)
    _max_active = 1  # config.max_active_trades
    logger.info(f"TradeManager config: max_active_trades={_max_active}")

    trade_manager = TradeManager(
        broker=broker,
        state_machine_manager=sm_manager,
        trade_repository=trade_repo,
        trade_publisher=trade_publisher,
        db_pool=db_pool,
        max_active_trades=_max_active,
        pdll_limit=config.pdll_limit,
        max_trades_per_day=config.max_trades_per_day,
        max_consecutive_losses=config.max_consecutive_losses,
        service_mode=config.service_mode,
        service_name=config.service_name,
    )

    # Store global references for reset endpoint
    _trade_manager = trade_manager
    _broker = broker
    _sm_manager = sm_manager

    # Restore state from database
    await sm_manager.restore_from_db()
    await trade_manager.restore_active_trades()

    # Set trading halt reason metric based on actual restored state
    # Check if trading is blocked due to restored state (PDLL, loss streak, etc.)
    can_trade, halt_reason = trade_manager._daily_tracker.can_trade()
    if can_trade:
        exec_metrics.set_trading_halt_reason(
            "NONE", config.service_mode, config.service_name
        )
        logger.info("Trading allowed after state restore - halt reason: NONE")
    else:
        # Trading is blocked - set the actual halt reason
        exec_metrics.set_trading_halt_reason(
            halt_reason or "UNSAFE_STATE", config.service_mode, config.service_name
        )
        logger.warning(
            f"Trading blocked after state restore - halt reason: {halt_reason or 'UNSAFE_STATE'}"
        )

    # Update metrics based on restored state
    exec_metrics.loss_streak_current.labels(
        mode=config.service_mode, service=config.service_name
    ).set(trade_manager._daily_tracker.state.consecutive_losses)

    exec_metrics.daily_pnl.labels(
        mode=config.service_mode, service=config.service_name
    ).set(trade_manager._daily_tracker.state.daily_pnl)

    # Calculate daily drawdown (max loss from peak)
    daily_drawdown = min(0, trade_manager._daily_tracker.state.daily_pnl)
    exec_metrics.daily_drawdown.labels(
        mode=config.service_mode, service=config.service_name
    ).set(abs(daily_drawdown))

    logger.info(
        f"Restored daily state metrics: "
        f"loss_streak={trade_manager._daily_tracker.state.consecutive_losses}, "
        f"daily_pnl={trade_manager._daily_tracker.state.daily_pnl:.2f}, "
        f"daily_drawdown={abs(daily_drawdown):.2f}"
    )

    # Create consumers
    signals_consumer = RedisStreamConsumer(
        redis_client,
        stream="signals.pending",
        group="execution",
        consumer_name="instance-1",
        message_type=SignalMessage,
    )

    candles_consumer = RedisStreamConsumer(
        redis_client,
        stream="candles.1m.gc",
        group="execution",
        consumer_name="instance-1",
        message_type=CandleMessage,
    )

    features_consumer = RedisStreamConsumer(
        redis_client,
        stream="features.1m",
        group="execution",
        consumer_name="instance-1",
        message_type=FeaturesMessage,
    )

    logger.info("Execution Service ready - consuming signals and candles")

    # SBOP: Sync ack publisher for backtest orchestration
    # Only sends acks in "replay" mode for synchronous backtesting
    sbop_mode = "backtest" if config.service_mode == "replay" else config.service_mode
    sync_ack_publisher = SyncAckPublisher(
        redis_client,
        service_id="execution",
        mode=sbop_mode,
    )
    logger.info(
        f"SBOP: service_mode={config.service_mode}, sbop_mode={sbop_mode}, "
        f"enabled={sync_ack_publisher.enabled}"
    )

    # SBOP: Sync coordinator to wait for bot-core before processing
    # Ensures signals arrive before we process candles
    sync_coordinator = ExecutionSyncCoordinator(
        redis_client,
        mode=sbop_mode,
    )

    # Synchronizer to pair candles with their matching features by timestamp
    # CRITICAL: Use a VERY large timeout (7 days of data-time) to handle:
    # 1. High-speed replay where candles arrive in batches spanning hours
    # 2. Features arriving in separate batches after their candles
    # 3. The cleanup uses DATA timestamps, not wall-clock time, so during
    #    replay, hours of data arrive in seconds - need large buffer
    # 4. For 7-day backtest (Nov 5-11), need timeout >= 7 days to prevent
    #    early candles from being cleaned before their features arrive
    global _synchronizer  # noqa: PLW0603 - intentional global for reset endpoint
    synchronizer = CandleFeatureSynchronizer(timeout_seconds=604800)  # 7 days
    _synchronizer = synchronizer  # Store global reference for reset endpoint

    # Cleanup counter (run cleanup every N candles to prevent memory leaks)
    cleanup_counter = 0
    cleanup_interval = 50  # Cleanup every 50 candles (~50 minutes)

    # SBOP: Track timestamps we've acked to avoid double-acking (must persist across iterations)
    acked_timestamps: set[datetime] = set()

    loop_iteration = 0

    try:
        while not shutdown_event.is_set():
            loop_iteration += 1
            if loop_iteration == 1 or loop_iteration % 100 == 0:
                logger.info(f"Execution loop iteration {loop_iteration}")
            # Read from all streams IN PARALLEL to avoid sequential blocking
            # Previously, each read blocked for up to 1000ms, causing ~3 second
            # delays when streams were empty. Now they run concurrently.
            signals_list, candles_list, features_list = await asyncio.gather(
                signals_consumer.read(
                    count=10, block_ms=100
                ),  # Short timeout for signals
                candles_consumer.read(
                    count=100, block_ms=100
                ),  # Larger batch for replay
                features_consumer.read(
                    count=100, block_ms=100
                ),  # Larger batch for replay
            )

            # SBOP: Debug logging in backtest mode
            if sync_ack_publisher.enabled:
                if candles_list or features_list:
                    logger.info(
                        f"SBOP: Read {len(candles_list)} candles, {len(features_list)} features"
                    )
                elif loop_iteration % 50 == 0:
                    logger.info(f"SBOP: No messages read (iteration {loop_iteration})")

            # Process signals (buffer for next bar execution)
            # KILL SWITCH: Skip signal processing if killed
            if _is_killed:
                if signals_list:
                    logger.warning(
                        f"🚨 Kill switch active - rejecting {len(signals_list)} signal(s)"
                    )
            else:
                for signal_msg in signals_list:
                    await trade_manager.on_signal(signal_msg)

            # CRITICAL FIX: Interleave candle and feature processing to prevent
            # cleanup from dropping unpaired messages during high-speed replay.
            # Previously, all candles were added first, then all features.
            # This caused messages spanning >2 minutes (data-time) to be dropped
            # before their pair arrived.
            #
            # New approach: Merge and sort by timestamp to maximize pairing.
            all_messages: list[tuple[str, CandleMessage | FeaturesMessage]] = []
            for c in candles_list:
                all_messages.append(("candle", c))
            for f in features_list:
                all_messages.append(("features", f))

            all_messages.sort(key=lambda x: x[1].timestamp)

            for msg_type, msg in all_messages:
                if msg_type == "candle":
                    pair = synchronizer.add_candle(msg)  # type: ignore[arg-type]
                else:
                    pair = synchronizer.add_features(msg)  # type: ignore[arg-type]

                if pair:
                    # SBOP: Wait for bot-core to complete before processing
                    # This ensures signals have been generated and published
                    await sync_coordinator.wait_for_bot_core_ready(pair[0].timestamp)

                    await _process_candle_with_features(pair, trade_manager, sm_manager, sync_ack_publisher)

                    # SBOP: Ack AFTER processing is complete
                    # This ensures Execution only signals completion after trade logic has executed
                    if sync_ack_publisher.enabled and pair[0].timestamp not in acked_timestamps:
                        await sync_ack_publisher.ack(pair[0].timestamp)
                        acked_timestamps.add(pair[0].timestamp)
                    cleanup_counter += 1

            # Log synchronizer stats periodically for debugging
            stats = synchronizer.get_buffer_stats()
            if stats["total_unpaired"] > 10:
                logger.warning(
                    f"Synchronizer buffer growing: {stats} - "
                    "candles/features may be out of sync"
                )

            # Periodic cleanup to prevent memory leaks
            if cleanup_counter >= cleanup_interval:
                sm_manager.cleanup_old_state_machines()
                cleanup_counter = 0

    except asyncio.CancelledError:
        logger.info("Execution processing cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in execution processing loop: {e}", exc_info=True)
        send_alert(
            AlertLevel.CRITICAL,
            AlertType.SERVICE_CRASHED,
            f"Execution Service crashed: {e}",
            context={
                "service": "execution",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            },
        )
        raise


async def _process_candle_with_features(
    pair: tuple[CandleMessage, FeaturesMessage],
    trade_manager: TradeManager,
    sm_manager: StateMachineManager,
    sync_ack_publisher: SyncAckPublisher | None = None,
) -> None:
    """Process a synchronized candle-features pair.

    This ensures that when we process a candle, we have the matching
    features with the same timestamp for invalidation checks.

    Args:
        pair: Tuple of (candle, features) with matching timestamps
        trade_manager: Trade manager instance
        sm_manager: State machine manager instance
        sync_ack_publisher: Optional sync ack publisher for backtest orchestration (SBOP)
    """
    global _is_killed  # noqa: PLW0603 - intentional global for kill switch
    candle_msg, features_msg = pair

    logger.info(f"Processing candle: {candle_msg.timestamp} (with matching features)")

    # Convert to internal Candle type for validation
    candle_obj = Candle(
        timestamp=candle_msg.timestamp,
        open=candle_msg.open,
        high=candle_msg.high,
        low=candle_msg.low,
        close=candle_msg.close,
        volume=candle_msg.volume,
        symbol=candle_msg.symbol,
        timeframe=candle_msg.timeframe,
        source="STREAM",
    )

    # Skip invalid candles (NaN/Inf) BEFORE incrementing bar counter
    # This matches legacy backtester behavior where invalid candles don't count as bars
    if not is_valid_candle(candle_obj):
        logger.debug(
            f"Skipping invalid candle at {candle_msg.timestamp} (NaN/Inf detected) "
            f"- bar counter not incremented"
        )
        return

    # CRITICAL: Check session reset BEFORE execute_pending_signals
    # to ensure daily limits (PDLL, max trades) are fresh at day boundaries
    trade_manager.check_session_reset(candle_msg.timestamp)

    # Increment bar counter BEFORE execute_pending_signals so that
    # check_confirmation() can confirm signals from the previous bar
    # (confirmation requires bar_idx > detection_bar_idx)
    # Only increment for valid candles (invalid candles already returned above)
    sm_manager.increment_bar_counter()

    # KILL SWITCH: Skip executing pending signals if killed
    # This prevents signals that were already in _pending_signals when the
    # kill switch was activated from being executed
    if _is_killed:
        if trade_manager._pending_signals:  # type: ignore[attr-defined]
            logger.warning(
                f"🚨 Kill switch active - skipping execution of {len(trade_manager._pending_signals)} pending signal(s)"
            )
    else:
        # Execute pending signals at this candle's open
        # Pass candle timestamp so signals only execute at the correct time
        await trade_manager.execute_pending_signals(
            candle_msg.open, candle_msg.timestamp
        )

    # Monitor active trades for SL/TP and invalidation
    # Now we pass the CORRECT features that match this candle's timestamp
    # Note: Invalid candle validation already handled above, so this is safe
    await trade_manager.on_candle(candle_msg, features_msg)

    # NOTE: SBOP ack is now sent in the main processing loop to handle
    # cases where features arrive before candles (ack based on features receipt)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    global _kill_switch_repo, _is_killed, _broker

    logger.info(f"Starting Execution Service v{config.service_version}")

    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {mask_connection_url(config.redis_url)}")
    # Set redis connected metric
    infrastructure.redis_connected.labels(
        mode=config.service_mode, service=config.service_name
    ).set(1)

    db_pool = DatabasePool(config.database_url)
    await db_pool.connect()
    logger.info(f"Connected to database at {mask_connection_url(config.database_url)}")

    # Initialize broker
    broker = create_broker(config.broker_mode, config)
    _broker = broker  # Store global reference for process_streams

    # Connect to broker if it has a connect method (e.g., IBPaperBroker)
    if hasattr(broker, "connect"):
        try:
            await broker.connect()
            logger.info(f"✅ Broker connected (mode: {config.broker_mode})")
            # Set broker connected metric
            exec_metrics.broker_connected.labels(
                mode=config.service_mode, service=config.service_name
            ).set(1)
        except Exception as e:
            logger.error(f"❌ Failed to connect broker: {e}")
            # Set broker disconnected metric
            exec_metrics.broker_connected.labels(
                mode=config.service_mode, service=config.service_name
            ).set(0)
            raise
    else:
        logger.info(f"✅ Broker initialized (mode: {config.broker_mode})")
        # Paper broker is always "connected" (local)
        exec_metrics.broker_connected.labels(
            mode=config.service_mode, service=config.service_name
        ).set(1)

    # Initialize kill switch repository and load state
    _kill_switch_repo = KillSwitchRepository(db_pool)
    kill_state = await _kill_switch_repo.get_state("execution")
    _is_killed = kill_state.is_killed

    # METRIC: Set trading enabled and unsafe state based on kill switch
    mode = config.service_mode
    service = config.service_name
    if _is_killed:
        logger.warning(
            f"🚨 KILL SWITCH IS ACTIVE - Trading halted "
            f"(killed at {kill_state.killed_at} by {kill_state.killed_by}: {kill_state.reason})"
        )
        exec_metrics.trading_enabled.labels(mode=mode, service=service).set(0)
        exec_metrics.set_unsafe_state("manual_kill", mode, service)
    else:
        logger.info("✅ Kill switch inactive - Trading enabled")
        exec_metrics.trading_enabled.labels(mode=mode, service=service).set(1)
        exec_metrics.set_unsafe_state(None, mode, service)

    # Send service started alert
    send_alert(
        AlertLevel.INFO,
        AlertType.SERVICE_STARTED,
        f"Execution Service v{config.service_version} started",
        context={
            "service": config.service_name,
            "version": config.service_version,
            "broker_mode": config.broker_mode,
            "kill_switch_active": _is_killed,
            "pdll_limit": config.pdll_limit,
            "max_trades_per_day": config.max_trades_per_day,
            "timestamp": datetime.now().isoformat(),
        },
    )

    # Start processing task
    processing_task = asyncio.create_task(process_streams(redis_client, db_pool))

    yield

    # Shutdown
    logger.info("Shutting down Execution Service")
    shutdown_event.set()
    processing_task.cancel()

    try:
        await processing_task
    except asyncio.CancelledError:
        logger.info("Processing task cancelled successfully")
    except Exception as e:
        logger.error(f"Processing task failed: {e}", exc_info=True)
    finally:
        # Disconnect broker if it has a disconnect method
        if hasattr(_broker, "disconnect"):
            try:
                await _broker.disconnect()
                logger.info("Broker disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting broker: {e}")

        # Set broker disconnected metric
        exec_metrics.broker_connected.labels(
            mode=config.service_mode, service=config.service_name
        ).set(0)

        # Set redis disconnected metric
        infrastructure.redis_connected.labels(
            mode=config.service_mode, service=config.service_name
        ).set(0)

        await redis_client.aclose()
        await db_pool.close()
        logger.info("Execution Service stopped")


# Create FastAPI app
app = FastAPI(
    title="SCP Execution Service",
    version=config.service_version,
    lifespan=lifespan,
)

# Add health check endpoints
health_router = create_health_router(
    service_name=config.service_name,
    version=config.service_version,
)
app.include_router(health_router)

# Add metrics endpoint
metrics_router = create_metrics_router()
app.include_router(metrics_router)


@app.post("/admin/kill")
async def kill_switch(reason: str = "Manual kill via API") -> dict[str, str]:
    """Activate kill switch to halt all trading.

    When activated:
    - New signals are rejected
    - Pending signals are cleared (to prevent stale entry prices)
    - Active trades continue to be monitored for SL/TP exits
    - State persists across restarts

    Args:
        reason: Reason for activation

    Returns:
        Status message with kill state
    """
    global _kill_switch_repo, _is_killed, _trade_manager

    if _kill_switch_repo is None:
        return {"status": "error", "message": "Service not fully initialized"}

    await _kill_switch_repo.set_killed("execution", "admin", reason)
    _is_killed = True

    # CRITICAL: Clear pending signals to prevent stale entry prices
    # If kill switch is active for extended period, signals in _pending_signals
    # will have outdated entry_price values. Clearing them prevents execution
    # with incorrect prices when kill switch is deactivated.
    pending_count = 0
    if _trade_manager is not None:
        pending_count = len(_trade_manager._pending_signals)  # type: ignore[attr-defined]
        if pending_count > 0:
            logger.warning(
                f"🚨 Clearing {pending_count} pending signal(s) due to kill switch activation"
            )
            _trade_manager._pending_signals.clear()  # type: ignore[attr-defined]

    # METRIC: Update trading state
    exec_metrics.trading_enabled.labels(
        mode=config.service_mode, service=config.service_name
    ).set(0)
    exec_metrics.set_unsafe_state(
        "manual_kill", config.service_mode, config.service_name
    )

    logger.warning(f"🚨 KILL SWITCH ACTIVATED: {reason}")
    send_alert(
        AlertLevel.CRITICAL,
        AlertType.KILL_SWITCH_ACTIVATED,
        f"Execution Service kill switch activated: {reason}",
        context={
            "service": "execution",
            "killed_by": "admin",
            "reason": reason,
            "pending_signals_cleared": pending_count,
            "timestamp": datetime.now().isoformat(),
        },
    )

    return {
        "status": "killed",
        "message": f"Trading halted: {reason}",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/admin/resume")
async def resume_trading() -> dict[str, str]:
    """Deactivate kill switch to resume trading.

    When resumed:
    - Pending signals are cleared (safety measure - they should already be empty
      if kill switch was activated, but clear anyway to prevent any stale signals)
    - New signals will be accepted and executed normally

    Returns:
        Status message
    """
    global _kill_switch_repo, _is_killed, _trade_manager

    if _kill_switch_repo is None:
        return {"status": "error", "message": "Service not fully initialized"}

    await _kill_switch_repo.set_resumed("execution")
    _is_killed = False

    # CRITICAL: Clear any remaining pending signals as a safety measure
    # (They should already be empty if kill switch was activated, but clear anyway
    # to prevent any edge cases where stale signals might execute with outdated prices)
    if _trade_manager is not None:
        pending_count = len(_trade_manager._pending_signals)  # type: ignore[attr-defined]
        if pending_count > 0:
            logger.warning(
                f"🚨 Clearing {pending_count} stale pending signal(s) on kill switch resume"
            )
            _trade_manager._pending_signals.clear()  # type: ignore[attr-defined]

    # METRIC: Update trading state
    exec_metrics.trading_enabled.labels(
        mode=config.service_mode, service=config.service_name
    ).set(1)
    exec_metrics.set_unsafe_state(None, config.service_mode, config.service_name)

    logger.info("✅ Kill switch deactivated - Trading resumed")
    send_alert(
        AlertLevel.INFO,
        AlertType.KILL_SWITCH_RESUMED,
        "Execution Service kill switch deactivated - trading resumed",
        context={
            "service": "execution",
            "resumed_by": "admin",
            "timestamp": datetime.now().isoformat(),
        },
    )

    return {
        "status": "active",
        "message": "Trading resumed",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/admin/status")
async def get_status() -> dict:
    """Get current kill switch status.

    Returns:
        Current kill switch state
    """
    global _kill_switch_repo, _is_killed

    if _kill_switch_repo is None:
        return {"status": "error", "message": "Service not fully initialized"}

    kill_state = await _kill_switch_repo.get_state("execution")

    return {
        "service": "execution",
        "is_killed": kill_state.is_killed,
        "killed_at": kill_state.killed_at.isoformat() if kill_state.killed_at else None,
        "killed_by": kill_state.killed_by,
        "reason": kill_state.reason,
        "updated_at": kill_state.updated_at.isoformat(),
    }


@app.post("/admin/reset")
async def reset_state() -> dict[str, str]:
    """Reset service state for testing.

    Clears all in-memory state:
    - Active trades
    - Pending signals
    - State machines
    - Daily tracker
    - InvalidationChecker daily state (loss streaks, PnL)
    - Broker positions
    - Synchronizer buffers

    This endpoint is intended for integration testing only.

    Returns:
        Status message
    """
    global _trade_manager, _broker, _sm_manager, _synchronizer, _is_killed

    if _trade_manager is None or _broker is None or _sm_manager is None:
        return {"status": "error", "message": "Service not fully initialized"}

    # Reset kill switch in-memory flag for test isolation.
    # Note: This does NOT alter the persisted kill switch state in the database.
    _is_killed = False

    # METRIC: Update trading state to reflect reset
    exec_metrics.trading_enabled.labels(
        mode=config.service_mode, service=config.service_name
    ).set(1)
    exec_metrics.set_unsafe_state(None, config.service_mode, config.service_name)

    # Reset trade manager state
    _trade_manager._active_trades.clear()
    _trade_manager._pending_signals.clear()
    _trade_manager._trade_entry_bars.clear()
    _trade_manager._last_processed_candle_ts = None  # Reset for clean replay
    _trade_manager._closed_trade_ranges.clear()  # Reset for clean replay
    _trade_manager._daily_tracker.reset_state()
    # CRITICAL: Reset InvalidationChecker daily state to prevent stale loss streaks/PnL
    # from causing incorrect risk breach checks after reset
    _trade_manager._invalidation_checker.reset_daily_state()

    # Reset state machine manager
    _sm_manager._state_machines.clear()
    _sm_manager._bar_counter = 0

    # Reset broker
    _broker.reset_state()

    # Reset synchronizer buffers (critical for test isolation)
    if _synchronizer is not None:
        _synchronizer.clear()

    logger.info("Execution service state reset via /admin/reset endpoint")

    return {"status": "ok", "message": "State reset successfully"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
