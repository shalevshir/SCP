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

from backtester.trade import Trade, close_trade

logger = get_logger(__name__)

# SOP timeout limits per setup type
TIMEOUT_BARS = {
    "VWAP_RECLAIM": 20,
    "DXY_CONTINUATION": 20,
    "VWAP_FADE": 10,
}


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
            logger.warning(
                f"Trade {trade.trade_id} has NaN or Inf in critical fields"
            )
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


def check_sl_hit(trade: Trade, candle: Candle) -> bool:
    """Check if stop loss is hit within candle.

    Args:
        trade: Open trade with SL level
        candle: Candle to check

    Returns:
        True if SL is hit, False otherwise

    Logic:
        - Long: SL hit if candle.low <= trade.stop_loss
        - Short: SL hit if candle.high >= trade.stop_loss
    """
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


def simulate_trade_outcome(
    trade: Trade,
    future_candles: pd.DataFrame,
    invalidation_checker=None,
    config: dict | None = None,
) -> Trade:
    """Simulate trade outcome by processing future candles.

    Determines which exit condition is met first: TP, SL, invalidation, timeout,
    or end of data. Returns a closed Trade with appropriate exit details.

    Args:
        trade: Open trade to simulate
        future_candles: DataFrame with candles after entry (DatetimeIndex)
        invalidation_checker: Optional InvalidationChecker for early exits
        config: Optional config dict for dollar PnL calculation

    Returns:
        Closed Trade with exit_reason, exit_price, and PnL

    Exit Priority (checked in order for each candle):
        1. Invalidation (if checker provided) → exit at candle open
        2. Stop Loss → exit at SL price
        3. Take Profit → exit at TP price
        4. Timeout (max bars) → exit at candle close
        5. End of data → exit at last candle close

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
        return close_trade(trade, exit_candle, "INVALID_SETUP", config)

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
        return close_trade(trade, exit_candle, "END_OF_DATA", config)

    bars_elapsed = 0

    # Iterate through future candles
    for timestamp, row in future_candles.iterrows():
        bars_elapsed += 1

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

        # Validate candle data
        if not is_valid_candle(candle):
            logger.warning(
                f"Skipping candle with NaN/Inf values at {timestamp} "
                f"for trade {trade.trade_id}"
            )
            continue

        # 1. Check for invalidation (exit at open)
        if invalidation_checker is not None:
            is_invalid, reason = invalidation_checker.check_all(
                trade, candle, bars_elapsed
            )
            if is_invalid:
                logger.info(
                    f"Trade {trade.trade_id} invalidated: {reason} "
                    f"(bars={bars_elapsed})"
                )
                return close_trade(trade, candle, "INVALIDATION", config)

        # 2. Check for SL hit (priority over TP per SOP)
        if check_sl_hit(trade, candle):
            logger.info(
                f"Trade {trade.trade_id} hit SL at {trade.stop_loss} "
                f"(bars={bars_elapsed})"
            )
            return close_trade(trade, candle, "SL", config)

        # 3. Check for TP hit
        if check_tp_hit(trade, candle):
            logger.info(
                f"Trade {trade.trade_id} hit TP at {trade.take_profit} "
                f"(bars={bars_elapsed})"
            )
            return close_trade(trade, candle, "TP", config)

        # 4. Check for timeout
        if check_timeout(bars_elapsed, trade.setup_type):
            logger.info(
                f"Trade {trade.trade_id} timed out after {bars_elapsed} bars"
            )
            return close_trade(trade, candle, "TIME", config)

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

    logger.info(
        f"Trade {trade.trade_id} reached end of data after {bars_elapsed} bars"
    )
    return close_trade(trade, last_candle, "END_OF_DATA", config)

