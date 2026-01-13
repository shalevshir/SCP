"""Trade lifecycle manager with SL/TP monitoring."""

import math
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from scp_shared.common.logger import get_logger
from scp_shared.common.types import Candle
from scp_shared.database import DatabasePool
from scp_shared.database.repositories import CandleRepository
from scp_shared.execution import InvalidationChecker
from scp_shared.execution.types import TradeRecord
from scp_shared.messaging.schemas import (
    CandleMessage,
    FeaturesMessage,
    SignalMessage,
    TradeMessage,
)

from execution_svc.broker import BaseBroker
from execution_svc.daily_state import DailyStateTracker
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository

logger = get_logger(__name__)


def is_valid_candle(candle: Candle) -> bool:
    """Check if candle has valid OHLC data (no NaN/Inf).

    Args:
        candle: Candle to validate

    Returns:
        True if candle is valid, False if it has NaN or Inf values
    """
    values = [candle.open, candle.high, candle.low, candle.close]
    for val in values:
        if math.isnan(val) or math.isinf(val):
            return False
    return True


class TradeManager:
    """Orchestrates trade lifecycle with SL/TP monitoring.
    
    Manages the complete trade flow:
    1. Receive signals from Bot Core
    2. Track confirmation via state machines
    3. Execute entry via broker
    4. Monitor SL/TP on each candle
    5. Apply invalidation rules
    6. Close trades and publish events
    
    Example:
        >>> manager = TradeManager(broker, sm_manager, repo, publisher, config)
        >>> await manager.on_signal(signal_msg)
        >>> await manager.on_candle(candle_msg, features_msg)
    """
    
    def __init__(
        self,
        broker: BaseBroker,
        state_machine_manager: StateMachineManager,
        trade_repository: TradeRepository,
        trade_publisher: TradePublisher,
        db_pool: DatabasePool,
        max_active_trades: int = 1,
        pdll_limit: float = 600.0,
        max_trades_per_day: int = 2,
    ) -> None:
        """Initialize trade manager.
        
        Args:
            broker: Broker interface for order execution
            state_machine_manager: State machine manager
            trade_repository: Trade repository for DB persistence
            trade_publisher: Trade publisher for Redis events
            db_pool: Database pool for candle queries
            max_active_trades: Maximum concurrent trades (default: 1)
            pdll_limit: Per day loss limit in points (default: 600.0)
            max_trades_per_day: Maximum trades per day (default: 2)
        """
        self._broker = broker
        self._sm_manager = state_machine_manager
        self._repo = trade_repository
        self._publisher = trade_publisher
        self._candle_repo = CandleRepository(db_pool)
        self._max_active_trades = max_active_trades
        
        # Active trades (in-memory cache)
        self._active_trades: dict[str, TradeRecord] = {}
        
        # Pending signals awaiting next bar open execution
        self._pending_signals: list[SignalMessage] = []
        
        # Daily state tracker for PDLL and trade limits
        self._daily_tracker = DailyStateTracker(
            pdll_limit=pdll_limit,
            max_trades_per_day=max_trades_per_day,
        )
        
        # Invalidation checker (pass pdll_limit for PDLL breach detection)
        self._invalidation_checker = InvalidationChecker(pdll_limit=pdll_limit)
        
        # Bar tracking for time-based invalidation
        self._trade_entry_bars: dict[str, int] = {}
        
        # Track last processed candle timestamp for late signal detection
        # In replay mode, signals arrive after candles, so we need to know
        # if a signal's execution bar has already been processed
        self._last_processed_candle_ts: datetime | None = None
        
        # Track closed trade time ranges for data-time overlap detection
        # In replay mode, signals arrive after candles, so we may receive
        # a late signal that would have been generated during a trade's active period
        # Format: list of (opened_at, closed_at) tuples
        self._closed_trade_ranges: list[tuple[datetime, datetime]] = []
    
    async def on_signal(self, signal: SignalMessage) -> None:
        """Handle incoming signal from Bot Core.
        
        If signal's execution time has already passed (late arrival in replay mode),
        fetches the execution candle from database and executes immediately.
        Otherwise, buffers signal for next bar execution.
        
        Args:
            signal: Signal message
        """
        # Check if we can take more trades
        if len(self._active_trades) >= self._max_active_trades:
            logger.info(
                f"Signal {signal.id} rejected: max active trades reached "
                f"({len(self._active_trades)}/{self._max_active_trades})"
            )
            return
        
        # CRITICAL FIX: Check if signal's execution time has already passed
        # Signal at T should execute at T+1 (next bar). If we're past T+1,
        # the execution candle was already processed.
        expected_exec_time = signal.timestamp + timedelta(minutes=1)
        
        # For replay mode: if signal arrives late (after its execution bar was processed),
        # execute immediately using the signal's pre-calculated entry_price.
        # We track _last_processed_candle_ts to know which candles have been processed.
        if (
            self._last_processed_candle_ts is not None
            and expected_exec_time <= self._last_processed_candle_ts
        ):
            # CRITICAL: Check for data-time overlap with closed trades
            # In replay mode, signals arrive after candles, so we may receive
            # a late signal that would have been generated during another trade's active period.
            # We must block these to match backtester behavior.
            for opened_at, closed_at in self._closed_trade_ranges:
                if opened_at <= signal.timestamp < closed_at:
                    logger.info(
                        f"Late signal {signal.id} blocked: data-time overlap with trade "
                        f"({opened_at} - {closed_at}), signal at {signal.timestamp}"
                    )
                    return
            
            # Signal arrived late (after execution bar processed) - execute immediately
            logger.info(
                f"Signal {signal.id} arrived late - executing immediately "
                f"(expected={expected_exec_time}, last_processed={self._last_processed_candle_ts})"
            )
            
            # Create state machine with auto_confirm=True for late signals
            # since we've verified the execution candle exists in DB
            await self._sm_manager.create_from_signal(signal, auto_confirm=True)
            
            # Execute immediately using the candle's open price
            # Note: We use signal.entry_price which was calculated at signal generation time
            await self.execute_entry(signal, float(signal.entry_price))
            return
        
        # Normal case: buffer signal for next bar execution
        self._pending_signals.append(signal)
        
        # Create state machine for this signal
        await self._sm_manager.create_from_signal(signal)
        
        logger.info(
            f"Signal buffered for next bar: {signal.direction} {signal.setup_type} "
            f"(score={signal.score:.1f}, confidence={signal.confidence}, "
            f"id={signal.id})"
        )
    
    def check_session_reset(self, current_timestamp: datetime) -> None:
        """Check for session reset at day boundaries.
        
        CRITICAL: Must be called BEFORE execute_pending_signals to ensure
        daily limits (PDLL, max trades) are fresh for the new trading day.
        
        Args:
            current_timestamp: Current timestamp to extract date from
        """
        self._daily_tracker.check_session_reset(current_timestamp.date())
    
    async def on_candle(
        self,
        candle: CandleMessage,
        features: FeaturesMessage | None = None,
    ) -> None:
        """Process candle for active trades and pending signals.
        
        Args:
            candle: Current candle
            features: Optional features for invalidation checking
        """
        # Note: bar counter is now incremented in main.py before execute_pending_signals
        # to ensure confirmation can happen before execution
        
        # Convert to internal Candle type
        candle_obj = Candle(
            timestamp=candle.timestamp,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            source="STREAM",
        )
        
        # Safety check: Invalid candles should already be filtered in main.py
        # before bar counter increment, but we keep this as a defensive check
        if not is_valid_candle(candle_obj):
            logger.warning(
                f"Invalid candle reached trade_manager.on_candle() at {candle.timestamp} "
                f"(NaN/Inf detected) - this should have been caught earlier"
            )
            return
        
        # Convert features to dict (expanded to include all fields needed by invalidation checks)
        features_dict: dict[str, Any] | None = None
        if features is not None:
            features_dict = {
                # Core features (original)
                "vwap": features.vwap,
                "rsi": features.rsi,
                "structure_label": features.structure_label,
                # VWAP slope for FADE invalidation (requires slope confirmation)
                "vwap_slope": features.vwap_slope,
                # DXY correlation for flip detection
                "dxy_corr": features.dxy_correlation,
                # DXY micro correlations for DXY_CONTINUATION (use dxy_5m_corr as proxy)
                "dxy_corr_1m": getattr(features, "dxy_5m_corr", None),
                "dxy_corr_5m": getattr(features, "dxy_5m_corr", None),
                # DXY structure for DXY_CONTINUATION invalidation
                "dxy_structure": features.dxy_structure,
                # HTF structure for VWAP_RECLAIM micro break confirmation
                "htf_structure_label": features.htf_structure_label,
            }
        
        # Check active trades for SL/TP and invalidation
        # Note: execute_pending_signals is called from main.py before on_candle
        for _trade_id, trade in list(self._active_trades.items()):
            await self._check_trade_exit(trade, candle_obj, features_dict)
    
    async def execute_pending_signals(
        self, next_bar_open: float, candle_timestamp: datetime
    ) -> None:
        """Execute buffered signals at next bar open price.
        
        Args:
            next_bar_open: Open price of the next bar
            candle_timestamp: Timestamp of the candle being processed
        """
        # CRITICAL: Track last processed candle timestamp for late signal detection
        # This must be updated BEFORE any early returns so on_signal() knows
        # which candles have been processed
        self._last_processed_candle_ts = candle_timestamp
        
        if not self._pending_signals:
            return
        
        logger.info(
            f"Executing {len(self._pending_signals)} pending signals "
            f"at open={next_bar_open:.2f}, candle_ts={candle_timestamp}"
        )
        
        # Signals ready for execution (candle timestamp >= signal timestamp)
        # A signal should execute when the candle is the "next bar" after signal
        signals_to_keep: list[SignalMessage] = []
        
        for signal in self._pending_signals:
            # CRITICAL FIX: Only execute signal at the CORRECT next bar
            # Signal at T should execute at T+1 (next bar), not any future bar
            # Expected execution time is signal.timestamp + 1 minute (for 1m bars)
            expected_exec_time = signal.timestamp + timedelta(minutes=1)
            
            if candle_timestamp < expected_exec_time:
                # Candle is before expected execution time - keep signal for later
                signals_to_keep.append(signal)
                continue
            
            # NOTE: We no longer discard "stale" signals because:
            # 1. Bot Core already calculated the correct entry_price at signal generation time
            # 2. In replay mode, streams are desynchronized (signals arrive after candles)
            # 3. The signal.entry_price contains the correct price, not next_bar_open
            # 
            # IMPORTANT: Kill switch clears _pending_signals when activated/resumed to prevent
            # stale signals with outdated entry prices from executing after extended kill periods.
            # This ensures entry prices remain current even if kill switch is active for hours/days.
            
            # Check concurrent trade limit FIRST
            # (prevents attempting execution when already at capacity)
            if len(self._active_trades) >= self._max_active_trades:
                logger.info(
                    f"Signal {signal.id} blocked: max active trades reached "
                    f"({len(self._active_trades)}/{self._max_active_trades})"
                )
                continue
            
            # Check daily limits before executing
            can_trade, reason = self._daily_tracker.can_trade()
            if not can_trade:
                logger.info(f"Signal {signal.id} blocked by daily limits: {reason}")
                continue
            
            # Use signal.entry_price (calculated by Bot Core at signal generation time)
            # This is correct even in replay mode where streams are desynchronized
            await self.execute_entry(signal, float(signal.entry_price))
        
        # Keep signals that weren't ready yet
        self._pending_signals = signals_to_keep
    
    async def _check_trade_exit(
        self,
        trade: TradeRecord,
        candle: Candle,
        features: dict[str, Any] | None,
    ) -> None:
        """Check if trade should exit (SL/TP or invalidation).
        
        Args:
            trade: Active trade
            candle: Current candle
            features: Optional features dict
        """
        # Calculate bars elapsed
        entry_bar = self._trade_entry_bars.get(trade.trade_id, 0)
        current_bar = self._sm_manager._bar_counter
        bars_elapsed = current_bar - entry_bar
        
        # Check all exit conditions (this updates internal state via update_state())
        should_exit, reason = self._invalidation_checker.check_all(
            trade, candle, bars_elapsed, features
        )
        
        # Check if trade just reached +1R (and persist to database)
        # MUST happen AFTER check_all() to ensure we persist the current candle's state
        if not trade.reached_1r:
            state = self._invalidation_checker._get_trade_state(trade.trade_id)
            if state.get("reached_1r", False):
                # Trade just reached +1R - persist to database immediately
                await self._repo.update_reached_1r(trade.trade_id, True)
                trade.reached_1r = True
                logger.info(
                    f"Trade {trade.trade_id} reached +1R, persisted to database"
                )
        
        if should_exit:
            # Determine exit price based on reason
            if reason and "SL_HIT" in reason:
                exit_price = trade.sl_price
            elif reason and "TP_HIT" in reason:
                exit_price = trade.tp_price
            else:
                # Invalidation - exit at close
                exit_price = candle.close
            
            await self._close_trade(
                trade, exit_price, reason or "UNKNOWN", candle.timestamp
            )
    
    async def execute_entry(
        self,
        signal: SignalMessage,
        entry_price: float,
    ) -> TradeRecord | None:
        """Execute trade entry.
        
        Args:
            signal: Signal to execute
            entry_price: Entry price (typically next bar open)
            
        Returns:
            TradeRecord if successful, None otherwise
        """
        try:
            # Check confirmation and re-entry protection for VWAP_RECLAIM
            # check_confirmation() handles auto-confirm for Phase 6 and returns can_execute()
            confirmation_result = self._sm_manager.check_confirmation(signal.id)
            
            if not confirmation_result:
                sm = self._sm_manager.get_state_machine(signal.id)
                exec_count = sm.execution_count if sm else 0
                logger.warning(
                    f"Signal {signal.id} blocked: not confirmed or max executions reached "
                    f"(execution_count={exec_count})"
                )
                return None
            
            # Place order via broker
            order_result = await self._broker.place_order(
                symbol="GC",
                side=cast(Literal["long", "short"], signal.direction),
                quantity=1,  # Hardcoded for Phase 6
                price=entry_price,
            )
            
            if order_result.status != "filled":
                logger.error(
                    f"Order not filled for signal {signal.id}: "
                    f"{order_result.status}"
                )
                return None
            
            # Create trade record
            # Entry timestamp should be NEXT BAR after signal (signal.timestamp + 1 minute)
            # This matches backtester behavior: signal at T, entry at T+1
            expected_exec_time = signal.timestamp + timedelta(minutes=1)
            opened_at = expected_exec_time
            entry_bar_idx = self._sm_manager._bar_counter
            
            trade_id = await self._repo.insert_trade(
                signal_id=signal.id,
                direction=signal.direction,
                setup_type=signal.setup_type,
                entry_price=entry_price,
                sl_price=signal.sl_price,
                tp_price=signal.tp_price,
                quantity=1,
                opened_at=opened_at,
                entry_bar_idx=entry_bar_idx,
            )
            
            # Calculate risk/reward
            # Convert Decimal prices to float for arithmetic compatibility
            sl_price = float(signal.sl_price)
            tp_price = float(signal.tp_price)
            if signal.direction == "long":
                risk_amount = entry_price - sl_price
                reward_amount = tp_price - entry_price
            else:  # short
                risk_amount = sl_price - entry_price
                reward_amount = entry_price - tp_price
            
            # Create TradeRecord
            trade = TradeRecord(
                trade_id=trade_id,
                signal_id=signal.id,
                symbol="GC",
                direction=signal.direction,
                setup_type=signal.setup_type,
                entry_price=entry_price,
                sl_price=signal.sl_price,
                tp_price=signal.tp_price,
                risk_amount=risk_amount,
                reward_amount=reward_amount,
                entry_timestamp=opened_at,
                entry_bar_idx=entry_bar_idx,
                reached_1r=False,
            )
            
            # Store in active trades
            self._active_trades[trade_id] = trade
            self._trade_entry_bars[trade_id] = self._sm_manager._bar_counter
            
            # Record trade opened for daily limits tracking
            self._daily_tracker.record_trade_opened()
            
            # Mark state machine as executed
            await self._sm_manager.execute(signal.id, self._sm_manager._bar_counter)
            
            # Publish trade opened event
            trade_msg = TradeMessage(
                id=trade_id,
                signal_id=signal.id,
                direction=signal.direction,
                entry_price=entry_price,
                sl_price=signal.sl_price,
                tp_price=signal.tp_price,
                quantity=1,
                opened_at=opened_at,
            )
            await self._publisher.publish_opened(trade_msg)
            
            logger.info(
                f"Trade executed: {signal.direction} {signal.setup_type} "
                f"@ {entry_price:.2f} (SL={signal.sl_price:.2f}, "
                f"TP={signal.tp_price:.2f}, trade_id={trade_id})"
            )
            
            return trade
        
        except Exception as e:
            logger.error(
                f"Failed to execute entry for signal {signal.id}: {e}",
                exc_info=True,
            )
            return None
    
    async def _close_trade(
        self,
        trade: TradeRecord,
        exit_price: float,
        exit_reason: str,
        closed_at: datetime,
    ) -> None:
        """Close trade and publish event.
        
        Args:
            trade: Trade to close
            exit_price: Exit price
            exit_reason: Exit reason
            closed_at: Close timestamp
        """
        broker_position_closed = False
        
        
        # Try to close position via broker (may not exist if orphaned)
        try:
            await self._broker.close_position(symbol=trade.symbol, price=exit_price)
            broker_position_closed = True
        except ValueError as e:
            # Position doesn't exist in broker (orphaned trade after restart)
            # This is expected when broker state wasn't restored properly
            logger.warning(
                f"Broker position not found for trade {trade.trade_id} "
                f"(orphaned trade): {e}. Proceeding with trade closure."
            )
        except Exception as e:
            logger.error(
                f"Unexpected error closing broker position for trade "
                f"{trade.trade_id}: {e}",
                exc_info=True,
            )
        
        # Always update trade in database and clean up,
        # even if broker position was missing
        try:
            await self._repo.close_trade(
                trade_id=trade.trade_id,
                exit_price=exit_price,
                exit_reason=exit_reason,
                closed_at=closed_at,
            )
            
            
            # Calculate P&L
            if trade.direction == "long":
                pnl_points = exit_price - trade.entry_price
            else:  # short
                pnl_points = trade.entry_price - exit_price
            
            # Record trade closed for daily limits tracking
            self._daily_tracker.record_trade_closed(pnl_points)
            
            # Update InvalidationChecker's daily state for loss streak and PnL tracking
            # Pass actual PnL so PDLL breach detection works correctly
            # CRITICAL: Pass close_timestamp to ensure session date is based on when
            # the trade closed, not when it opened (fixes multi-day trade attribution bug)
            won = pnl_points > 0 if pnl_points != 0 else None
            self._invalidation_checker.record_trade_outcome(
                trade, won, pnl_points=pnl_points, close_timestamp=closed_at
            )
            
            # Remove from active trades (critical - must happen even if broker failed)
            if trade.trade_id in self._active_trades:
                del self._active_trades[trade.trade_id]
            if trade.trade_id in self._trade_entry_bars:
                del self._trade_entry_bars[trade.trade_id]
            
            # Track closed trade time range for data-time overlap detection
            # This prevents late signals from executing during periods when
            # a trade was active (in data time, not wall-clock time)
            self._closed_trade_ranges.append((trade.entry_timestamp, closed_at))
            
            # Reset invalidation checker state
            self._invalidation_checker.reset_trade(trade.trade_id)
            
            # Reset context execution count to allow new trades for the same day
            # This matches backtester behavior where multiple trades per day are allowed
            self._sm_manager.reset_context_for_signal(trade.signal_id)
            
            # Publish trade closed event
            trade_msg = TradeMessage(
                id=trade.trade_id,
                signal_id=trade.signal_id,
                direction=trade.direction,
                entry_price=trade.entry_price,
                sl_price=trade.sl_price,
                tp_price=trade.tp_price,
                quantity=1,
                opened_at=trade.entry_timestamp,
                closed_at=closed_at,
                exit_price=exit_price,
                pnl_points=pnl_points,
                exit_reason=exit_reason,
            )
            await self._publisher.publish_closed(trade_msg)
            
            status_note = " (orphaned trade)" if not broker_position_closed else ""
            
            logger.info(
                f"Trade closed: {trade.direction} exit @ {exit_price:.2f} "
                f"(pnl={pnl_points:.2f} points, reason={exit_reason}, "
                f"trade_id={trade.trade_id}){status_note}"
            )
        
        except ValueError as e:
            # Trade not found in database - this indicates a data inconsistency
            logger.error(
                f"Trade {trade.trade_id} not found in database during close "
                f"operation. This indicates state inconsistency between "
                f"in-memory tracking and database. Cleaning up local state only. "
                f"Error: {e}"
            )
            # Clean up local state to prevent memory leaks, but DO NOT publish event
            # since database was never updated
            if trade.trade_id in self._active_trades:
                del self._active_trades[trade.trade_id]
            if trade.trade_id in self._trade_entry_bars:
                del self._trade_entry_bars[trade.trade_id]
        
        except Exception as e:
            logger.error(
                f"Failed to close trade {trade.trade_id} in database: {e}",
                exc_info=True,
            )
            # Still try to remove from active trades to prevent blocking
            if trade.trade_id in self._active_trades:
                del self._active_trades[trade.trade_id]
            if trade.trade_id in self._trade_entry_bars:
                del self._trade_entry_bars[trade.trade_id]
    
    async def restore_active_trades(self) -> None:
        """Restore active trades from database on startup.
        
        Also reconciles broker positions to match restored trades,
        ensuring broker state is consistent with database state.
        
        CRITICAL: This method also restores daily state (P&L and trade count)
        from today's trades to ensure PDLL and trade limit enforcement remains
        consistent after service restarts.
        """
        # Step 1: Restore daily state from today's trades
        # This MUST happen before any trading to prevent exceeding daily limits
        from datetime import datetime
        
        today = datetime.now()
        todays_trades = await self._repo.get_trades_for_date(today)
        self._daily_tracker.restore_from_trades(todays_trades, today.date())
        
        logger.info(
            f"Restored daily state: {len(todays_trades)} trades today, "
            f"daily_pnl={self._daily_tracker.state.daily_pnl:.2f}"
        )
        
        # Step 2: Restore active trades
        open_trades = await self._repo.get_open_trades()
        
        for trade in open_trades:
            self._active_trades[trade.trade_id] = trade
            
            # Restore entry_bar_idx from database
            if trade.entry_bar_idx is not None:
                self._trade_entry_bars[trade.trade_id] = trade.entry_bar_idx
            else:
                # Fallback: use current bar counter if entry_bar_idx not set
                # (for trades created before migration)
                self._trade_entry_bars[trade.trade_id] = (
                    self._sm_manager._bar_counter
                )
                logger.warning(
                    f"Trade {trade.trade_id} has no entry_bar_idx, "
                    f"using current bar counter"
                )
            
            # Restore invalidation checker state
            self._invalidation_checker.restore_trade_state(
                trade.trade_id,
                reached_1r=trade.reached_1r,
                # Would need to persist this too for full recovery
                vwap_reclaimed=False,
            )
        
        logger.info(f"Restored {len(open_trades)} active trades from database")
        
        # Step 3: Reconcile broker positions with restored trades
        if open_trades:
            # Build list of (symbol, side, entry_price, quantity) tuples
            position_data = [
                # quantity=1 for Phase 6
                (trade.symbol, trade.direction, trade.entry_price, 1)
                for trade in open_trades
            ]
            await self._broker.reconcile_positions(position_data)  # type: ignore[attr-defined]
            logger.info(f"Reconciled broker positions for {len(open_trades)} trades")

