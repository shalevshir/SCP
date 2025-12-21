"""Trade outcome simulator - determines TP/SL/timeout exits.

This module simulates trade outcomes by processing future candles to determine
which exit condition is met first: Take Profit, Stop Loss, Timeout, or Invalidation.

Following Shir Capital SOP requirements:
- SL takes priority over TP within same candle
- Gaps are handled realistically (exit at limit, not worse)
- Timeout logic: 20 bars for continuation, 10 bars for fade
- Invalidation checks exit at next candle open

Key Features:
- Realistic intra-candle order-of-operations
- Gap handling (don't exit worse than SL/TP)
- Setup-specific timeout logic
- Full auditability with exit reasons
- Edge case handling (NaN, zero risk, invalid trades)
"""

import math

import pandas as pd
from common.logger import get_logger
from common.types import Candle

from backtester.trade import Trade, close_trade, is_fade, is_reclaim, is_continuation

logger = get_logger(__name__)

# PATCH PART 2: Grace period constants removed in favor of inline setup-specific logic
# Old constants MIN_BARS_RECLAIM, MIN_BARS_CONTINUATION, MIN_BARS_FADE removed

# Sprint 3 Task 6: Extended grace period for VWAP_RECLAIM
# Allows VWAP reclaim to retest and accept without premature stop-out
ACCEPTANCE_GRACE_BARS_RECLAIM = 8

# SOP timeout limits - import from invalidations.py as single source of truth
from backtester.invalidations import R1_TIME_LIMITS as TIMEOUT_BARS


def is_valid_candle(candle: Candle) -> bool:
    """Check if candle has valid OHLC data.

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


def is_valid_trade(trade: Trade) -> bool:
    """Check if trade has valid SL/TP levels.

    Args:
        trade: Trade to validate

    Returns:
        True if trade is valid, False if it has zero risk or invalid levels
    """
    # Check for zero risk (entry == SL)
    if abs(trade.entry_price - trade.stop_loss) < 1e-10:
        logger.warning(
            f"Trade {trade.trade_id} has zero risk distance "
            f"(entry={trade.entry_price}, SL={trade.stop_loss})"
        )
        return False

    # Check for NaN/Inf in critical fields
    critical_values = [
        trade.entry_price,
        trade.stop_loss,
        trade.take_profit,
        trade.risk_amount,
    ]
    for val in critical_values:
        if math.isnan(val) or math.isinf(val):
            logger.warning(f"Trade {trade.trade_id} has NaN or Inf in critical fields")
            return False

    return True


def check_tp_hit(trade: Trade, candle: Candle) -> bool:
    """Check if take profit is hit within candle.

    Args:
        trade: Open trade with TP level
        candle: Candle to check

    Returns:
        True if TP is hit, False otherwise

    Logic:
        - Long: TP hit if candle.high >= trade.take_profit
        - Short: TP hit if candle.low <= trade.take_profit
    """
    if trade.direction == "long":
        return candle.high >= trade.take_profit
    else:  # short
        return candle.low <= trade.take_profit


def check_sl_hit(trade: Trade, candle: Candle, use_close: bool = False) -> bool:
    """Check if stop loss is hit within candle.

    Args:
        trade: Open trade with SL level
        candle: Candle to check
        use_close: If True, use close-based SL (for FADE bar 1 protection)

    Returns:
        True if SL is hit, False otherwise

    Logic:
        - use_close=True: Close-based (tolerant - for FADE bar 1)
          * Long: SL hit if candle.close <= trade.stop_loss
          * Short: SL hit if candle.close >= trade.stop_loss
        - use_close=False (default): Wick-based (strict)
          * Long: SL hit if candle.low <= trade.stop_loss
          * Short: SL hit if candle.high >= trade.stop_loss
    """
    if use_close:
        # CLOSE-BASED (tolerant - for FADE bar 1)
        if trade.direction == "long":
            return candle.close <= trade.stop_loss
        else:
            return candle.close >= trade.stop_loss

    # WICK-BASED (strict - default)
    if trade.direction == "long":
        return candle.low <= trade.stop_loss
    else:  # short
        return candle.high >= trade.stop_loss


def check_timeout(bars_elapsed: int, setup_type: str) -> bool:
    """Check if maximum time in trade is exceeded.

    Args:
        bars_elapsed: Number of bars since entry
        setup_type: Setup type (determines max bars)

    Returns:
        True if timeout reached, False otherwise

    SOP Rules:
        - Continuation (VWAP_RECLAIM, DXY_CONTINUATION): 20 bars
        - Fade (VWAP_FADE): 10 bars
    """
    max_bars = TIMEOUT_BARS.get(setup_type, 20)  # Default to 20 if unknown
    return bars_elapsed >= max_bars


def check_trade_exit_single_bar(
    trade: Trade,
    candle: Candle,
    bars_elapsed: int,
    invalidation_checker=None,
    config: dict | None = None,
    candle_features: dict | None = None,
) -> Trade:
    """Check if trade should exit on this single candle (single-bar approach).

    This function checks a single candle against an active trade to determine
    if any exit condition is met. Unlike simulate_trade_outcome(), this checks
    only one bar at a time, making it suitable for incremental processing that
    matches live trading behavior.

    Args:
        trade: Open trade to check
        candle: Current candle to check against trade
        bars_elapsed: Number of bars elapsed since entry (externally tracked)
        invalidation_checker: Optional InvalidationChecker for early exits
        config: Optional config dict for dollar PnL calculation
        candle_features: Optional dict with features for current candle

    Returns:
        Trade object - either closed (if exit hit) or original trade (if still open)

    Exit Priority (checked in order per SOP):
        1. Stop Loss → exit at SL price
        2. Take Profit → exit at TP price
        3. Invalidations (VWAP, HTF, DXY, Session, Window) → exit at candle open
        4. Timeout (max bars) → exit at candle close

    Grace Periods (setup-specific):
        - CONTINUATION: 6 bars for both SL/TP and invalidations
        - RECLAIM: 2 bars for both SL/TP and invalidations
        - FADE: 0 bars for SL/TP (immediate), 3 bars for invalidations only
    """
    # Validate trade
    if not is_valid_trade(trade):
        logger.error(
            f"Trade {trade.trade_id} is invalid (zero risk or NaN values). "
            "Closing at entry with INVALID_SETUP."
        )
        exit_candle = Candle(
            timestamp=trade.entry_timestamp,
            open=trade.entry_price,
            high=trade.entry_price,
            low=trade.entry_price,
            close=trade.entry_price,
            volume=0,
            symbol=trade.symbol,
            timeframe=trade.timeframe,
            source="SIMULATION",
        )
        return close_trade(trade, exit_candle, "invalid_setup", config)

    # Check if trade is already closed
    if trade.status != "OPEN":
        logger.debug(
            f"Trade {trade.trade_id} is already closed (status={trade.status}). "
            "Returning unchanged."
        )
        return trade

    # Validate candle data - skip invalid candles (return trade as-is)
    if not is_valid_candle(candle):
        logger.warning(
            f"Skipping candle with NaN/Inf values at {candle.timestamp} "
            f"for trade {trade.trade_id}"
        )
        return trade

    # Setup-specific grace periods
    skip_sl_tp = False
    skip_invalidations = False

    if is_continuation(trade):
        # CONTINUATION: skip both SL/TP and invalidations for first 6 bars
        skip_sl_tp = bars_elapsed <= 6
        skip_invalidations = bars_elapsed <= 6
        if skip_sl_tp:
            logger.debug(
                f"Trade {trade.trade_id}: CONTINUATION grace period active "
                f"(bar {bars_elapsed}/6) - skipping SL/TP and invalidations"
            )
    elif is_fade(trade):
        # FADE: NEVER skip SL/TP (allow TP hits and close-based SL on bar 1)
        # But skip invalidations for 3 bars
        skip_sl_tp = False
        skip_invalidations = bars_elapsed <= 3
        if skip_invalidations:
            logger.debug(
                f"Trade {trade.trade_id}: FADE invalidation grace active "
                f"(bar {bars_elapsed}/3) - SL/TP allowed, invalidations skipped"
            )
    elif is_reclaim(trade):
        # RECLAIM: Skip SL/TP for first 8 bars, skip invalidations for 8 bars
        # Sprint 3 Task 6: Extended grace period to allow VWAP retest/acceptance
        skip_sl_tp = bars_elapsed <= ACCEPTANCE_GRACE_BARS_RECLAIM
        skip_invalidations = bars_elapsed <= ACCEPTANCE_GRACE_BARS_RECLAIM
        if skip_sl_tp:
            logger.debug(
                f"Trade {trade.trade_id}: RECLAIM grace period active "
                f"(bar {bars_elapsed}/{ACCEPTANCE_GRACE_BARS_RECLAIM}) - skipping SL/TP and invalidations"
            )

    # Exit Priority Order (per SOP):
    # 1. Stop Loss (highest priority)
    if not skip_sl_tp:
        # FADE bar 1: use close-based SL for volatility protection
        use_close_sl = is_fade(trade) and bars_elapsed == 1
        if use_close_sl:
            logger.debug(f"Trade {trade.trade_id}: FADE bar 1 - using close-based SL")

        if check_sl_hit(trade, candle, use_close=use_close_sl):
            logger.info(
                f"Trade {trade.trade_id} hit SL at {trade.stop_loss} "
                f"(bars={bars_elapsed}, close_based={use_close_sl})"
            )
            return close_trade(trade, candle, "sl", config)

    # 2. Take Profit
    if not skip_sl_tp and check_tp_hit(trade, candle):
        logger.info(
            f"Trade {trade.trade_id} hit TP at {trade.take_profit} "
            f"(bars={bars_elapsed})"
        )
        return close_trade(trade, candle, "tp", config)

    # 3. Invalidation checks (VWAP, HTF, DXY, Session, Window)
    if not skip_invalidations and invalidation_checker is not None:
        is_invalid, reason = invalidation_checker.check_all(
            trade, candle, bars_elapsed, features=candle_features
        )
        if is_invalid:
            # Map reason to exit code
            # FIXED: Order matters - check specific patterns before generic ones
            exit_reason = "invalidation"  # Default
            reason_lower = reason.lower()
            if "+1r" in reason_lower or "timeout" in reason_lower or "not reached" in reason_lower:
                # Time-based exit (must check before "vwap" since reason contains setup type)
                exit_reason = "time_stop"
            elif "dxy" in reason_lower:
                # DXY flip (must check before "structure" since DXY reasons may contain "structure")
                exit_reason = "dxy_flip"
            elif "micro structure" in reason_lower or "micro_structure" in reason_lower:
                # Micro (1m) structure break - separate from true HTF
                exit_reason = "micro_structure_invalidation"
            elif "vwap" in reason_lower:
                exit_reason = "vwap_invalidation"
            elif "htf" in reason_lower:
                # Reserved for actual HTF (15m/1h) structure breaks
                exit_reason = "htf_invalidation"
            elif "session" in reason_lower:
                exit_reason = "session_close"
            elif "window" in reason_lower:
                exit_reason = "window_expired"
            elif "daily" in reason_lower or "risk" in reason_lower:
                exit_reason = "daily_risk_stop"

            logger.info(
                f"Trade {trade.trade_id} invalidated: {reason} "
                f"(bars={bars_elapsed}, exit_reason={exit_reason})"
            )
            return close_trade(trade, candle, exit_reason, config)

    # 4. Timeout (only if no other exit occurred)
    if check_timeout(bars_elapsed, trade.setup_type):
        logger.info(f"Trade {trade.trade_id} timed out after {bars_elapsed} bars")
        return close_trade(trade, candle, "timeout", config)

    # No exit condition met - trade stays open
    return trade


def simulate_trade_outcome(
    trade: Trade,
    future_candles: pd.DataFrame,
    invalidation_checker=None,
    config: dict | None = None,
    future_features: pd.DataFrame | None = None,
) -> Trade:
    """Simulate trade outcome by processing future candles.

    Determines which exit condition is met first: TP, SL, invalidation, timeout,
    or end of data. Returns a closed Trade with appropriate exit details.

    Args:
        trade: Open trade to simulate
        future_candles: DataFrame with candles after entry (DatetimeIndex)
        invalidation_checker: Optional InvalidationChecker for early exits
        config: Optional config dict for dollar PnL calculation
        future_features: Optional DataFrame with features for future candles (DatetimeIndex)

    Returns:
        Closed Trade with exit_reason, exit_price, and PnL

    Exit Priority (checked in order for each candle per SOP):
        1. Stop Loss → exit at SL price
        2. Take Profit → exit at TP price
        3. VWAP invalidation → exit at candle open
        4. HTF invalidation → exit at candle open
        5. DXY flip → exit at candle open
        6. Session end → exit at candle open
        7. Setup window expiration → exit at candle open
        8. Timeout (max bars) → exit at candle close
        9. End of data → exit at last candle close

    SOP Rules:
        - SL takes priority over TP within same candle
        - Gaps: exit at limit price (SL/TP), not worse
        - Timeout: 20 bars (continuation), 10 bars (fade)
    """
    # Validate trade
    if not is_valid_trade(trade):
        logger.error(
            f"Trade {trade.trade_id} is invalid (zero risk or NaN values). "
            "Closing at entry with INVALID_SETUP."
        )
        exit_candle = Candle(
            timestamp=trade.entry_timestamp,
            open=trade.entry_price,
            high=trade.entry_price,
            low=trade.entry_price,
            close=trade.entry_price,
            volume=0,
            symbol=trade.symbol,
            timeframe=trade.timeframe,
            source="SIMULATION",
        )
        return close_trade(trade, exit_candle, "invalid_setup", config)

    # Check if trade is already closed
    if trade.status != "OPEN":
        logger.warning(
            f"Trade {trade.trade_id} is already closed (status={trade.status}). "
            "Returning unchanged."
        )
        return trade

    # Validate future_candles
    if future_candles.empty:
        logger.warning(
            f"No future candles for trade {trade.trade_id}. "
            "Closing at entry price with END_OF_DATA."
        )
        # Create dummy candle at entry to close trade
        exit_candle = Candle(
            timestamp=trade.entry_timestamp,
            open=trade.entry_price,
            high=trade.entry_price,
            low=trade.entry_price,
            close=trade.entry_price,
            volume=0,
            symbol=trade.symbol,
            timeframe=trade.timeframe,
            source="SIMULATION",
        )
        return close_trade(trade, exit_candle, "end_of_data", config)

    bars_elapsed = 0

    # FIX #2: Track retest protection for VWAP_RECLAIM
    # If trade has retest protection enabled, we skip SL check on first bar
    retest_protection_active = trade.ignore_first_retest_bar

    # Iterate through future candles
    for timestamp, row in future_candles.iterrows():
        # Reconstruct Candle from DataFrame row
        candle = Candle(
            timestamp=timestamp,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            symbol=trade.symbol,
            timeframe=trade.timeframe,
            source="SIMULATION",
        )

        # Validate candle data - skip invalid candles (don't count toward timeout)
        if not is_valid_candle(candle):
            logger.warning(
                f"Skipping candle with NaN/Inf values at {timestamp} "
                f"for trade {trade.trade_id}"
            )
            continue

        # Only increment bars_elapsed for valid candles
        # SOP timeout rules apply to valid candles only
        bars_elapsed += 1

        # Log rejection-candle diagnostics during trade lifetime (per-bar tracking)
        from backtester.diagnostics import add_nested_diag

        # Extract features for this candle if available
        candle_features = None
        if future_features is not None and timestamp in future_features.index:
            feature_row = future_features.loc[timestamp]
            # Convert to dict if it's a Series
            if isinstance(feature_row, pd.Series):
                candle_features = feature_row.to_dict()
            elif isinstance(feature_row, dict):
                candle_features = feature_row
            else:
                # Try to convert to dict
                candle_features = (
                    dict(feature_row) if hasattr(feature_row, "__iter__") else None
                )

        # Add per-bar rejection diagnostics if features available
        if candle_features is not None:
            key = f"bar_{bars_elapsed}"
            add_nested_diag(
                trade,
                "rejection_during_trade",
                key,
                {
                    "upper_wick_pct": candle_features.get("upper_wick_pct"),
                    "lower_wick_pct": candle_features.get("lower_wick_pct"),
                    "close_vwap_diff": candle_features.get("close_vwap_diff"),
                    "close_vwap_pct": candle_features.get("close_vwap_pct"),
                    "direction_valid": candle_features.get("rejection_direction_valid"),
                },
            )

        # PATCH PART 2: Setup-specific grace periods with separate SL/TP and invalidation flags
        # This prevents contamination: FADE shouldn't skip SL/TP, but should skip early invalidations
        skip_sl_tp = False
        skip_invalidations = False

        if is_continuation(trade):
            # CONTINUATION: skip both SL/TP and invalidations for first 6 bars (strict protection)
            skip_sl_tp = bars_elapsed <= 6
            skip_invalidations = bars_elapsed <= 6
            if skip_sl_tp:
                logger.debug(
                    f"Trade {trade.trade_id}: CONTINUATION grace period active "
                    f"(bar {bars_elapsed}/6) - skipping SL/TP and invalidations"
                )
        elif is_fade(trade):
            # FADE: NEVER skip SL/TP (allow TP hits and close-based SL on bar 1)
            # But skip invalidations for 3 bars (grace period for invalidations only)
            # This allows multi-candle duration while still honoring TP targets and SL checks
            skip_sl_tp = False
            skip_invalidations = bars_elapsed <= 3
            if skip_invalidations:
                logger.debug(
                    f"Trade {trade.trade_id}: FADE invalidation grace active "
                    f"(bar {bars_elapsed}/3) - SL/TP allowed, invalidations skipped"
                )
        elif is_reclaim(trade):
            # RECLAIM: Skip SL/TP for first 8 bars (grace period), skip invalidations for 8 bars (allow retest)
            # Bug Fix: Use ACCEPTANCE_GRACE_BARS_RECLAIM constant for consistency
            skip_sl_tp = bars_elapsed <= ACCEPTANCE_GRACE_BARS_RECLAIM
            skip_invalidations = bars_elapsed <= ACCEPTANCE_GRACE_BARS_RECLAIM
            if skip_sl_tp:
                logger.debug(
                    f"Trade {trade.trade_id}: RECLAIM grace period active "
                    f"(bar {bars_elapsed}/{ACCEPTANCE_GRACE_BARS_RECLAIM}) - skipping SL/TP and invalidations"
                )

        # Exit Priority Order (per SOP):
        # 1. Stop Loss (highest priority)
        # PATCH PART 2: Use skip_sl_tp flag for grace period
        # Note: retest_protection_active is now handled by skip_sl_tp for RECLAIM
        if skip_sl_tp:
            # Grace period: skip SL check
            pass
        else:
            # FADE bar 1: use close-based SL for volatility protection
            use_close_sl = is_fade(trade) and bars_elapsed == 1
            if use_close_sl:
                logger.debug(
                    f"Trade {trade.trade_id}: FADE bar 1 - using close-based SL"
                )

            if check_sl_hit(trade, candle, use_close=use_close_sl):
                # Add SL hit diagnostics before closing
                from backtester.diagnostics import add_nested_diag

                add_nested_diag(trade, "sl_hit_context", "sl_level", trade.stop_loss)
                add_nested_diag(trade, "sl_hit_context", "candle_low", candle.low)
                add_nested_diag(trade, "sl_hit_context", "candle_high", candle.high)
                add_nested_diag(trade, "sl_hit_context", "candle_close", candle.close)
                add_nested_diag(trade, "sl_hit_context", "bars_elapsed", bars_elapsed)
                add_nested_diag(
                    trade, "sl_hit_context", "used_close_based_sl", use_close_sl
                )

                # ATR at SL hit (if features are passed in this scope)
                if candle_features is not None:
                    add_nested_diag(
                        trade, "sl_hit_context", "atr_5", candle_features.get("atr_5")
                    )

                logger.info(
                    f"Trade {trade.trade_id} hit SL at {trade.stop_loss} "
                    f"(bars={bars_elapsed}, close_based={use_close_sl})"
                )
                return close_trade(trade, candle, "sl", config)

        # 2. Take Profit
        # PATCH PART 2: Use skip_sl_tp flag for grace period
        if not skip_sl_tp and check_tp_hit(trade, candle):
            # Add TP hit diagnostics before closing
            from backtester.diagnostics import add_nested_diag

            add_nested_diag(trade, "tp_hit_context", "tp_level", trade.take_profit)
            add_nested_diag(trade, "tp_hit_context", "candle_high", candle.high)
            add_nested_diag(trade, "tp_hit_context", "candle_low", candle.low)
            add_nested_diag(trade, "tp_hit_context", "candle_close", candle.close)
            add_nested_diag(trade, "tp_hit_context", "bars_elapsed", bars_elapsed)

            logger.info(
                f"Trade {trade.trade_id} hit TP at {trade.take_profit} "
                f"(bars={bars_elapsed})"
            )
            return close_trade(trade, candle, "tp", config)

        # 3-7. Invalidation checks (VWAP, HTF, DXY, Session, Window)
        # PATCH PART 2: Use skip_invalidations flag (separate from SL/TP)
        if not skip_invalidations and invalidation_checker is not None:
            is_invalid, reason = invalidation_checker.check_all(
                trade, candle, bars_elapsed, features=candle_features
            )
            if is_invalid:
                # Map reason to exit code
                # FIXED: Order matters - check specific patterns before generic ones
                exit_reason = "invalidation"  # Default
                reason_lower = reason.lower()
                if "+1r" in reason_lower or "timeout" in reason_lower or "not reached" in reason_lower:
                    # Time-based exit (must check before "vwap" since reason contains setup type)
                    exit_reason = "time_stop"
                elif "dxy" in reason_lower:
                    # DXY flip (must check before "structure" since DXY reasons may contain "structure")
                    exit_reason = "dxy_flip"
                elif "micro structure" in reason_lower or "micro_structure" in reason_lower:
                    # Micro (1m) structure break - separate from true HTF
                    exit_reason = "micro_structure_invalidation"
                elif "vwap" in reason_lower:
                    exit_reason = "vwap_invalidation"
                elif "htf" in reason_lower:
                    # Reserved for actual HTF (15m/1h) structure breaks
                    exit_reason = "htf_invalidation"
                elif "session" in reason_lower:
                    exit_reason = "session_close"
                elif "window" in reason_lower:
                    exit_reason = "window_expired"
                elif "daily" in reason_lower or "risk" in reason_lower:
                    exit_reason = "daily_risk_stop"

                logger.info(
                    f"Trade {trade.trade_id} invalidated: {reason} "
                    f"(bars={bars_elapsed}, exit_reason={exit_reason})"
                )
                return close_trade(trade, candle, exit_reason, config)

        # 8. Timeout (only if no other exit occurred)
        if check_timeout(bars_elapsed, trade.setup_type):
            logger.info(f"Trade {trade.trade_id} timed out after {bars_elapsed} bars")
            return close_trade(trade, candle, "timeout", config)

    # 5. End of data - close at last candle
    last_candle = Candle(
        timestamp=future_candles.index[-1],
        open=future_candles.iloc[-1]["open"],
        high=future_candles.iloc[-1]["high"],
        low=future_candles.iloc[-1]["low"],
        close=future_candles.iloc[-1]["close"],
        volume=future_candles.iloc[-1]["volume"],
        symbol=trade.symbol,
        timeframe=trade.timeframe,
        source="SIMULATION",
    )

    logger.info(f"Trade {trade.trade_id} reached end of data after {bars_elapsed} bars")
    return close_trade(trade, last_candle, "end_of_data", config)
