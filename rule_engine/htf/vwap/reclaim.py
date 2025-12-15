"""VWAP Reclaim Detection - proper sequence validation.

Implements the complete VWAP reclaim sequence:
1. Price below VWAP
2. Liquidity sweep
3. Displacement candle
4. Close above VWAP

A valid VWAP_RECLAIM setup requires ALL of these components.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from common.logger import get_logger

from rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


@dataclass
class VWAPReclaimState:
    """State tracking for VWAP reclaim sequence.

    Attributes:
        started_below: Price was below VWAP in the lookback window
        sweep_detected: Liquidity sweep occurred
        sweep_bar_idx: Bar index where sweep occurred
        displacement_detected: Strong displacement move present
        reclaim_confirmed: Close above VWAP after complete sequence
    """

    started_below: bool = False
    sweep_detected: bool = False
    sweep_bar_idx: int | None = None
    displacement_detected: bool = False
    reclaim_confirmed: bool = False


def detect_vwap_reclaim(
    df: pd.DataFrame,
    htf_bias: HTFBias,
    lookback: int = 5,
) -> tuple[bool, VWAPReclaimState]:
    """Detect complete VWAP reclaim sequence.

    Scans the last N bars to verify:
    1. Price started below VWAP
    2. Liquidity sweep detected (from HTF bias)
    3. Displacement candle present (body > average)
    4. Currently closed above VWAP

    Args:
        df: DataFrame with OHLC + VWAP columns
        htf_bias: HTFBias object with sweep detection
        lookback: Number of bars to scan (default: 5)

    Returns:
        Tuple of (is_valid_reclaim, state)

    Example:
        >>> is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)
        >>> if is_reclaim:
        ...     print("Valid VWAP reclaim detected")
    """
    state = VWAPReclaimState()

    # Validate required columns
    required_cols = {"open", "high", "low", "close", "vwap"}
    if not required_cols.issubset(df.columns):
        logger.warning(f"Missing required columns: {required_cols - set(df.columns)}")
        return False, state

    # Need at least lookback bars
    if len(df) < lookback:
        return False, state

    # Get recent bars
    recent_df = df.iloc[-lookback:]

    # Check 1: Price was below VWAP at some point
    was_below = (recent_df["close"] < recent_df["vwap"]).any()
    state.started_below = was_below

    if not was_below:
        return False, state

    # Check 2: Liquidity sweep detected (from HTF bias)
    state.sweep_detected = htf_bias.liquidity_sweep_detected

    if not state.sweep_detected:
        return False, state

    # Check 3: Displacement candle present
    # Find the bar that crossed above VWAP
    reclaim_bar_idx = None
    for i in range(len(recent_df) - 1):
        curr_close = recent_df["close"].iloc[i]
        next_close = recent_df["close"].iloc[i + 1]
        curr_vwap = recent_df["vwap"].iloc[i]
        next_vwap = recent_df["vwap"].iloc[i + 1]

        # Crossed from below to above
        if curr_close < curr_vwap and next_close > next_vwap:
            reclaim_bar_idx = i + 1  # The bar that crossed above
            break

    if reclaim_bar_idx is not None:
        # Check if reclaim bar is a displacement candle
        abs_idx = len(df) - lookback + reclaim_bar_idx
        reclaim_body = abs(
            recent_df["close"].iloc[reclaim_bar_idx]
            - recent_df["open"].iloc[reclaim_bar_idx]
        )

        # Calculate average body size of previous bars
        start_idx = max(0, abs_idx - 10)
        prev_bars = df.iloc[start_idx:abs_idx]
        if len(prev_bars) > 0:
            avg_body = (prev_bars["close"] - prev_bars["open"]).abs().mean()
            state.displacement_detected = reclaim_body > avg_body
        else:
            state.displacement_detected = False
    else:
        state.displacement_detected = False

    if not state.displacement_detected:
        return False, state

    # Check 4: Currently closed above VWAP
    current_close = recent_df["close"].iloc[-1]
    current_vwap = recent_df["vwap"].iloc[-1]
    state.reclaim_confirmed = current_close > current_vwap

    if not state.reclaim_confirmed:
        return False, state

    # All checks passed
    logger.debug(
        f"Valid VWAP reclaim detected: started_below={state.started_below}, "
        f"sweep={state.sweep_detected}, displacement={state.displacement_detected}, "
        f"confirmed={state.reclaim_confirmed}"
    )

    return True, state


def validate_reclaim_prerequisites(
    htf_bias: HTFBias, features: pd.Series | None = None
) -> tuple[bool, str | None]:
    """Validate HTF bias meets reclaim prerequisites (loosened for SOP compliance).

    Prerequisites (loosened to reduce over-filtering):
    1. Liquidity sweep detected
    2. Structure clarity >= 0.5 (lowered from 0.7)
    3. BOS detected recently (within 15 bars)
    4. BOS or CHoCH aligns with trade direction (if features provided)
    5. No excessive structure conflict (if features provided)

    Note: Removed chop check - VWAP_RECLAIM should work during gold micro chop per SOP.

    Args:
        htf_bias: HTFBias object to validate
        features: Optional feature series for additional validation checks

    Returns:
        Tuple of (is_valid, rejection_reason)

    Example:
        >>> is_valid, reason = validate_reclaim_prerequisites(htf_bias)
        >>> if not is_valid:
        ...     print(f"Rejected: {reason}")
    """
    # Check 1: Liquidity sweep
    if not htf_bias.liquidity_sweep_detected:
        return False, "No liquidity sweep detected"

    # Check 2: Structure clarity (lowered threshold)
    if htf_bias.structure_clarity < 0.5:
        return (
            False,
            f"Structure clarity too low: {htf_bias.structure_clarity:.2f} < 0.5",
        )

    # Check 3: Recent BOS
    if not htf_bias.bos_detected:
        return False, "No BOS detected"

    if htf_bias.bars_since_bos is None:
        return False, "BOS timing unknown"

    if htf_bias.bars_since_bos > 15:
        return False, f"BOS too stale: {htf_bias.bars_since_bos} bars ago (>15)"

    # Enhanced checks if features are provided
    if features is not None:
        # Check 4: BOS or CHoCH alignment with trade direction
        bos_direction = features.get("bos_direction")
        choch_detected = features.get("choch_detected", False)
        choch_direction = features.get("choch_direction")

        direction = htf_bias.direction

        # Either BOS or CHoCH should align with trade direction
        if direction == "long":
            has_bullish_signal = (bos_direction == "bullish") or (
                choch_detected and choch_direction == "bullish"
            )
            if not has_bullish_signal:
                return (
                    False,
                    f"No bullish BOS/CHoCH for long reclaim "
                    f"(bos={bos_direction}, choch={choch_direction})",
                )
        elif direction == "short":
            has_bearish_signal = (bos_direction == "bearish") or (
                choch_detected and choch_direction == "bearish"
            )
            if not has_bearish_signal:
                return (
                    False,
                    f"No bearish BOS/CHoCH for short reclaim "
                    f"(bos={bos_direction}, choch={choch_direction})",
                )

        # Check 5: Reject if excessive structure conflict
        # Note: VWAP_RECLAIM can work during micro chop, but not during conflict
        structure_conflict = features.get("structure_conflict_flag", False)
        if structure_conflict:
            return False, "Structure conflict detected (mixed HH/LL signals)"

    # All prerequisites met
    return True, None
