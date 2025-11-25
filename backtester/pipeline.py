"""Backtesting pipeline orchestration.

Integrates feature generation, scoring, validation, and entry execution.

This module provides the complete backtesting pipeline that orchestrates:
1. Feature generation (BacktestProcessor)
2. HTF bias computation (caller-provided)
3. Signal scoring (RuleEngine)
4. Signal validation (ValidationEngine)
5. Entry execution (EntryModel)
"""

from collections.abc import Callable

import pandas as pd
from common.logger import get_logger
from feature_engine.backtesting import BacktestProcessor
from feature_engine.integration import process_features_with_validation
from rule_engine.htf.types import HTFBias

from backtester.entry_model import EntryExecution, execute_entry_at_next_open

logger = get_logger(__name__)


def run_backtest_with_entries(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    market_state: dict,
    htf_bias_func: Callable[[pd.Series, dict], HTFBias],
    log_signals: bool = False,
    log_dir: str | None = None,
) -> list[EntryExecution]:
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

    Returns:
        List of EntryExecution objects, one per signal generated.
        Includes both successful entries (executed=True) and rejected entries
        (executed=False with rejection_reason).

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
        >>> executions = run_backtest_with_entries(
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

    # Initialize processor
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

    return executions
