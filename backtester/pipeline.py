"""Backtesting pipeline orchestration.

Integrates feature generation, scoring, validation, and entry execution.

This module provides the complete backtesting pipeline that orchestrates:
1. Feature generation (BacktestProcessor)
2. HTF bias computation (caller-provided)
3. Signal scoring (RuleEngine)
4. Signal validation (ValidationEngine)
5. Entry execution (EntryModel)
6. Trade simulation (Simulator)
"""

from collections.abc import Callable
from datetime import datetime

import pandas as pd
from common.logger import get_logger
from data_layer.multi_timeframe_helpers import extract_execution_dataframes
from data_layer.multi_timeframe_sync import MultiTimeframeData
from feature_engine.backtesting import BacktestProcessor
from feature_engine.integration import process_features_with_validation
from rule_engine.htf.integration import create_htf_bias_func_with_sync_layer
from rule_engine.htf.types import HTFBias

from backtester.entry_model import EntryExecution, execute_entry_at_next_open
from backtester.invalidations import InvalidationChecker
from backtester.simulator import simulate_trade_outcome
from backtester.trade import Trade, create_trade_from_entry

logger = get_logger(__name__)


def _timestamp_to_datetime(value: pd.Timestamp | datetime) -> datetime:
    """Normalize pandas timestamps to timezone-aware datetimes."""
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    msg = f"Unsupported timestamp type: {type(value)}"
    raise TypeError(msg)


def _compute_entry_htf_bias_map(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    htf_bias_func: Callable[[pd.Series, dict], HTFBias],
    target_timestamps: set[datetime],
) -> dict[datetime, HTFBias]:
    """Compute HTF bias for the specific timestamps where entries execute."""
    if not target_timestamps:
        return {}

    processor = BacktestProcessor(timeframe=timeframe)
    bias_map: dict[datetime, HTFBias] = {}

    for features, validation_context in processor.iterate_with_context(gc_df, dxy_df):
        timestamp = _timestamp_to_datetime(features["timestamp"])
        if timestamp in target_timestamps and timestamp not in bias_map:
            bias_map[timestamp] = htf_bias_func(features, validation_context)
            if len(bias_map) == len(target_timestamps):
                break

    return bias_map


def _is_htf_aligned(direction: str, bias_value: str | None) -> bool:
    """Check if trade direction aligns with HTF bias string."""
    if bias_value is None:
        return False

    return (bias_value == "bullish" and direction == "long") or (
        bias_value == "bearish" and direction == "short"
    )


def run_backtest_with_entries(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    market_state: dict,
    htf_bias_func: Callable[[pd.Series, dict], HTFBias],
    log_signals: bool = False,
    log_dir: str | None = None,
    processor: BacktestProcessor | None = None,
) -> tuple[list[EntryExecution], BacktestProcessor]:
    """Run complete backtest pipeline with entry execution.

    This function orchestrates the full backtesting pipeline:
    1. Iterate through features bar-by-bar (BacktestProcessor)
    2. Compute HTF bias for each bar (caller-provided function)
    3. Score and validate signals (RuleEngine + ValidationEngine)
    4. Execute entries at next bar open (EntryModel)

    Only A+ confidence signals that pass full SOP validation will result in
    executed entries. All signals (including rejected ones) produce
    EntryExecution records for analysis.

    Args:
        gc_df: GC DataFrame with DatetimeIndex and OHLCV columns
        dxy_df: DXY DataFrame with DatetimeIndex and OHLCV columns
        timeframe: Timeframe string (e.g., "1m", "15m", "1h")
        market_state: Market context dict containing:
            - buffer_phase: Current capital phase ("startup", "growth", etc.)
            - tier_active: Active enforcer tier ("Conservative", "EarlyMild", etc.)
            - ceo_directive_active: Whether CEO directive is active (bool)
            - news_ok: Whether trading is allowed during news events (bool)
            - session_ok: Whether current session is valid for trading (bool)
        htf_bias_func: Function that computes HTFBias given (features, context).
            Signature: (pd.Series, dict) -> HTFBias
        log_signals: Whether to log signals to disk (default: False)
        log_dir: Directory for signal logs (required if log_signals=True)
        processor: Optional BacktestProcessor instance to reuse (for state persistence)

    Returns:
        Tuple of (list of EntryExecution objects, processor instance).
        EntryExecution list includes both successful entries (executed=True) and
        rejected entries (executed=False with rejection_reason).
        Processor instance is returned to allow recording trade outcomes.

    Example:
        >>> def compute_htf_bias(features, context):
        ...     # Compute HTF bias using 1H and 15M data
        ...     return HTFBias(bias="bullish", direction="long", ...)
        >>>
        >>> market_state = {
        ...     "buffer_phase": "growth",
        ...     "tier_active": "EarlyMild",
        ...     "ceo_directive_active": True,
        ...     "news_ok": True,
        ...     "session_ok": True,
        ... }
        >>>
        >>> executions, processor = run_backtest_with_entries(
        ...     gc_df=gc_data,
        ...     dxy_df=dxy_data,
        ...     timeframe="1m",
        ...     market_state=market_state,
        ...     htf_bias_func=compute_htf_bias,
        ... )
        >>>
        >>> # Analyze results
        >>> executed = [e for e in executions if e.executed]
        >>> print(f"Executed entries: {len(executed)}/{len(executions)}")
    """
    logger.info(
        f"Starting backtest pipeline: timeframe={timeframe}, "
        f"tier={market_state.get('tier_active')}"
    )

    # Initialize processor (reuse if provided)
    if processor is None:
        processor = BacktestProcessor(timeframe=timeframe)

    # Collect all entry executions
    executions: list[EntryExecution] = []
    signal_count = 0
    executed_count = 0

    # Iterate through features with entry context
    for (
        features,
        validation_context,
        next_candle,
    ) in processor.iterate_with_entry_context(gc_df, dxy_df):
        signal_count += 1

        # Compute HTF bias using caller-provided function
        htf_bias = htf_bias_func(features, validation_context)

        # Get session constraints from validation context
        session_constraints = validation_context.get("session_constraints")
        if session_constraints is None:
            logger.debug(
                "No session constraints in validation context at "
                f"{features['timestamp']} - validation will use defaults"
            )

        # Score and validate signal
        signal = process_features_with_validation(
            features=features,
            htf_bias=htf_bias,
            market_state=market_state,
            session_constraints=session_constraints,
            guardrail_result=validation_context.get("guardrail_result"),
            log_signals=log_signals,
            log_dir=log_dir,
        )

        # Execute entry at next bar open
        execution = execute_entry_at_next_open(signal, next_candle)
        executions.append(execution)

        if execution.executed:
            executed_count += 1
            logger.debug(
                f"Entry executed: {signal.direction} {signal.symbol} @ "
                f"{execution.entry_price} (score={signal.score:.1f})"
            )

    logger.info(
        f"Backtest pipeline complete: {signal_count} signals, "
        f"{executed_count} entries executed "
        f"({100*executed_count/signal_count if signal_count > 0 else 0:.1f}%)"
    )

    return executions, processor


def get_future_candles(
    gc_df: pd.DataFrame,
    entry_timestamp: pd.Timestamp,
    max_bars: int,
) -> pd.DataFrame:
    """Extract future candles after entry for simulation.

    Args:
        gc_df: Full GC DataFrame with DatetimeIndex
        entry_timestamp: Entry timestamp
        max_bars: Maximum number of bars to extract (20 for continuation, 10 for fade)

    Returns:
        DataFrame with future candles (up to max_bars)
    """
    # Find entry index
    try:
        entry_idx = gc_df.index.get_loc(entry_timestamp)
    except KeyError:
        logger.warning(
            f"Entry timestamp {entry_timestamp} not found in dataset. "
            "Returning empty DataFrame."
        )
        return pd.DataFrame()

    # Get candles after entry (up to max_bars)
    start_idx = entry_idx + 1
    end_idx = min(start_idx + max_bars, len(gc_df))

    future_candles = gc_df.iloc[start_idx:end_idx]

    logger.debug(
        f"Extracted {len(future_candles)} future candles "
        f"(max_bars={max_bars}, available={len(gc_df) - entry_idx - 1})"
    )

    return future_candles


def run_backtest_with_trades(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    market_state: dict,
    htf_bias_func: Callable[[pd.Series, dict], HTFBias],
    risk_config: dict,
    config: dict | None = None,
    log_signals: bool = False,
    log_dir: str | None = None,
) -> list[Trade]:
    """Run complete backtest pipeline with trade simulation.

    This function orchestrates the full backtesting pipeline including trade outcomes:
    1. Generate signals (run_backtest_with_entries)
    2. For each executed entry:
       a. Create Trade object with SL/TP
       b. Simulate outcome (TP/SL/timeout/invalidation)
    3. Return list of closed trades

    Args:
        gc_df: GC DataFrame with DatetimeIndex and OHLCV columns
        dxy_df: DXY DataFrame with DatetimeIndex and OHLCV columns
        timeframe: Timeframe string (e.g., "1m", "15m", "1h")
        market_state: Market context dict (buffer_phase, tier_active, etc.)
        htf_bias_func: Function that computes HTFBias given (features, context)
        risk_config: Risk configuration dict containing:
            - risk_per_trade: Dollar risk per trade
            - buffer_phase: Current capital phase
            - max_contracts: Maximum contracts allowed
        config: Optional config dict for dollar PnL calculation
        log_signals: Whether to log signals to disk (default: False)
        log_dir: Directory for signal logs (required if log_signals=True)

    Returns:
        List of Trade objects (all closed with outcomes)

    Example:
        >>> def compute_htf_bias(features, context):
        ...     return HTFBias(bias="bullish", direction="long", ...)
        >>>
        >>> risk_config = {
        ...     "risk_per_trade": 350,
        ...     "buffer_phase": "startup",
        ...     "max_contracts": 1,
        ... }
        >>>
        >>> trades = run_backtest_with_trades(
        ...     gc_df=gc_data,
        ...     dxy_df=dxy_data,
        ...     timeframe="1m",
        ...     market_state=market_state,
        ...     htf_bias_func=compute_htf_bias,
        ...     risk_config=risk_config,
        ...     config=config,
        ... )
        >>>
        >>> # Analyze results
        >>> winning_trades = [t for t in trades if t.pnl > 0]
        >>> print(f"Win rate: {len(winning_trades)/len(trades)*100:.1f}%")
    """
    logger.info(
        f"Starting backtest with trades: timeframe={timeframe}, "
        f"tier={market_state.get('tier_active')}"
    )

    # Create processor upfront for state persistence across the entire backtest
    # This ensures loss streaks and other state evolve correctly as trades close
    processor = BacktestProcessor(timeframe=timeframe)

    # Step 1: Get executed entries (reuse processor for state persistence)
    executions, processor = run_backtest_with_entries(
        gc_df=gc_df,
        dxy_df=dxy_df,
        timeframe=timeframe,
        market_state=market_state,
        htf_bias_func=htf_bias_func,
        log_signals=log_signals,
        log_dir=log_dir,
        processor=processor,  # Pass processor to reuse state
    )

    # Filter to only executed entries
    executed_entries = [e for e in executions if e.executed]
    logger.info(f"Processing {len(executed_entries)} executed entries")

    # Step 2: Create and simulate trades
    trades: list[Trade] = []
    invalidation_checker = InvalidationChecker()
    entry_timestamps = {entry.entry_timestamp for entry in executed_entries}
    entry_htf_bias_map = _compute_entry_htf_bias_map(
        gc_df=gc_df,
        dxy_df=dxy_df,
        timeframe=timeframe,
        htf_bias_func=htf_bias_func,
        target_timestamps=entry_timestamps,
    )

    for entry in executed_entries:
        # Get HTF bias for this entry
        entry_bias_obj = entry_htf_bias_map.get(entry.entry_timestamp)
        if entry_bias_obj is None:
            entry_bias_value = entry.signal.htf_bias
            if entry_timestamps:
                logger.warning(
                    "Missing HTF bias for entry timestamp %s; falling back to signal bias",
                    entry.entry_timestamp,
                )
        else:
            entry_bias_value = entry_bias_obj.bias

        # Extract structure candles from HTF bias
        bos_candle = entry_bias_obj.bos_candle if entry_bias_obj else None

        # For confirmation candle, use HTF-provided if available,
        # otherwise use entry candle
        if entry_bias_obj and entry_bias_obj.confirmation_candle:
            confirmation_candle = entry_bias_obj.confirmation_candle
        else:
            # Fallback: Use entry candle as confirmation
            entry_idx = gc_df.index.get_loc(entry.entry_timestamp)
            confirmation_candle_row = gc_df.iloc[entry_idx]

            from common.types import Candle

            confirmation_candle = Candle(
                timestamp=confirmation_candle_row.name,
                open=confirmation_candle_row["open"],
                high=confirmation_candle_row["high"],
                low=confirmation_candle_row["low"],
                close=confirmation_candle_row["close"],
                volume=confirmation_candle_row["volume"],
                symbol=entry.signal.symbol,
                timeframe=entry.signal.timeframe,
                source="BACKTEST",
            )

        # Get DXY alignment from HTF bias
        dxy_aligned = entry_bias_obj.dxy_alignment if entry_bias_obj else True

        # Sprint 3 Task 5: Extract VWAP value at entry for VWAP-zone SL
        vwap_value = None
        try:
            entry_idx = gc_df.index.get_loc(entry.entry_timestamp)
            # Compute features up to entry point to get VWAP
            gc_slice = gc_df.iloc[: entry_idx + 1]
            dxy_slice = (
                dxy_df.iloc[: entry_idx + 1] if len(dxy_df) >= entry_idx + 1 else dxy_df
            )
            features_df = processor._compute_features(gc_slice, dxy_slice)
            if len(features_df) > entry_idx and "vwap" in features_df.columns:
                vwap_value = features_df.iloc[entry_idx]["vwap"]
        except Exception as e:
            logger.debug(f"Failed to extract VWAP at entry: {e}")
            vwap_value = None

        trade = create_trade_from_entry(
            entry_execution=entry,
            confirmation_candle=confirmation_candle,
            bos_candle=bos_candle,
            risk_config=risk_config,
            market_context={
                "month": entry.entry_timestamp.month,
                "htf_aligned": _is_htf_aligned(
                    entry.signal.direction, entry_bias_value
                ),
                "dxy_aligned": dxy_aligned,
            },
            config=None,  # TODO: Add config parameter to enable MIN_RISK_TICKS validation
            vwap_value=vwap_value,
        )

        # Get future candles for simulation
        # Determine max bars based on setup type
        if trade.setup_type == "VWAP_FADE":
            max_bars = 10
        else:
            max_bars = 20

        future_candles = get_future_candles(gc_df, entry.entry_timestamp, max_bars)

        # Compute features for future candles (required for invalidation checks)
        # Without features, VWAP/HTF/DXY invalidations will be silently skipped
        future_features = None
        if not future_candles.empty:
            try:
                # Find entry index in gc_df
                entry_idx = gc_df.index.get_loc(entry.entry_timestamp)

                # Get data slice from start up to end of future candles
                end_idx = min(entry_idx + 1 + len(future_candles), len(gc_df))
                gc_slice = gc_df.iloc[:end_idx]
                dxy_slice = dxy_df.iloc[:end_idx] if len(dxy_df) >= end_idx else dxy_df

                # Compute features for the entire slice using processor
                # Note: This doesn't affect processor's validation state
                features_df = processor._compute_features(gc_slice, dxy_slice)

                # Extract only features for future candles (after entry)
                if len(features_df) > entry_idx + 1:
                    future_features_df = features_df.iloc[entry_idx + 1 :].copy()

                    # Set timestamp index if not already set
                    if "ts_event" in future_features_df.columns:
                        future_features_df = future_features_df.set_index("ts_event")
                    elif not isinstance(future_features_df.index, pd.DatetimeIndex):
                        # Use gc_slice timestamps for alignment
                        if len(gc_slice) > entry_idx + 1:
                            future_timestamps = gc_slice.index[entry_idx + 1 :]
                            future_features_df.index = future_timestamps[
                                : len(future_features_df)
                            ]

                    # Align with future_candles timestamps (handle any missing timestamps)
                    future_features = future_features_df.reindex(
                        future_candles.index, method=None
                    )

                    logger.debug(
                        f"Computed features for {len(future_features)} future candles "
                        f"(aligned with {len(future_candles)} candles)"
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to compute features for future candles: {e}. "
                    "Feature-based invalidations (VWAP/HTF/DXY) will be skipped."
                )
                future_features = None

        # Simulate trade outcome
        closed_trade = simulate_trade_outcome(
            trade=trade,
            future_candles=future_candles,
            invalidation_checker=invalidation_checker,
            config=config,
            future_features=future_features,
        )

        # Record trade outcome to update state in two places:
        # 1. InvalidationChecker: Updates daily_pnl, consecutive_losses for PDLL checks during trades
        # 2. Behavior Tracker: Updates loss streak guardrails before entry
        #
        # Outcome classification:
        # - won=True: pnl > 0 (actual profit)
        # - won=False: pnl < 0 (actual loss)
        # - won=None: pnl == 0 (breakeven, no capital lost)
        if closed_trade.pnl is None:
            won = None  # No PnL available (shouldn't happen, but handle gracefully)
        elif closed_trade.pnl > 0:
            won = True
        elif closed_trade.pnl < 0:
            won = False
        else:  # pnl == 0
            won = None  # Breakeven: no win, no loss

        # Update InvalidationChecker daily state (for PDLL checks during trade simulation)
        # CRITICAL: Pass close_timestamp to ensure session date is based on when
        # the trade closed, not when it opened (fixes multi-day trade attribution bug)
        invalidation_checker.record_trade_outcome(
            closed_trade, 
            won=won,
        )

        # Update behavior tracker (for loss streak guardrails before entry)
        if processor and processor.enable_validation:
            processor.record_trade_outcome(won)
            logger.debug(
                f"Recorded trade outcome: won={won}, "
                f"daily_pnl={invalidation_checker._daily_state['daily_pnl']:.2f}, "
                f"consecutive_losses={invalidation_checker._daily_state['consecutive_losses']}"
            )

        trades.append(closed_trade)

        logger.debug(
            f"Trade {closed_trade.trade_id} closed: {closed_trade.exit_reason} "
            f"(PnL={closed_trade.pnl:.2f}, R={closed_trade.r_realized:.2f})"
        )

    logger.info(
        f"Backtest with trades complete: {len(trades)} trades, "
        f"{len([t for t in trades if t.pnl and t.pnl > 0])} winners, "
        f"{len([t for t in trades if t.pnl and t.pnl < 0])} losers"
    )

    return trades


def run_backtest_with_entries_multi_tf(
    multi_tf_data: MultiTimeframeData,
    timeframe: str,
    market_state: dict,
    htf_approach: str = "streaming",
    log_signals: bool = False,
    log_dir: str | None = None,
    processor: BacktestProcessor | None = None,
) -> tuple[list[EntryExecution], BacktestProcessor]:
    """Run backtest with MultiTimeframeData for efficient HTF bias computation.

    This is the new interface that accepts MultiTimeframeData and automatically
    creates the HTF bias function with proper HTF feature computation.

    Args:
        multi_tf_data: Synchronized multi-timeframe data
        timeframe: Execution timeframe (e.g., "1m")
        market_state: Market context dict containing:
            - buffer_phase: Current capital phase ("startup", "growth", etc.)
            - tier_active: Active enforcer tier ("Conservative", "EarlyMild", etc.)
            - ceo_directive_active: Whether CEO directive is active (bool)
            - news_ok: Whether trading is allowed during news events (bool)
            - session_ok: Whether current session is valid for trading (bool)
        htf_approach: "streaming" (incremental) or "vectorized" (pre-computed)
                     for HTF feature computation (default: "streaming")
        log_signals: Whether to log signals to disk (default: False)
        log_dir: Directory for signal logs (required if log_signals=True)
        processor: Optional BacktestProcessor instance to reuse (for state persistence)

    Returns:
        Tuple of (list of EntryExecution objects, processor instance).
        EntryExecution list includes both successful entries (executed=True) and
        rejected entries (executed=False with rejection_reason).
        Processor instance is returned to allow recording trade outcomes.

    Example:
        >>> from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
        >>> sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
        >>> multi_tf_data = sync_layer.load(start, end)
        >>>
        >>> market_state = {
        ...     "buffer_phase": "growth",
        ...     "tier_active": "EarlyMild",
        ...     "ceo_directive_active": True,
        ...     "news_ok": True,
        ...     "session_ok": True,
        ... }
        >>>
        >>> executions, processor = run_backtest_with_entries_multi_tf(
        ...     multi_tf_data=multi_tf_data,
        ...     timeframe="1m",
        ...     market_state=market_state,
        ...     htf_approach="streaming",
        ... )
    """
    logger.info(
        f"Starting backtest with multi-timeframe sync: timeframe={timeframe}, "
        f"htf_approach={htf_approach}, tier={market_state.get('tier_active')}"
    )

    # Extract 1m DataFrames for BacktestProcessor
    gc_df, dxy_df = extract_execution_dataframes(multi_tf_data)

    if len(gc_df) == 0 or len(dxy_df) == 0:
        logger.warning("No execution data extracted from MultiTimeframeData")
        return [], processor or BacktestProcessor(timeframe=timeframe)

    # Create HTF bias function with sync layer
    htf_bias_func = create_htf_bias_func_with_sync_layer(
        multi_tf_data,
        approach=htf_approach,
    )

    # Call existing pipeline
    return run_backtest_with_entries(
        gc_df=gc_df,
        dxy_df=dxy_df,
        timeframe=timeframe,
        market_state=market_state,
        htf_bias_func=htf_bias_func,
        log_signals=log_signals,
        log_dir=log_dir,
        processor=processor,
    )


def run_backtest_with_trades_multi_tf(
    multi_tf_data: MultiTimeframeData,
    timeframe: str,
    market_state: dict,
    risk_config: dict,
    htf_approach: str = "streaming",
    config: dict | None = None,
    log_signals: bool = False,
    log_dir: str | None = None,
) -> list[Trade]:
    """Run complete backtest pipeline with trade simulation using MultiTimeframeData.

    This is the new interface that accepts MultiTimeframeData and automatically
    creates the HTF bias function with proper HTF feature computation.

    Args:
        multi_tf_data: Synchronized multi-timeframe data
        timeframe: Execution timeframe (e.g., "1m")
        market_state: Market context dict (buffer_phase, tier_active, etc.)
        risk_config: Risk configuration dict containing:
            - risk_per_trade: Dollar risk per trade
            - buffer_phase: Current capital phase
            - max_contracts: Maximum contracts allowed
        htf_approach: "streaming" (incremental) or "vectorized" (pre-computed)
                     for HTF feature computation (default: "streaming")
        config: Optional config dict for dollar PnL calculation
        log_signals: Whether to log signals to disk (default: False)
        log_dir: Directory for signal logs (required if log_signals=True)

    Returns:
        List of Trade objects (all closed with outcomes)

    Example:
        >>> from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
        >>> sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
        >>> multi_tf_data = sync_layer.load(start, end)
        >>>
        >>> risk_config = {
        ...     "risk_per_trade": 350.0,
        ...     "buffer_phase": "startup",
        ...     "max_contracts": 1,
        ... }
        >>>
        >>> trades = run_backtest_with_trades_multi_tf(
        ...     multi_tf_data=multi_tf_data,
        ...     timeframe="1m",
        ...     market_state=market_state,
        ...     risk_config=risk_config,
        ...     htf_approach="vectorized",
        ... )
    """
    logger.info(
        f"Starting backtest with trades (multi-timeframe): timeframe={timeframe}, "
        f"htf_approach={htf_approach}, tier={market_state.get('tier_active')}"
    )

    # Extract 1m DataFrames
    gc_df, dxy_df = extract_execution_dataframes(multi_tf_data)

    if len(gc_df) == 0 or len(dxy_df) == 0:
        logger.warning("No execution data extracted from MultiTimeframeData")
        return []

    # Create HTF bias function with sync layer
    htf_bias_func = create_htf_bias_func_with_sync_layer(
        multi_tf_data,
        approach=htf_approach,
    )

    # Call existing pipeline
    return run_backtest_with_trades(
        gc_df=gc_df,
        dxy_df=dxy_df,
        timeframe=timeframe,
        market_state=market_state,
        htf_bias_func=htf_bias_func,
        risk_config=risk_config,
        config=config,
        log_signals=log_signals,
        log_dir=log_dir,
    )
