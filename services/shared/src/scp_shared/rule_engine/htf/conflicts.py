"""HTF Bias Conflict Detection Rules.

Detects conflicting market conditions that should neutralize HTF bias:
1. Structure conflict between 1H and 15M timeframes
2. Price chop on 15M timeframe
3. Liquidity sweep against established trend

Task: Define conflict rules
Epic: Full HTF Bias Engine Upgrade
Status: In Progress
"""

from __future__ import annotations

import pandas as pd
from scp_shared.common.logger import get_logger

from scp_shared.rule_engine.htf.types import ChopSeverity

logger = get_logger(__name__)


def detect_structure_conflict(
    structure_1h: str | None,
    structure_15m: str | None,
) -> tuple[bool, str | None]:
    """Detect if 1H and 15M structures are in STRONG conflict.

    Only marks conflict when both timeframes show STRONG opposing momentum.
    Allows normal retracement patterns (HL+LL, LH+HH) which are healthy.

    Args:
        structure_1h: 1H structure label (HH, HL, LH, LL, or None)
        structure_15m: 15M structure label (HH, HL, LH, LL, or None)

    Returns:
        Tuple of (is_conflict, reason):
        - is_conflict: True if structures are in STRONG conflict
        - reason: Description of conflict, or None if no conflict

    Logic (loosened to allow retracements):
        - 1H HH + 15M LL = TRUE conflict (strong momentum opposition)
        - 1H LL + 15M HH = TRUE conflict (strong momentum opposition)
        - 1H HL + 15M LL = NO conflict (normal bullish retracement)
        - 1H LH + 15M HH = NO conflict (normal bearish retracement)
        - Same direction = NO conflict

    Example:
        >>> detect_structure_conflict("HH", "LL")
        (True, "1H strong bullish (HH) conflicts with 15M strong bearish (LL)")
        >>> detect_structure_conflict("HL", "LL")
        (False, None)  # Normal retracement, not a conflict
    """
    # Handle None or empty values
    if not structure_1h or not structure_15m:
        return False, None

    # Only TRUE conflict when BOTH timeframes show STRONG opposing momentum
    # HH = strong bullish, LL = strong bearish
    # HL = bullish with pullback (retracement), LH = bearish with pullback

    # Strong bullish 1H (HH only) + Strong bearish 15M (LL only) = conflict
    if structure_1h == "HH" and structure_15m == "LL":
        reason = (
            f"1H strong bullish ({structure_1h}) conflicts with "
            f"15M strong bearish ({structure_15m})"
        )
        logger.debug(f"Structure conflict detected: {reason}")
        return True, reason

    # Strong bearish 1H (LL only) + Strong bullish 15M (HH only) = conflict
    if structure_1h == "LL" and structure_15m == "HH":
        reason = (
            f"1H strong bearish ({structure_1h}) conflicts with "
            f"15M strong bullish ({structure_15m})"
        )
        logger.debug(f"Structure conflict detected: {reason}")
        return True, reason

    # All other combinations are allowed (including retracements):
    # - HL + LL: bullish 1H with bearish 15M retracement (normal)
    # - HL + LH: bullish 1H with 15M pullback (normal)
    # - LH + HH: bearish 1H with bullish 15M retracement (normal)
    # - LH + HL: bearish 1H with 15M pullback (normal)
    # - Same direction: always allowed

    logger.debug(
        f"No structure conflict: 1H={structure_1h}, 15M={structure_15m} "
        f"(retracements and pullbacks allowed)"
    )
    return False, None


def detect_price_chop_15m(
    df_15m: pd.DataFrame,
    wick_threshold: float = 1.8,
    min_chop_candles: int = 5,
    atr: float | None = None,
    min_candle_size_ratio: float = 0.3,
) -> bool:
    """Detect if 15M price action is in chop mode (tolerant version).

    Chop is defined as sustained wick-to-wick behavior where wicks are large
    relative to the candle body, indicating ranging/indecisive market conditions.

    Tolerant thresholds (calibrated for intraday Gold):
    - Wicks must be 1.8x body or larger (catches actual indecision, not reactions)
    - Requires 5 consecutive candles (filters transient noise)
    - Filters out small candles (< 0.3 * ATR) to avoid noise

    Args:
        df_15m: DataFrame with 15M OHLC data
        wick_threshold: Minimum wick-to-body ratio to consider chop (default: 1.0)
        min_chop_candles: Consecutive chop candles needed to trigger (default: 5)
        atr: Average True Range for noise filtering (optional)
        min_candle_size_ratio: Min candle size as fraction of ATR (default: 0.3)

    Returns:
        True if chop detected in recent candles

    Logic:
        - Chop candle: (upper_wick + lower_wick) / body >= wick_threshold
        - Noise filter: candles with range < min_candle_size_ratio * ATR ignored
        - Chop condition: min_chop_candles consecutive chop candles
        - Check most recent candles

    Raises:
        ValueError: If required columns missing or invalid parameters

    Example:
        >>> df = pd.DataFrame({
        ...     'high': [100, 105, 110],
        ...     'low': [80, 85, 90],
        ...     'open': [95, 97, 99],
        ...     'close': [97, 99, 101]
        ... })
        >>> detect_price_chop_15m(df)
        True  # Large wicks indicate chop
    """
    # Validate parameters
    if wick_threshold <= 0:
        raise ValueError(f"wick_threshold must be > 0, got {wick_threshold}")
    if min_chop_candles < 1:
        raise ValueError(f"min_chop_candles must be >= 1, got {min_chop_candles}")

    # Validate required columns
    required_cols = {"high", "low", "open", "close"}
    missing_cols = required_cols - set(df_15m.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required column(s): {missing_cols}. "
            f"Available columns: {list(df_15m.columns)}"
        )

    # Handle empty DataFrame
    if len(df_15m) == 0:
        return False

    # Calculate wick sizes and body size
    upper_wick = df_15m["high"] - df_15m[["open", "close"]].max(axis=1)
    lower_wick = df_15m[["open", "close"]].min(axis=1) - df_15m["low"]
    body_size = (df_15m["close"] - df_15m["open"]).abs()

    # ATR-based noise filter: ignore small candles
    is_noise_candle = pd.Series([False] * len(df_15m), index=df_15m.index)
    if atr is not None and atr > 0:
        candle_range = df_15m["high"] - df_15m["low"]
        min_candle_size = atr * min_candle_size_ratio
        is_noise_candle = candle_range < min_candle_size

        noise_count = is_noise_candle.sum()
        if noise_count > 0:
            logger.debug(
                f"Filtering {noise_count} noise candles (range < {min_candle_size:.2f})"
            )

    # Calculate wick ratio
    wick_ratio = pd.Series(index=df_15m.index, dtype=float)

    # Handle zero body (doji) - treat as chop
    zero_body_mask = body_size == 0
    wick_ratio[zero_body_mask] = float("inf")

    # Calculate normal ratio for non-zero bodies
    non_zero_mask = ~zero_body_mask
    wick_ratio[non_zero_mask] = (
        upper_wick[non_zero_mask] + lower_wick[non_zero_mask]
    ) / body_size[non_zero_mask]

    # Identify individual chop candles (excluding noise candles)
    is_chop_candle = (wick_ratio >= wick_threshold) & (~is_noise_candle)
    is_chop_candle = is_chop_candle.fillna(False)

    # Count consecutive chop candles from the end
    consecutive_count = 0
    for i in range(len(df_15m) - 1, -1, -1):
        if is_chop_candle.iloc[i]:
            consecutive_count += 1
        else:
            break  # Stop at first non-chop candle

    # Chop detected if recent consecutive count >= threshold
    chop_detected = consecutive_count >= min_chop_candles

    if chop_detected:
        logger.debug(
            f"15M price chop detected: {consecutive_count} consecutive chop candles "
            f"(threshold={min_chop_candles})"
        )

    return chop_detected


def classify_chop_severity(
    df_15m: pd.DataFrame,
    atr: float | None = None,
    wick_threshold: float = 1.8,
    min_candle_size_ratio: float = 0.3,
    soft_threshold: int = 3,
    hard_threshold: int = 5,
    extreme_wick_ratio: float = 2.0,
) -> tuple[ChopSeverity, int]:
    """Classify chop severity based on consecutive count and wick extremity.

    This function extends detect_price_chop_15m() by adding severity classification
    to enable setup-aware chop handling. Detection logic remains unchanged.

    Args:
        df_15m: DataFrame with 15M OHLC data
        atr: Average True Range for noise filtering (optional)
        wick_threshold: Minimum wick-to-body ratio to consider chop (default: 1.8)
        min_candle_size_ratio: Min candle size as fraction of ATR (default: 0.3)
        soft_threshold: Consecutive candles for SOFT_CHOP (default: 3)
        hard_threshold: Consecutive candles for HARD_CHOP (default: 5)
        extreme_wick_ratio: Wick ratio that escalates severity (default: 2.0)

    Returns:
        Tuple of (ChopSeverity, consecutive_count):
        - ChopSeverity.NONE: 0-2 consecutive chop candles
        - ChopSeverity.SOFT_CHOP: 3-4 consecutive chop candles
        - ChopSeverity.HARD_CHOP: 5+ consecutive chop candles
        - Extreme wick ratios (>2.0) escalate to next severity level

    Logic:
        1. Use existing chop detection logic (wick-to-body ratio)
        2. Count consecutive chop candles from most recent
        3. Classify severity based on count and wick extremity
        4. Escalate severity if wicks are extremely large (>2.0 ratio)

    Example:
        >>> severity, count = classify_chop_severity(df_15m, atr=5.0)
        >>> if severity == ChopSeverity.SOFT_CHOP:
        ...     # Allow VWAP_FADE, penalize VWAP_RECLAIM
        >>> elif severity == ChopSeverity.HARD_CHOP:
        ...     # Block most setups except VWAP_FADE with confirmation
    """
    # Validate parameters
    if wick_threshold <= 0:
        raise ValueError(f"wick_threshold must be > 0, got {wick_threshold}")
    if soft_threshold < 1:
        raise ValueError(f"soft_threshold must be >= 1, got {soft_threshold}")
    if hard_threshold < soft_threshold:
        raise ValueError(
            f"hard_threshold ({hard_threshold}) must be >= soft_threshold ({soft_threshold})"
        )

    # Validate required columns
    required_cols = {"high", "low", "open", "close"}
    missing_cols = required_cols - set(df_15m.columns)
    if missing_cols:
        raise ValueError(
            f"Missing required column(s): {missing_cols}. "
            f"Available columns: {list(df_15m.columns)}"
        )

    # Handle empty DataFrame
    if len(df_15m) == 0:
        return ChopSeverity.NONE, 0

    # Calculate wick sizes and body size (same as detect_price_chop_15m)
    upper_wick = df_15m["high"] - df_15m[["open", "close"]].max(axis=1)
    lower_wick = df_15m[["open", "close"]].min(axis=1) - df_15m["low"]
    body_size = (df_15m["close"] - df_15m["open"]).abs()

    # ATR-based noise filter: ignore small candles
    is_noise_candle = pd.Series([False] * len(df_15m), index=df_15m.index)
    if atr is not None and atr > 0:
        candle_range = df_15m["high"] - df_15m["low"]
        min_candle_size = atr * min_candle_size_ratio
        is_noise_candle = candle_range < min_candle_size

    # Calculate wick ratio
    wick_ratio = pd.Series(index=df_15m.index, dtype=float)

    # Handle zero body (doji) - treat as chop
    zero_body_mask = body_size == 0
    wick_ratio[zero_body_mask] = float("inf")

    # Calculate normal ratio for non-zero bodies
    non_zero_mask = ~zero_body_mask
    wick_ratio[non_zero_mask] = (
        upper_wick[non_zero_mask] + lower_wick[non_zero_mask]
    ) / body_size[non_zero_mask]

    # Identify individual chop candles (excluding noise candles)
    is_chop_candle = (wick_ratio >= wick_threshold) & (~is_noise_candle)
    is_chop_candle = is_chop_candle.fillna(False)

    # Track extreme wick ratios for severity escalation
    has_extreme_wicks = (wick_ratio >= extreme_wick_ratio) & (~is_noise_candle)
    has_extreme_wicks = has_extreme_wicks.fillna(False)

    # Count consecutive chop candles from the end
    consecutive_count = 0
    has_extreme_in_sequence = False

    for i in range(len(df_15m) - 1, -1, -1):
        if is_chop_candle.iloc[i]:
            consecutive_count += 1
            if has_extreme_wicks.iloc[i]:
                has_extreme_in_sequence = True
        else:
            break  # Stop at first non-chop candle

    # Classify severity based on consecutive count
    if consecutive_count == 0:
        severity = ChopSeverity.NONE
    elif consecutive_count < soft_threshold:
        # 1-2 consecutive: NONE (not enough to be significant)
        severity = ChopSeverity.NONE
    elif consecutive_count < hard_threshold:
        # 3-4 consecutive: SOFT_CHOP
        severity = ChopSeverity.SOFT_CHOP
        # Escalate to HARD_CHOP if extreme wicks present
        if has_extreme_in_sequence:
            severity = ChopSeverity.HARD_CHOP
            logger.debug(
                f"Chop severity escalated to HARD_CHOP due to extreme wicks "
                f"(count={consecutive_count}, extreme_wick_ratio={extreme_wick_ratio})"
            )
    else:
        # 5+ consecutive: HARD_CHOP
        severity = ChopSeverity.HARD_CHOP

    logger.debug(
        f"Chop severity: {severity.value} | consecutive_count={consecutive_count} | "
        f"extreme_wicks={has_extreme_in_sequence} | "
        f"thresholds: soft={soft_threshold}, hard={hard_threshold}"
    )

    return severity, consecutive_count


def detect_sweep_against_trend(
    bias: str,
    sweep_events: pd.Series,
    sweep_success: pd.Series | None = None,
) -> tuple[bool, str | None]:
    """Detect if recent liquidity sweep opposes the established trend.

    A sweep against trend is a potential reversal signal and creates conflict
    with the established directional bias.

    Args:
        bias: Current HTF bias ("bullish", "bearish", "neutral")
        sweep_events: Series with sweep labels from detect_liquidity_sweeps()
        sweep_success: Optional Series indicating if sweep was successful

    Returns:
        Tuple of (is_conflict, reason):
        - is_conflict: True if sweep opposes trend
        - reason: Description of conflict, or None if no conflict

    Logic:
        - Bullish trend + successful sweep_low = conflict (reversal signal)
        - Bearish trend + successful sweep_high = conflict (reversal signal)
        - Failed sweeps don't count (continuation setup)
        - Neutral bias doesn't trigger conflicts
        - Check most recent sweep only

    Example:
        >>> events = pd.Series([None, None, "sweep_low"])
        >>> success = pd.Series([None, None, True])
        >>> detect_sweep_against_trend("bullish", events, success)
        (True, "Bullish bias with successful sweep_low (reversal signal)")
    """
    # Neutral bias doesn't conflict
    if bias == "neutral":
        return False, None

    # Handle empty or all-None sweep events
    if sweep_events.empty or sweep_events.isna().all():
        return False, None

    # Find most recent sweep
    recent_sweeps = sweep_events[sweep_events.notna()]
    if len(recent_sweeps) == 0:
        return False, None

    most_recent_idx = recent_sweeps.index[-1]
    most_recent_sweep = recent_sweeps.iloc[-1]

    # Check if sweep was successful (if success data provided)
    if sweep_success is not None:
        sweep_was_successful = sweep_success.loc[most_recent_idx]
        # If not successful or unknown, no conflict (treat as continuation)
        if pd.isna(sweep_was_successful) or not sweep_was_successful:
            return False, None
    # If no success data, assume sweep is significant

    # Check for conflicts
    if bias == "bullish" and most_recent_sweep == "sweep_low":
        reason = "Bullish bias with successful sweep_low (reversal signal)"
        logger.debug(f"Sweep conflict detected: {reason}")
        return True, reason

    if bias == "bearish" and most_recent_sweep == "sweep_high":
        reason = "Bearish bias with successful sweep_high (reversal signal)"
        logger.debug(f"Sweep conflict detected: {reason}")
        return True, reason

    # No conflict (sweep aligns with trend)
    return False, None


def detect_structure_invalidation(
    prev_structure: str | None,
    curr_structure: str | None,
    bias: str,
) -> tuple[bool, str | None]:
    """Detect if structure transition invalidates HTF bias.

    Only invalidates on real structure breaks, not micro volatility.

    Valid invalidations (per SOP):
    - Bullish bias + (HH->LL or HL->LL) = invalidate
    - Bearish bias + (LH->HH or LL->HH) = invalidate

    NOT invalidations (micro volatility):
    - HL->LH (single step, not a break)
    - LH->HL (single step, not a break)
    - Same structure continuation (HH->HH, LL->LL, etc.)

    Args:
        prev_structure: Previous structure label (HH, HL, LH, LL, or None)
        curr_structure: Current structure label (HH, HL, LH, LL, or None)
        bias: Current HTF bias ("bullish", "bearish", "neutral")

    Returns:
        Tuple of (is_invalidated, reason):
        - is_invalidated: True if structure transition invalidates bias
        - reason: Description of invalidation, or None if not invalidated

    Example:
        >>> detect_structure_invalidation("HH", "LL", "bullish")
        (True, "Bullish bias invalidated: HH -> LL (structure break)")
    """
    # Neutral bias cannot be invalidated
    if bias == "neutral":
        return False, None

    # Handle None values
    if prev_structure is None or curr_structure is None:
        return False, None

    # No change = no invalidation
    if prev_structure == curr_structure:
        return False, None

    # Define bullish and bearish labels
    bullish_labels = {"HH", "HL"}
    bearish_labels = {"LH", "LL"}

    # Bullish bias invalidations
    if bias == "bullish":
        # HH -> LL or HL -> LL = bullish to bearish flip
        if prev_structure in bullish_labels and curr_structure == "LL":
            reason = f"Bullish bias invalidated: {prev_structure} -> {curr_structure} (structure break)"
            logger.warning(reason)
            return True, reason

    # Bearish bias invalidations
    elif bias == "bearish":
        # LH -> HH or LL -> HH = bearish to bullish flip
        if prev_structure in bearish_labels and curr_structure == "HH":
            reason = f"Bearish bias invalidated: {prev_structure} -> {curr_structure} (structure break)"
            logger.warning(reason)
            return True, reason

    # All other transitions are NOT invalidations
    # Examples:
    # - HL -> LH (single step, micro volatility)
    # - HH -> HL (bullish continuation)
    # - LL -> LH (bearish continuation)
    return False, None
