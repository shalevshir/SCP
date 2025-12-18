"""Trade dataclass - complete trade lifecycle with SOP-compliant SL/TP.

This module implements the Trade object that represents a complete trade from
entry to exit, with stop loss and take profit calculations based on Shir Capital
SOP requirements.

Key Features:
- Structure-based stop loss placement (never inside liquidity)
- SOP-compliant R-multiple targets (2R/3R based on setup and seasonality)
- Immutable trade records for auditability
- JSON serialization for logging and analysis
- Full PnL and metrics tracking
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
import math
from typing import Any
from uuid import uuid4

import pandas as pd

from common.logger import get_logger
from common.types import Candle

from backtester.entry_model import EntryExecution

logger = get_logger(__name__)

# Minimum risk threshold in ticks to prevent micro-chop entries
# Trades with risk below this threshold are rejected to avoid noise
MIN_RISK_TICKS = 10

# Minimum stop-loss distance for VWAP_RECLAIM setups (SOP requirement)
# VWAP_RECLAIM requires retest protection, so SL must be far enough
# from entry to avoid premature stop-out during the retest phase
# Requirement: 20 ticks minimum for VWAP_RECLAIM
MIN_SL_TICKS_VWAP_RECLAIM = 20

# Sprint 3 Task 5: VWAP-zone SL buffer for VWAP_RECLAIM
# Conservative buffer below/above VWAP for long/short trades
# Allows normal retest behavior without premature stop-out
VWAP_SL_BUFFER_TICKS = 30

# Minimum stop-loss distance for DXY_CONTINUATION setups
# Continuation trades need structural breathing room to avoid micro-swing noise
# PATCH PART 4: Updated from 15 to 25 ticks per patch specification
MIN_SL_TICKS_DXY_CONTINUATION = 25

# Minimum stop-loss distance for VWAP_FADE setups
# Fade setups need sufficient SL distance to avoid instant stop-out from micro-chop
MIN_SL_TICKS_VWAP_FADE = 15


# PATCH PART 1: Setup-specific helper functions for clean isolation
def is_fade(trade: "Trade") -> bool:
    """Check if trade is a VWAP_FADE setup.

    Args:
        trade: Trade object to check

    Returns:
        True if setup_type is VWAP_FADE, False otherwise
    """
    return trade.setup_type == "VWAP_FADE"


def is_reclaim(trade: "Trade") -> bool:
    """Check if trade is a VWAP_RECLAIM setup.

    Args:
        trade: Trade object to check

    Returns:
        True if setup_type is VWAP_RECLAIM, False otherwise
    """
    return trade.setup_type == "VWAP_RECLAIM"


def is_continuation(trade: "Trade") -> bool:
    """Check if trade is a DXY_CONTINUATION setup.

    Args:
        trade: Trade object to check

    Returns:
        True if setup_type is DXY_CONTINUATION, False otherwise
    """
    return trade.setup_type == "DXY_CONTINUATION"


def validate_trade_invariants(
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    direction: str,
    risk_amount: float,
    reward_amount: float,
) -> None:
    """Validate trade invariants before trade creation (FIX #3/#8).

    Ensures that:
    - SL != entry_price
    - TP != entry_price
    - TP is on correct side of entry (long: TP > entry, short: TP < entry)
    - SL is on correct side of entry (long: SL < entry, short: SL > entry)
    - risk_amount > 0
    - reward_amount > 0

    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price
        direction: Trade direction ("long" or "short")
        risk_amount: Risk amount (distance from entry to SL)
        reward_amount: Reward amount (distance from entry to TP)

    Raises:
        ValueError: If any invariant is violated
    """
    # Check SL != entry
    if stop_loss == entry_price:
        raise ValueError(
            f"Invalid trade: stop_loss cannot equal entry_price. "
            f"SL={stop_loss}, entry={entry_price}"
        )

    # Check TP != entry
    if take_profit == entry_price:
        raise ValueError(
            f"Invalid trade: take_profit cannot equal entry_price. "
            f"TP={take_profit}, entry={entry_price}"
        )

    # Check SL is on correct side of entry
    if direction == "long":
        if stop_loss >= entry_price:
            raise ValueError(
                f"Invalid long trade: stop_loss must be below entry_price. "
                f"SL={stop_loss}, entry={entry_price}"
            )
    else:  # short
        if stop_loss <= entry_price:
            raise ValueError(
                f"Invalid short trade: stop_loss must be above entry_price. "
                f"SL={stop_loss}, entry={entry_price}"
            )

    # Check TP is on correct side of entry
    if direction == "long":
        if take_profit <= entry_price:
            raise ValueError(
                f"Invalid long trade: take_profit must be above entry_price. "
                f"TP={take_profit}, entry={entry_price}"
            )
    else:  # short
        if take_profit >= entry_price:
            raise ValueError(
                f"Invalid short trade: take_profit must be below entry_price. "
                f"TP={take_profit}, entry={entry_price}"
            )

    # Check risk_amount > 0
    if risk_amount <= 0:
        raise ValueError(
            f"Invalid trade: risk_amount must be positive. "
            f"risk={risk_amount}, SL={stop_loss}, entry={entry_price}"
        )

    # Check reward_amount > 0
    if reward_amount <= 0:
        raise ValueError(
            f"Invalid trade: reward_amount must be positive. "
            f"reward={reward_amount}, TP={take_profit}, entry={entry_price}"
        )

    logger.debug(
        f"Trade invariants validated: SL={stop_loss}, entry={entry_price}, "
        f"TP={take_profit}, risk={risk_amount}, reward={reward_amount}"
    )


@dataclass(frozen=True)
class Trade:
    """Complete trade lifecycle with SOP-compliant SL/TP.

    Represents a complete trade from entry to exit, including stop loss (SL),
    take profit (TP), risk/reward calculations, and PnL tracking. Immutable
    for auditability.

    Attributes:
        trade_id: Unique identifier (UUID string)
        symbol: Asset symbol (e.g., "GC", "DXY")
        timeframe: Candle period (e.g., "1m", "5m", "15m")

        entry_execution: Complete entry context (EntryExecution object)
        entry_timestamp: Entry timestamp (from EntryExecution)
        entry_price: Executed entry price
        direction: Trade direction ("long" or "short")
        setup_type: Setup classification (e.g., "VWAP_RECLAIM", "VWAP_FADE")

        stop_loss: Stop loss price (structure-based)
        take_profit: Take profit price (R-multiple based)
        sl_rationale: Explanation of SL placement
        tp_rationale: Explanation of TP calculation (R-multiple, seasonality)

        risk_amount: Risk in points (not dollars)
        reward_amount: Reward in points (not dollars)
        r_multiple: R:R ratio (2.0, 3.0, etc.)
        contracts: Number of contracts

        exit_timestamp: Exit timestamp (None if open)
        exit_price: Exit price (None if open)
        exit_reason: Exit reason ("TP", "SL", "TIME", "INVALIDATION", None if open)

        pnl: Realized PnL in points (None if open)
        pnl_percent: PnL as % of risk (None if open)
        r_realized: Actual R achieved (None if open)

        pnl_dollars: Gross PnL in dollars before costs (None if open)
        pnl_net: Net PnL in dollars after slippage + commission (None if open)
        slippage_cost: Slippage cost in dollars (None if open)
        commission_cost: Commission cost in dollars (None if open)

        status: Trade status ("OPEN", "CLOSED_WIN", "CLOSED_LOSS", "STOPPED_OUT")
        duration_bars: Trade duration in candles (None if open)
        invalidation_triggered: Whether trade closed due to invalidation

    Example:
        >>> entry = EntryExecution(...)  # From entry model
        >>> trade = create_trade_from_entry(
        ...     entry, confirmation_candle, bos_candle, risk_config, market_context
        ... )
        >>> # Later, close the trade
        >>> closed_trade = close_trade(trade, exit_candle, "TP")
        >>> print(f"PnL: {closed_trade.pnl} ({closed_trade.r_realized}R)")
    """

    # Identity
    trade_id: str
    symbol: str
    timeframe: str

    # Entry details
    entry_execution: EntryExecution
    entry_timestamp: datetime
    entry_price: float
    direction: str
    setup_type: str

    # SL/TP (calculated at trade creation)
    stop_loss: float
    take_profit: float
    sl_rationale: str
    tp_rationale: str

    # Risk/Reward
    risk_amount: float
    reward_amount: float
    r_multiple: float
    contracts: int

    # Exit details (None if still open)
    exit_timestamp: datetime | None
    exit_price: float | None
    exit_reason: str | None

    # PnL (calculated at exit or mark-to-market)
    pnl: float | None
    pnl_percent: float | None
    r_realized: float | None

    # Dollar-based PnL (calculated at exit)
    pnl_dollars: float | None
    pnl_net: float | None
    slippage_cost: float | None
    commission_cost: float | None

    # Metadata
    status: str
    duration_bars: int | None
    invalidation_triggered: bool
    ignore_first_retest_bar: bool  # FIX #2: Retest protection flag for VWAP_RECLAIM

    # Diagnostics (mutable dict for debugging context)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def calculate_stop_loss(
    entry_execution: EntryExecution,
    direction: str,
    confirmation_candle: Candle,
    bos_candle: Candle | None = None,
    config: dict | None = None,
    vwap_value: float | None = None,
) -> tuple[float, str, bool]:
    """Calculate stop loss based on SOP rules.

    SOP Rules:
    - Continuation (long): SL = min(confirmation_low, bos_low)
    - Continuation (short): SL = max(confirmation_high, bos_high)
    - Fade: SL = sweep candle extreme (confirmation_candle is sweep)
    - SL must be outside liquidity zones (not inside FVG, sweep wick, etc.)
    - VWAP_RECLAIM: Minimum 20-tick buffer to prevent premature stop-out during retest

    Args:
        entry_execution: Entry execution with signal details
        direction: Trade direction ("long" or "short")
        confirmation_candle: Confirmation candle (or sweep candle for fades)
        bos_candle: Break of structure candle (optional, for continuation)
        config: Config dict for asset-specific tick sizes (optional)

    Returns:
        Tuple of (stop_loss_price, rationale, ignore_first_retest_bar)
        - stop_loss_price: Stop loss price level
        - rationale: Explanation of SL placement
        - ignore_first_retest_bar: True if SL should be ignored on first bar (VWAP_RECLAIM only)

    Example:
        >>> sl, rationale, retest_flag = calculate_stop_loss(entry, "long", conf_candle, bos_candle, config)
        >>> print(f"SL: {sl} - {rationale} (retest protection: {retest_flag})")
    """
    setup_type = entry_execution.signal.setup_type
    entry_price = entry_execution.entry_price

    # VWAP_FADE: Use sweep candle extreme (no retest protection)
    if setup_type == "VWAP_FADE":
        if direction == "long":
            sl = confirmation_candle.low
            rationale = "Below sweep candle low (fade setup)"
        else:
            sl = confirmation_candle.high
            rationale = "Above sweep candle high (fade setup)"

        # FIX: VWAP_FADE minimum 15-tick buffer to prevent instant stop-out
        # Get tick_size from config based on symbol (default 0.1 for GC)
        symbol = entry_execution.signal.symbol
        if config is not None:
            tick_size = config.get("assets", {}).get("tick_sizes", {}).get(symbol, 0.1)
        else:
            # Fallback defaults for common assets
            default_tick_sizes = {"GC": 0.1, "ES": 0.25, "NQ": 0.25, "CL": 0.01}
            tick_size = default_tick_sizes.get(symbol, 0.1)

        risk_distance = abs(entry_price - sl)
        risk_ticks = risk_distance / tick_size

        if risk_ticks < MIN_SL_TICKS_VWAP_FADE:
            # Expand SL outward to meet minimum requirement
            if direction == "long":
                sl = entry_price - (MIN_SL_TICKS_VWAP_FADE * tick_size)
            else:
                sl = entry_price + (MIN_SL_TICKS_VWAP_FADE * tick_size)

            rationale = f"VWAP Fade SL padded to {MIN_SL_TICKS_VWAP_FADE}-tick minimum (was {risk_ticks:.1f} ticks)"
            logger.info(
                f"VWAP_FADE SL expanded: {entry_price} -> {sl} "
                f"(from {risk_ticks:.1f} ticks to {MIN_SL_TICKS_VWAP_FADE} ticks)"
            )

        logger.debug(
            f"Fade SL calculated: {sl} (direction={direction}, " f"setup={setup_type})"
        )
        return sl, rationale, False  # No retest protection for fades

    # Sprint 3 Task 5: VWAP-zone SL for VWAP_RECLAIM setups
    # Other continuation setups use confirmation/BOS candle logic
    ignore_first_retest_bar = False

    # Bug Fix: Check for both None and NaN VWAP values
    vwap_is_valid = (
        vwap_value is not None
        and not (isinstance(vwap_value, float) and math.isnan(vwap_value))
        and not pd.isna(vwap_value)
    )

    if setup_type == "VWAP_RECLAIM" and vwap_is_valid:
        # Sprint 3: Use VWAP-zone SL (VWAP ± buffer) instead of micro candle extremes
        # This allows normal retest behavior without premature stop-out
        symbol = entry_execution.signal.symbol
        if config is not None:
            tick_size = config.get("assets", {}).get("tick_sizes", {}).get(symbol, 0.1)
        else:
            default_tick_sizes = {"GC": 0.1, "ES": 0.25, "NQ": 0.25, "CL": 0.01}
            tick_size = default_tick_sizes.get(symbol, 0.1)

        buffer_amount = VWAP_SL_BUFFER_TICKS * tick_size

        if direction == "long":
            sl = vwap_value - buffer_amount
            rationale = (
                f"VWAP-zone SL: VWAP - {VWAP_SL_BUFFER_TICKS} ticks (allows retest)"
            )
        else:
            sl = vwap_value + buffer_amount
            rationale = (
                f"VWAP-zone SL: VWAP + {VWAP_SL_BUFFER_TICKS} ticks (allows retest)"
            )

        # Verify 20-tick minimum floor still met
        risk_distance = abs(entry_price - sl)
        risk_ticks = risk_distance / tick_size

        if risk_ticks < MIN_SL_TICKS_VWAP_RECLAIM:
            # Expand SL outward to meet minimum requirement
            if direction == "long":
                sl = entry_price - (MIN_SL_TICKS_VWAP_RECLAIM * tick_size)
            else:
                sl = entry_price + (MIN_SL_TICKS_VWAP_RECLAIM * tick_size)

            rationale = f"VWAP-zone SL expanded to {MIN_SL_TICKS_VWAP_RECLAIM}-tick minimum (was {risk_ticks:.1f} ticks)"
            logger.info(
                f"VWAP_RECLAIM SL expanded from VWAP-zone: {entry_price} -> {sl} "
                f"(from {risk_ticks:.1f} ticks to {MIN_SL_TICKS_VWAP_RECLAIM} ticks)"
            )

        # Enable retest protection for all VWAP_RECLAIM setups
        ignore_first_retest_bar = True
        logger.debug(
            f"VWAP_RECLAIM VWAP-zone SL: {sl} (VWAP={vwap_value}, buffer={VWAP_SL_BUFFER_TICKS} ticks)"
        )

    elif setup_type == "VWAP_RECLAIM" and not vwap_is_valid:
        # Fallback to confirmation candle if VWAP not available
        logger.warning(
            "VWAP value not available for VWAP_RECLAIM, falling back to confirmation candle SL"
        )
        if direction == "long":
            sl = confirmation_candle.low
            rationale = "Below confirmation candle low (VWAP not available)"
        else:
            sl = confirmation_candle.high
            rationale = "Above confirmation candle high (VWAP not available)"
        ignore_first_retest_bar = True

    else:
        # Non-VWAP_RECLAIM continuation setups: use confirmation/BOS candle logic
        if direction == "long":
            # Long: SL below lower of confirmation/BOS
            if bos_candle is not None:
                sl = min(confirmation_candle.low, bos_candle.low)
                if sl == bos_candle.low:
                    rationale = "Below BOS candle low (structure-based)"
                else:
                    rationale = "Below confirmation candle low (structure-based)"
            else:
                sl = confirmation_candle.low
                rationale = "Below confirmation candle low (structure-based)"
        else:
            # Short: SL above higher of confirmation/BOS
            if bos_candle is not None:
                sl = max(confirmation_candle.high, bos_candle.high)
                if sl == bos_candle.high:
                    rationale = "Above BOS candle high (structure-based)"
                else:
                    rationale = "Above confirmation candle high (structure-based)"
            else:
                sl = confirmation_candle.high
                rationale = "Above confirmation candle high (structure-based)"

    # FIX #1: For VWAP_RECLAIM without VWAP, ensure minimum 20-tick buffer
    # FIX #2: VWAP_RECLAIM retest protection (skip SL on first bar)
    if setup_type == "VWAP_RECLAIM" and not vwap_is_valid:
        # Get tick_size from config based on symbol (default 0.1 for GC)
        symbol = entry_execution.signal.symbol
        if config is not None:
            tick_size = config.get("assets", {}).get("tick_sizes", {}).get(symbol, 0.1)
        else:
            # Fallback defaults for common assets
            default_tick_sizes = {"GC": 0.1, "ES": 0.25, "NQ": 0.25, "CL": 0.01}
            tick_size = default_tick_sizes.get(symbol, 0.1)

        risk_distance = abs(entry_price - sl)
        risk_ticks = risk_distance / tick_size

        if risk_ticks < MIN_SL_TICKS_VWAP_RECLAIM:
            # Expand SL outward to meet minimum requirement
            if direction == "long":
                sl = entry_price - (MIN_SL_TICKS_VWAP_RECLAIM * tick_size)
            else:
                sl = entry_price + (MIN_SL_TICKS_VWAP_RECLAIM * tick_size)

            rationale = f"VWAP Reclaim SL padded to {MIN_SL_TICKS_VWAP_RECLAIM}-tick minimum (was {risk_ticks:.1f} ticks)"
            logger.info(
                f"VWAP_RECLAIM SL expanded: {entry_price} -> {sl} "
                f"(from {risk_ticks:.1f} ticks to {MIN_SL_TICKS_VWAP_RECLAIM} ticks)"
            )

        # Enable retest protection for all VWAP_RECLAIM setups
        ignore_first_retest_bar = True
        logger.debug(f"VWAP_RECLAIM retest protection enabled for trade")

    # FIX #3: DXY_CONTINUATION minimum 15-tick buffer
    if setup_type == "DXY_CONTINUATION":
        # Get tick_size from config based on symbol (default 0.1 for GC)
        symbol = entry_execution.signal.symbol
        if config is not None:
            tick_size = config.get("assets", {}).get("tick_sizes", {}).get(symbol, 0.1)
        else:
            # Fallback defaults for common assets
            default_tick_sizes = {"GC": 0.1, "ES": 0.25, "NQ": 0.25, "CL": 0.01}
            tick_size = default_tick_sizes.get(symbol, 0.1)

        risk_distance = abs(entry_price - sl)
        risk_ticks = risk_distance / tick_size

        if risk_ticks < MIN_SL_TICKS_DXY_CONTINUATION:
            # Expand SL outward to meet minimum requirement
            if direction == "long":
                sl = entry_price - (MIN_SL_TICKS_DXY_CONTINUATION * tick_size)
            else:
                sl = entry_price + (MIN_SL_TICKS_DXY_CONTINUATION * tick_size)

            rationale = f"Continuation SL padded to {MIN_SL_TICKS_DXY_CONTINUATION}-tick minimum (was {risk_ticks:.1f} ticks)"
            logger.info(
                f"DXY_CONTINUATION SL expanded: {entry_price} -> {sl} "
                f"(from {risk_ticks:.1f} ticks to {MIN_SL_TICKS_DXY_CONTINUATION} ticks)"
            )

    logger.debug(
        f"Continuation SL calculated: {sl} (direction={direction}, "
        f"bos_provided={bos_candle is not None}, setup={setup_type}, "
        f"retest_protection={ignore_first_retest_bar})"
    )
    return sl, rationale, ignore_first_retest_bar


def calculate_take_profit(
    entry_price: float,
    stop_loss: float,
    direction: str,
    setup_type: str,
    r_multiple: float,
    month: int,
    htf_aligned: bool,
    dxy_aligned: bool,
) -> tuple[float, str]:
    """Calculate take profit based on SOP rules.

    SOP Rules:
    - Continuation: Default 3R (September: 2R max, Nov-Dec: 3R)
    - Fade: Default 2R (upgrade to 3R with HTF/DXY/seasonality alignment)
    - Formula: TP = entry ± (risk_distance × R_multiple)

    Args:
        entry_price: Entry price
        stop_loss: Stop loss price
        direction: Trade direction ("long" or "short")
        setup_type: Setup type ("VWAP_RECLAIM", "VWAP_FADE", "DXY_CONTINUATION")
        r_multiple: R:R multiple to use (2.0, 3.0, etc.)
        month: Month number (1-12) for seasonality
        htf_aligned: Whether HTF bias aligns
        dxy_aligned: Whether DXY correlation aligns

    Returns:
        Tuple of (take_profit_price, rationale)

    Example:
        >>> tp, rationale = calculate_take_profit(
        ...     2650.0, 2645.0, "long", "VWAP_RECLAIM", 3.0, 11, True, True
        ... )
        >>> print(f"TP: {tp} - {rationale}")
    """
    # Calculate risk distance
    if direction == "long":
        risk_distance = entry_price - stop_loss
    else:
        risk_distance = stop_loss - entry_price

    # Build rationale
    rationale_parts = []

    # Determine R-multiple reasoning
    if setup_type == "VWAP_FADE":
        if r_multiple >= 3.0 and (htf_aligned or dxy_aligned or month in [11, 12]):
            rationale_parts.append("3R fade (upgraded with HTF/DXY/seasonality)")
        else:
            rationale_parts.append("2R fade (default)")
    else:
        # Continuation setups
        if month == 9:
            rationale_parts.append("2R continuation (September defensive)")
        elif month in [11, 12]:
            rationale_parts.append("3R continuation (Nov-Dec trend window)")
        else:
            rationale_parts.append("3R continuation (Jan-Aug baseline)")

    # Calculate TP
    if direction == "long":
        tp = entry_price + (risk_distance * r_multiple)
    else:
        tp = entry_price - (risk_distance * r_multiple)

    rationale = " ".join(rationale_parts)
    logger.debug(
        f"TP calculated: {tp} (entry={entry_price}, sl={stop_loss}, "
        f"R={r_multiple}, month={month})"
    )
    return tp, rationale


def create_trade_from_entry(
    entry_execution: EntryExecution,
    confirmation_candle: Candle,
    bos_candle: Candle | None,
    risk_config: dict,
    market_context: dict,
    config: dict | None = None,
    vwap_value: float | None = None,
) -> Trade:
    """Create Trade object from executed entry.

    This function orchestrates trade creation by:
    1. Calculating SL based on structure
    2. Calculating TP based on R-multiple and seasonality
    3. Computing risk/reward amounts
    4. Generating unique trade ID
    5. Setting initial status to "OPEN"

    Args:
        entry_execution: Entry execution from entry model
        confirmation_candle: Confirmation candle for SL calculation
        bos_candle: Break of structure candle (optional)
        risk_config: Risk configuration dict containing:
            - risk_per_trade: Dollar risk per trade
            - buffer_phase: Current capital phase
            - max_contracts: Maximum contracts allowed
        market_context: Market context dict containing:
            - month: Month number (1-12)
            - htf_aligned: HTF bias alignment (bool)
            - dxy_aligned: DXY correlation alignment (bool)
            - seasonality: Season name (optional)

    Returns:
        Trade object with calculated SL/TP and status="OPEN"

    Example:
        >>> entry = EntryExecution(...)
        >>> trade = create_trade_from_entry(
        ...     entry,
        ...     confirmation_candle,
        ...     bos_candle,
        ...     {"risk_per_trade": 350, "max_contracts": 1},
        ...     {"month": 11, "htf_aligned": True, "dxy_aligned": True}
        ... )
    """
    signal = entry_execution.signal
    direction = signal.direction
    setup_type = signal.setup_type

    # 1. Calculate stop loss (FIX #2: Also returns retest protection flag)
    # Sprint 3 Task 5: Pass VWAP value for VWAP-zone SL calculation
    stop_loss, sl_rationale, ignore_first_retest_bar = calculate_stop_loss(
        entry_execution, direction, confirmation_candle, bos_candle, config, vwap_value
    )

    # 1.5. Validate minimum risk threshold (prevent micro-chop entries)
    if config is not None:
        tick_size = (
            config.get("assets", {}).get("tick_sizes", {}).get(signal.symbol, 0.1)
        )
        risk_distance = abs(entry_execution.entry_price - stop_loss)
        risk_ticks = risk_distance / tick_size

        if risk_ticks < MIN_RISK_TICKS:
            raise ValueError(
                f"Risk below minimum threshold: {risk_ticks:.1f} ticks < {MIN_RISK_TICKS} ticks "
                f"(risk={risk_distance:.2f} points, tick_size={tick_size})"
            )

    # 2. Determine R-multiple based on setup and seasonality
    month = market_context.get("month", 1)
    htf_aligned = market_context.get("htf_aligned", False)
    dxy_aligned = market_context.get("dxy_aligned", False)

    # Determine R-multiple per SOP
    if setup_type == "VWAP_FADE":
        # Fade: default 2R, upgrade to 3R with alignment
        if month in [11, 12] and htf_aligned and dxy_aligned:
            r_multiple = 3.0
        else:
            r_multiple = 2.0
    else:
        # Continuation: default 3R, except September (2R)
        if month == 9:
            r_multiple = 2.0
        else:
            r_multiple = 3.0

    # 3. Calculate take profit
    take_profit, tp_rationale = calculate_take_profit(
        entry_execution.entry_price,
        stop_loss,
        direction,
        setup_type,
        r_multiple,
        month,
        htf_aligned,
        dxy_aligned,
    )

    # 4. Calculate risk/reward amounts (in points, not dollars)
    risk_distance = abs(entry_execution.entry_price - stop_loss)
    reward_distance = abs(take_profit - entry_execution.entry_price)

    # 5. Determine contracts (from risk config)
    contracts = risk_config.get("max_contracts", 1)

    # 5.5. Validate trade invariants (FIX #3/#8)
    # This ensures we never create a trade with invalid SL/TP or risk
    validate_trade_invariants(
        entry_price=entry_execution.entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        direction=direction,
        risk_amount=risk_distance,
        reward_amount=reward_distance,
    )

    # 6. Generate unique trade ID
    trade_id = str(uuid4())

    logger.info(
        f"Trade created: {trade_id} {direction} {signal.symbol} @ "
        f"{entry_execution.entry_price} (SL={stop_loss}, TP={take_profit}, "
        f"R={r_multiple}, setup={setup_type})"
    )

    return Trade(
        trade_id=trade_id,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        entry_execution=entry_execution,
        entry_timestamp=entry_execution.entry_timestamp,
        entry_price=entry_execution.entry_price,
        direction=direction,
        setup_type=setup_type,
        stop_loss=stop_loss,
        take_profit=take_profit,
        sl_rationale=sl_rationale,
        tp_rationale=tp_rationale,
        risk_amount=risk_distance,
        reward_amount=reward_distance,
        r_multiple=r_multiple,
        contracts=contracts,
        exit_timestamp=None,
        exit_price=None,
        exit_reason=None,
        pnl=None,
        pnl_percent=None,
        r_realized=None,
        pnl_dollars=None,
        pnl_net=None,
        slippage_cost=None,
        commission_cost=None,
        status="OPEN",
        duration_bars=None,
        invalidation_triggered=False,
        ignore_first_retest_bar=ignore_first_retest_bar,  # FIX #2: Store retest protection flag
    )


def close_trade(
    trade: Trade,
    exit_candle: Candle,
    exit_reason: str,
    config: dict | None = None,
) -> Trade:
    """Close trade and calculate final PnL (points and dollars).

    Creates a new Trade instance with exit details (immutable update).
    Calculates realized PnL in both points and dollars, including:
    - Point-based PnL (existing)
    - Dollar-based gross PnL
    - Slippage costs
    - Commission costs
    - Net PnL after all costs

    Args:
        trade: Open trade to close
        exit_candle: Exit candle
        exit_reason: Exit reason ("tp", "sl", "timeout", "vwap_invalidation",
                   "htf_invalidation", "dxy_flip", "session_close",
                   "window_expired", "daily_risk_stop", "end_of_data", etc.)
        config: Configuration dict with tick values, slippage, and commission
                If None, dollar-based PnL fields will be None

    Returns:
        New Trade instance with exit details and calculated PnL

    Example:
        >>> from common.config import load_config
        >>> config = load_config()
        >>> closed = close_trade(open_trade, exit_candle, "tp", config)
        >>> print(f"PnL: {closed.pnl} points, ${closed.pnl_net} net")
    """
    # Determine exit price based on exit reason
    # Handle both old (uppercase) and new (lowercase) exit reasons for backward compatibility
    exit_reason_lower = exit_reason.lower() if exit_reason else ""

    if exit_reason_lower in ("tp", "take_profit"):
        exit_price = trade.take_profit
    elif exit_reason_lower in ("sl", "stop_loss"):
        exit_price = trade.stop_loss
    elif exit_reason_lower in (
        "vwap_invalidation",
        "htf_invalidation",
        "dxy_flip",
        "session_close",
        "window_expired",
        "daily_risk_stop",
        "invalidation",
        "timeout",
        "time",
        "end_of_data",
        "invalid_setup",
    ):
        # Use close price of exit candle for all invalidation/timeout exits
        exit_price = exit_candle.close
    else:
        # Default to close price (backward compatibility)
        exit_price = exit_candle.close

    # Calculate PnL in points
    if trade.direction == "long":
        pnl = (exit_price - trade.entry_price) * trade.contracts
    else:
        pnl = (trade.entry_price - exit_price) * trade.contracts

    # Calculate R realized (per-contract)
    if trade.risk_amount > 0:
        if trade.direction == "long":
            r_realized = (exit_price - trade.entry_price) / trade.risk_amount
        else:
            r_realized = (trade.entry_price - exit_price) / trade.risk_amount
    else:
        r_realized = 0

    # Calculate PnL as % of risk (must be consistent with r_realized)
    # pnl_percent = (r_realized * 100) to ensure consistency regardless of contracts
    pnl_percent = r_realized * 100

    # Calculate dollar-based PnL if config provided
    pnl_dollars = None
    pnl_net = None
    slippage_cost = None
    commission_cost = None

    if config is not None:
        from backtester.pnl_calculator import calculate_net_pnl, compute_slippage

        try:
            # Extract config values
            tick_value = (
                config.get("assets", {}).get("tick_values", {}).get(trade.symbol, 10.0)
            )
            tick_size = (
                config.get("assets", {}).get("tick_sizes", {}).get(trade.symbol, 0.1)
            )
            commission_per_contract = config.get("backtest", {}).get(
                "commission_per_trade", 5.0
            )

            # PATCH PART 5: Dynamic slippage based on ATR instead of fixed value
            # Try to get ATR from config (passed from simulator) or use default
            atr = config.get("current_atr")
            slippage_ticks = compute_slippage(atr, order_type="market")

            # Calculate complete PnL breakdown
            pnl_breakdown = calculate_net_pnl(
                trade.entry_price,
                exit_price,
                trade.direction,
                trade.contracts,
                tick_value,
                tick_size,
                slippage_ticks,
                commission_per_contract,
            )

            pnl_dollars = pnl_breakdown["gross_pnl"]
            pnl_net = pnl_breakdown["net_pnl"]
            slippage_cost = pnl_breakdown["slippage_cost"]
            commission_cost = pnl_breakdown["commission_cost"]

            logger.info(
                f"Dollar PnL calculated: gross=${pnl_dollars:.2f}, "
                f"net=${pnl_net:.2f} (slippage={slippage_cost:.2f}, "
                f"commission={commission_cost:.2f})"
            )
        except Exception as e:
            logger.warning(
                f"Failed to calculate dollar-based PnL: {e}. "
                f"Point-based PnL will still be available."
            )

    # Determine trade status
    exit_reason_lower = exit_reason.lower() if exit_reason else ""
    if exit_reason_lower in ("sl", "stop_loss"):
        status = "STOPPED_OUT"
    elif pnl > 0:
        status = "CLOSED_WIN"
    else:
        status = "CLOSED_LOSS"

    # Calculate duration in bars
    # Get timeframe multiplier
    timeframe = trade.timeframe
    if timeframe.endswith("m"):
        minutes_per_bar = int(timeframe[:-1])
    elif timeframe.endswith("h"):
        minutes_per_bar = int(timeframe[:-1]) * 60
    else:
        minutes_per_bar = 1  # Default to 1 minute

    time_delta = exit_candle.timestamp - trade.entry_timestamp
    duration_bars = int(time_delta.total_seconds() / 60 / minutes_per_bar)

    # Determine if invalidation triggered
    exit_reason_lower = exit_reason.lower() if exit_reason else ""
    invalidation_triggered = exit_reason_lower in (
        "vwap_invalidation",
        "htf_invalidation",
        "dxy_flip",
        "session_close",
        "window_expired",
        "daily_risk_stop",
        "invalidation",
    )

    logger.info(
        f"Trade closed: {trade.trade_id} {trade.direction} {trade.symbol} "
        f"(entry={trade.entry_price}, exit={exit_price}, pnl={pnl:.2f}, "
        f"R={r_realized:.2f}, reason={exit_reason})"
    )

    # Return new Trade instance with exit details
    return replace(
        trade,
        exit_timestamp=exit_candle.timestamp,
        exit_price=exit_price,
        exit_reason=exit_reason,
        pnl=pnl,
        pnl_percent=pnl_percent,
        r_realized=r_realized,
        pnl_dollars=pnl_dollars,
        pnl_net=pnl_net,
        slippage_cost=slippage_cost,
        commission_cost=commission_cost,
        status=status,
        duration_bars=duration_bars,
        invalidation_triggered=invalidation_triggered,
    )


def to_dict(trade: Trade) -> dict:
    """Convert Trade to JSON-serializable dictionary.

    Handles datetime serialization and nested objects (EntryExecution, Signal).

    Args:
        trade: Trade object to serialize

    Returns:
        Dictionary with all Trade attributes (JSON-serializable)

    Example:
        >>> trade_dict = to_dict(trade)
        >>> import json
        >>> json_str = json.dumps(trade_dict)
    """
    from rule_engine.signal import Signal

    from backtester.entry_model import EntryExecution

    # Helper to serialize EntryExecution
    def serialize_entry_execution(entry: EntryExecution) -> dict:
        return {
            "signal_timestamp": entry.signal_timestamp.isoformat(),
            "entry_timestamp": entry.entry_timestamp.isoformat(),
            "entry_price": entry.entry_price,
            "signal": serialize_signal(entry.signal),
            "executed": entry.executed,
            "rejection_reason": entry.rejection_reason,
        }

    # Helper to serialize Signal
    def serialize_signal(signal: Signal) -> dict:
        return {
            "timestamp": signal.timestamp.isoformat(),
            "symbol": signal.symbol,
            "timeframe": signal.timeframe,
            "direction": signal.direction,
            "setup_type": signal.setup_type,
            "htf_bias": signal.htf_bias,
            "score": signal.score,
            "confidence": signal.confidence,
            "factors": signal.factors,
            "rationale": signal.rationale,
            "validation_flags": signal.validation_flags,
            "enforcer_tier": signal.enforcer_tier,
        }

    return {
        "trade_id": trade.trade_id,
        "symbol": trade.symbol,
        "timeframe": trade.timeframe,
        "entry_execution": serialize_entry_execution(trade.entry_execution),
        "entry_timestamp": trade.entry_timestamp.isoformat(),
        "entry_price": trade.entry_price,
        "direction": trade.direction,
        "setup_type": trade.setup_type,
        "stop_loss": trade.stop_loss,
        "take_profit": trade.take_profit,
        "sl_rationale": trade.sl_rationale,
        "tp_rationale": trade.tp_rationale,
        "risk_amount": trade.risk_amount,
        "reward_amount": trade.reward_amount,
        "r_multiple": trade.r_multiple,
        "contracts": trade.contracts,
        "exit_timestamp": (
            trade.exit_timestamp.isoformat() if trade.exit_timestamp else None
        ),
        "exit_price": trade.exit_price,
        "exit_reason": trade.exit_reason,
        "pnl": trade.pnl,
        "pnl_percent": trade.pnl_percent,
        "r_realized": trade.r_realized,
        "pnl_dollars": trade.pnl_dollars,
        "pnl_net": trade.pnl_net,
        "slippage_cost": trade.slippage_cost,
        "commission_cost": trade.commission_cost,
        "status": trade.status,
        "duration_bars": trade.duration_bars,
        "invalidation_triggered": trade.invalidation_triggered,
        "ignore_first_retest_bar": trade.ignore_first_retest_bar,
        "diagnostics": trade.diagnostics or {},
    }


def from_dict(data: dict) -> Trade:
    """Reconstruct Trade from dictionary.

    Handles datetime deserialization and nested objects (EntryExecution, Signal).

    Args:
        data: Dictionary with Trade data (from to_dict)

    Returns:
        Reconstructed Trade object

    Example:
        >>> trade_dict = to_dict(trade)
        >>> reconstructed = from_dict(trade_dict)
    """
    from datetime import datetime

    from rule_engine.signal import Signal

    from backtester.entry_model import EntryExecution

    # Helper to deserialize Signal
    def deserialize_signal(signal_data: dict) -> Signal:
        return Signal(
            timestamp=datetime.fromisoformat(signal_data["timestamp"]),
            symbol=signal_data["symbol"],
            timeframe=signal_data["timeframe"],
            direction=signal_data["direction"],
            setup_type=signal_data["setup_type"],
            htf_bias=signal_data["htf_bias"],
            score=signal_data["score"],
            confidence=signal_data["confidence"],
            factors=signal_data["factors"],
            rationale=signal_data["rationale"],
            validation_flags=signal_data["validation_flags"],
            enforcer_tier=signal_data["enforcer_tier"],
        )

    # Helper to deserialize EntryExecution
    def deserialize_entry_execution(entry_data: dict) -> EntryExecution:
        return EntryExecution(
            signal_timestamp=datetime.fromisoformat(entry_data["signal_timestamp"]),
            entry_timestamp=datetime.fromisoformat(entry_data["entry_timestamp"]),
            entry_price=entry_data["entry_price"],
            signal=deserialize_signal(entry_data["signal"]),
            executed=entry_data["executed"],
            rejection_reason=entry_data["rejection_reason"],
        )

    return Trade(
        trade_id=data["trade_id"],
        symbol=data["symbol"],
        timeframe=data["timeframe"],
        entry_execution=deserialize_entry_execution(data["entry_execution"]),
        entry_timestamp=datetime.fromisoformat(data["entry_timestamp"]),
        entry_price=data["entry_price"],
        direction=data["direction"],
        setup_type=data["setup_type"],
        stop_loss=data["stop_loss"],
        take_profit=data["take_profit"],
        sl_rationale=data["sl_rationale"],
        tp_rationale=data["tp_rationale"],
        risk_amount=data["risk_amount"],
        reward_amount=data["reward_amount"],
        r_multiple=data["r_multiple"],
        contracts=data["contracts"],
        exit_timestamp=(
            datetime.fromisoformat(data["exit_timestamp"])
            if data["exit_timestamp"]
            else None
        ),
        exit_price=data["exit_price"],
        exit_reason=data["exit_reason"],
        pnl=data["pnl"],
        pnl_percent=data["pnl_percent"],
        r_realized=data["r_realized"],
        pnl_dollars=data.get("pnl_dollars"),
        pnl_net=data.get("pnl_net"),
        slippage_cost=data.get("slippage_cost"),
        commission_cost=data.get("commission_cost"),
        status=data["status"],
        duration_bars=data["duration_bars"],
        invalidation_triggered=data["invalidation_triggered"],
        ignore_first_retest_bar=data.get(
            "ignore_first_retest_bar", False
        ),  # Default to False for backward compat
        diagnostics=data.get(
            "diagnostics", {}
        ),  # Default to empty dict for backward compat
    )
