"""Trade lifecycle manager with SL/TP monitoring."""

from datetime import datetime
from typing import Any

from scp_shared.common.logger import get_logger
from scp_shared.common.types import Candle
from scp_shared.execution import InvalidationChecker
from scp_shared.execution.types import TradeRecord
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage, SignalMessage, TradeMessage

from execution_svc.broker import BaseBroker
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository

logger = get_logger(__name__)


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
        max_active_trades: int = 1,
    ) -> None:
        """Initialize trade manager.
        
        Args:
            broker: Broker interface for order execution
            state_machine_manager: State machine manager
            trade_repository: Trade repository for DB persistence
            trade_publisher: Trade publisher for Redis events
            max_active_trades: Maximum concurrent trades (default: 1)
        """
        self._broker = broker
        self._sm_manager = state_machine_manager
        self._repo = trade_repository
        self._publisher = trade_publisher
        self._max_active_trades = max_active_trades
        
        # Active trades (in-memory cache)
        self._active_trades: dict[str, TradeRecord] = {}
        
        # Invalidation checker
        self._invalidation_checker = InvalidationChecker()
        
        # Bar tracking for time-based invalidation
        self._trade_entry_bars: dict[str, int] = {}
    
    async def on_signal(self, signal: SignalMessage) -> None:
        """Handle incoming signal from Bot Core.
        
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
        
        # Create state machine for this signal
        await self._sm_manager.create_from_signal(signal)
        
        logger.info(
            f"Signal received: {signal.direction} {signal.setup_type} "
            f"(score={signal.score:.1f}, confidence={signal.confidence}, id={signal.id})"
        )
    
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
        # Increment bar counter
        self._sm_manager.increment_bar_counter()
        
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
        
        # Convert features to dict
        features_dict: dict[str, Any] | None = None
        if features is not None:
            features_dict = {
                "vwap": features.vwap,
                "rsi": features.rsi,
                "structure_label": features.structure_label,
            }
        
        # 1. Check active trades for SL/TP and invalidation
        for trade_id, trade in list(self._active_trades.items()):
            await self._check_trade_exit(trade, candle_obj, features_dict)
        
        # 2. Check pending signals for confirmation and execution
        await self._check_pending_signals(candle)
    
    async def _check_pending_signals(self, candle: CandleMessage) -> None:
        """Check pending signals for confirmation and execution.
        
        Args:
            candle: Current candle
        """
        # Get all pending state machines (simplified - would iterate properly in production)
        # For Phase 6, we'll check confirmation on next bar and execute
        pass  # Signals are executed in on_signal for simplification
    
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
        
        # Check all exit conditions
        should_exit, reason = self._invalidation_checker.check_all(
            trade, candle, bars_elapsed, features
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
            
            await self._close_trade(trade, exit_price, reason or "UNKNOWN", candle.timestamp)
    
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
            # Place order via broker
            order_result = await self._broker.place_order(
                symbol="GC",
                side=signal.direction,
                quantity=1,  # Hardcoded for Phase 6
                price=entry_price,
            )
            
            if order_result.status != "filled":
                logger.error(f"Order not filled for signal {signal.id}: {order_result.status}")
                return None
            
            # Create trade record
            opened_at = datetime.utcnow()
            trade_id = await self._repo.insert_trade(
                signal_id=signal.id,
                direction=signal.direction,
                setup_type=signal.setup_type,
                entry_price=entry_price,
                sl_price=signal.sl_price,
                tp_price=signal.tp_price,
                quantity=1,
                opened_at=opened_at,
            )
            
            # Calculate risk/reward
            if signal.direction == "long":
                risk_amount = entry_price - signal.sl_price
                reward_amount = signal.tp_price - entry_price
            else:  # short
                risk_amount = signal.sl_price - entry_price
                reward_amount = entry_price - signal.tp_price
            
            # Create TradeRecord
            trade = TradeRecord(
                trade_id=trade_id,
                symbol="GC",
                direction=signal.direction,
                setup_type=signal.setup_type,
                entry_price=entry_price,
                sl_price=signal.sl_price,
                tp_price=signal.tp_price,
                risk_amount=risk_amount,
                reward_amount=reward_amount,
                entry_timestamp=opened_at,
            )
            
            # Store in active trades
            self._active_trades[trade_id] = trade
            self._trade_entry_bars[trade_id] = self._sm_manager._bar_counter
            
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
                f"Trade executed: {signal.direction} {signal.setup_type} @ {entry_price:.2f} "
                f"(SL={signal.sl_price:.2f}, TP={signal.tp_price:.2f}, trade_id={trade_id})"
            )
            
            return trade
        
        except Exception as e:
            logger.error(f"Failed to execute entry for signal {signal.id}: {e}", exc_info=True)
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
                f"Unexpected error closing broker position for trade {trade.trade_id}: {e}",
                exc_info=True,
            )
        
        # Always update trade in database and clean up, even if broker position was missing
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
            
            # Remove from active trades (critical - must happen even if broker failed)
            if trade.trade_id in self._active_trades:
                del self._active_trades[trade.trade_id]
            if trade.trade_id in self._trade_entry_bars:
                del self._trade_entry_bars[trade.trade_id]
            
            # Reset invalidation checker state
            self._invalidation_checker.reset_trade(trade.trade_id)
            
            # Publish trade closed event
            trade_msg = TradeMessage(
                id=trade.trade_id,
                signal_id=str(trade.trade_id),  # Would need signal_id from DB in production
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
        """
        open_trades = await self._repo.get_open_trades()
        
        for trade in open_trades:
            self._active_trades[trade.trade_id] = trade
            # Set entry bar to 0 (unknown on recovery)
            self._trade_entry_bars[trade.trade_id] = 0
        
        logger.info(f"Restored {len(open_trades)} active trades from database")
        
        # Reconcile broker positions with restored trades
        if open_trades and hasattr(self._broker, "reconcile_positions"):
            # Build list of (symbol, side, entry_price, quantity) tuples
            position_data = [
                (trade.symbol, trade.direction, trade.entry_price, 1)  # quantity=1 for Phase 6
                for trade in open_trades
            ]
            await self._broker.reconcile_positions(position_data)
            logger.info(f"Reconciled broker positions for {len(open_trades)} trades")

