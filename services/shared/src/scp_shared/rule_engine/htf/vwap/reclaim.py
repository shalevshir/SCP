"""VWAP Reclaim Detection - proper sequence validation.

Implements the complete VWAP reclaim sequence:
1. Price below VWAP
2. Liquidity sweep
3. Displacement candle
4. Close above VWAP

A valid VWAP_RECLAIM setup requires ALL of these components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import pandas as pd
from scp_shared.common.logger import get_logger

from scp_shared.rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


@dataclass
class VWAPReclaimState:
    """State tracking for VWAP reclaim sequence (direction-agnostic).

    Attributes:
        started_on_dwell_side: Price was on dwell side (below for long, above for short)
        sweep_detected: Liquidity sweep occurred
        sweep_bar_idx: Bar index where sweep occurred
        displacement_detected: Strong displacement move present
        reclaim_confirmed: Close on reclaim side after complete sequence
    """

    started_on_dwell_side: bool = False
    sweep_detected: bool = False
    sweep_bar_idx: int | None = None
    displacement_detected: bool = False
    reclaim_confirmed: bool = False

    # Migration: backward-compatible alias for started_below
    @property
    def started_below(self) -> bool:
        """Deprecated alias for started_on_dwell_side (backward compatibility)."""
        return self.started_on_dwell_side

    @started_below.setter
    def started_below(self, value: bool) -> None:
        """Deprecated setter for started_below (backward compatibility)."""
        self.started_on_dwell_side = value


@dataclass
class ExpansionGate:
    """Expansion gate evaluation for VWAP_RECLAIM entry readiness.

    Tracks which expansion signals are present to determine if market is
    resolving out of compression, making it safe to enter VWAP_RECLAIM trades.

    Attributes:
        passed: True if any expansion signal is present
        recent_bos: True if BOS within recency threshold
        range_expansion: True if current bar range expanded vs recent median
        atr_expansion: True if ATR is expanding (ratio > threshold)
        displacement_candle: True if strong displacement detected
        reasons: List of string reasons for expansion (e.g., ["recent_bos", "range_expansion"])
    """

    passed: bool = False
    recent_bos: bool = False
    range_expansion: bool = False
    atr_expansion: bool = False
    displacement_candle: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class ReclaimContextResult:
    """Result of VWAP_RECLAIM context validity check.

    Determines if the market context allows VWAP_RECLAIM signals to be considered.
    Context validity is checked BEFORE entry readiness.

    Attributes:
        context_valid: True if context prerequisites are met (safety gates only)
        reason: Rejection reason if context is invalid (safety issues only)
        sweep_detected: True if liquidity sweep was detected
        structure_clarity: Structure clarity value that was checked
        quality_flags: Dict of quality issues for penalty calculation (not safety)
            - no_sweep: bool - no liquidity sweep detected
            - low_clarity: bool - structure clarity below threshold
            - no_bos: bool - no BOS detected
            - bos_stale: bool - BOS age exceeds threshold
    """

    context_valid: bool
    reason: str | None = None
    sweep_detected: bool = False
    structure_clarity: float = 0.0
    quality_flags: dict[str, bool] = field(default_factory=dict)


@dataclass
class EntryReadinessResult:
    """Result of VWAP_RECLAIM entry readiness evaluation.

    Determines if a valid context is ready for trade execution.
    Entry readiness is checked AFTER context validity passes.

    Attributes:
        entry_ready: True if entry timing is appropriate
        expansion_satisfied: True if expansion gate passed
        expansion_reasons: List of expansion signals detected
        bos_age: Age of most recent BOS (bars since BOS)
        penalties: Dict of penalty types to penalty values (negative floats)
    """

    entry_ready: bool
    expansion_satisfied: bool = False
    expansion_reasons: list[str] = field(default_factory=list)
    bos_age: int | None = None
    penalties: dict[str, float] = field(default_factory=dict)


def validate_reclaim_context(
    htf_bias: HTFBias,
    features: pd.Series | None = None,
) -> ReclaimContextResult:
    """Validate that market context allows VWAP_RECLAIM signals to be considered.

    Context validation checks SAFETY gates only. Quality issues are returned as flags
    for penalty calculation in scoring, not hard rejection.

    SAFETY gates (hard rejection):
        1. BOS/CHoCH direction mismatch with trade direction
        2. Structure conflict flag (mixed HH/LL signals)
        3. Structure label conflicts with trade direction
        4. Minimum VWAP deviation not met (entry too close to VWAP)

    QUALITY flags (returned for penalty, not rejected):
        1. No liquidity sweep detected
        2. Structure clarity < 0.4
        3. No BOS detected
        4. BOS age exceeds threshold

    Args:
        htf_bias: HTFBias object to validate
        features: Optional feature series for additional context

    Returns:
        ReclaimContextResult with validation outcome and quality flags

    Example:
        >>> result = validate_reclaim_context(htf_bias, features)
        >>> if result.context_valid:
        ...     # Safety gates passed, check quality_flags for penalties
        ...     if result.quality_flags.get("no_sweep"):
        ...         # Apply penalty in scoring
        ...         pass
    """
    CLARITY_THRESHOLD = 0.4
    # Minimum VWAP deviation required for entry (percentage)
    # SOP requires price to have "traded below/above VWAP for 30-60 min"
    # This translates to meaningful deviation from VWAP, not touching it
    MIN_VWAP_DEVIATION_PCT = 0.15  # 0.15% minimum deviation

    # HARD REJECT: Check if structure_1h is null
    # HTF bias must only be computed when BOTH 1H and 15M votes are available
    # If structure_1h is null, we're trading 15M-only with fake "HTF" alignment
    structure_1h = htf_bias.structure_1h
    structure_1h_is_null = (
        structure_1h is None
        or (isinstance(structure_1h, float) and pd.isna(structure_1h))
        or structure_1h == ""
    )
    if structure_1h_is_null:
        logger.warning(
            f"VWAP_RECLAIM HARD REJECT: structure_1h is null "
            f"(raw value: {structure_1h!r}, 15m: {htf_bias.structure_15m!r})"
        )
        # Return rejection with explicit reason (no exception in live paths)
        return ReclaimContextResult(
            context_valid=False,
            reason="structure_1h_null: HTF 1H structure missing - cannot validate HTF alignment",
            sweep_detected=False,
            structure_clarity=htf_bias.structure_clarity,
            quality_flags={
                "no_sweep": True,
                "low_clarity": False,
                "no_bos": True,
                "bos_stale": False,
            },
        )

    # Get structure_clarity from features (1M) as primary source
    # Fallback to htf_bias.structure_clarity (1H) if features not available
    if features is not None:
        structure_clarity = features.get(
            "structure_clarity", htf_bias.structure_clarity
        )
    else:
        structure_clarity = htf_bias.structure_clarity

    # Get sweep info from features if available (more responsive)
    # Check both current bar sweep AND recent sweep via sweep_age
    SWEEP_RECENCY_THRESHOLD = 20  # Sweep within last 20 bars is considered recent

    if features is not None:
        # Current bar sweep
        sweep_on_this_bar = (
            features.get("liquidity_sweep", False) or htf_bias.liquidity_sweep_detected
        )
        # Recent sweep via sweep_age
        sweep_age = features.get("sweep_age")
        sweep_recent = (
            sweep_age is not None
            and not pd.isna(sweep_age)
            and int(sweep_age) <= SWEEP_RECENCY_THRESHOLD
        )
        sweep_detected = sweep_on_this_bar or sweep_recent
        # BOS exists if: bos_recent=True, htf_bias.bos_detected=True, OR bos_age is valid
        bos_age_val = features.get("bos_age")
        bos_age_valid = bos_age_val is not None and not pd.isna(bos_age_val)
        bos_detected = (
            features.get("bos_recent", False) or htf_bias.bos_detected or bos_age_valid
        )
    else:
        sweep_detected = htf_bias.liquidity_sweep_detected
        bos_detected = htf_bias.bos_detected
        sweep_age = None
        bos_age_valid = False

    clarity_str = "None" if structure_clarity is None else f"{structure_clarity:.2f}"
    logger.info(
        f"VWAP_RECLAIM context check: "
        f"sweep={sweep_detected}, sweep_age={sweep_age}, "
        f"clarity={clarity_str}, "
        f"bos={bos_detected}"
    )

    # Initialize quality flags (for penalty calculation, not rejection)
    quality_flags = {
        "no_sweep": not sweep_detected,
        "low_clarity": (structure_clarity or 0.0) < CLARITY_THRESHOLD,
        "no_bos": not bos_detected,
        "bos_stale": False,  # Will be set based on BOS age if available
    }

    # Check BOS age for staleness flag
    if bos_detected and features is not None:
        bos_age = features.get("bos_age")
        if bos_age is not None and not pd.isna(bos_age):
            quality_flags["bos_stale"] = bos_age > 15  # Staleness threshold

    # MANDATORY SAFETY CHECK: Structure label MUST be available (moved OUTSIDE features block)
    # This is checked BEFORE other gates to ensure no bypass when features is None
    direction = htf_bias.direction
    structure_label = None
    if features is not None:
        # Get structure_label, handling pd.NA properly (can't use 'or' with NA)
        raw_label = features.get("structure_label")
        if (
            raw_label is None
            or (isinstance(raw_label, float) and pd.isna(raw_label))
            or pd.isna(raw_label)
        ):
            raw_label = features.get("last_structure_label")
        structure_label = raw_label

    # HARD REJECT if no structure label available at decision time
    # No guessing, no defaulting, no silent pass-through
    is_label_missing = structure_label is None or (
        isinstance(structure_label, float) and pd.isna(structure_label)
    )
    # Handle pandas NA type explicitly
    try:
        if pd.isna(structure_label):
            is_label_missing = True
    except (TypeError, ValueError):
        pass

    if is_label_missing:
        logger.warning(
            "VWAP_RECLAIM HARD REJECT: no structure_label available at decision time"
        )
        return ReclaimContextResult(
            context_valid=False,
            reason="HARD REJECT: No structure label available - cannot safely manage trade",
            sweep_detected=sweep_detected,
            structure_clarity=structure_clarity,
            quality_flags=quality_flags,
        )

    # Check structure_label direction alignment (applies to both long and short)
    if direction == "long" and structure_label in ("LH", "LL"):
        logger.debug(
            f"VWAP_RECLAIM SAFETY REJECT: bearish structure_label={structure_label} "
            f"conflicts with long direction"
        )
        return ReclaimContextResult(
            context_valid=False,
            reason=f"SAFETY: Bearish micro structure ({structure_label}) conflicts with long",
            sweep_detected=sweep_detected,
            structure_clarity=structure_clarity,
            quality_flags=quality_flags,
        )
    elif direction == "short" and structure_label in ("HH", "HL"):
        logger.debug(
            f"VWAP_RECLAIM SAFETY REJECT: bullish structure_label={structure_label} "
            f"conflicts with short direction"
        )
        return ReclaimContextResult(
            context_valid=False,
            reason=f"SAFETY: Bullish micro structure ({structure_label}) conflicts with short",
            sweep_detected=sweep_detected,
            structure_clarity=structure_clarity,
            quality_flags=quality_flags,
        )

    # SAFETY CHECK 1: BOS or CHoCH alignment with trade direction
    # Only reject when there's an EXPLICIT, RECENT directional conflict
    # Allow through when:
    # - BOS direction is unknown (None) - matches backtester where micro_bos was null
    # - BOS is stale (old) - not relevant to current market structure
    if features is not None:
        bos_direction = features.get("bos_direction")
        bos_recent = features.get("bos_recent", False)
        bos_age = features.get("bos_age")
        choch_detected = features.get("choch_detected", False)
        choch_direction = features.get("choch_direction")

        direction = htf_bias.direction

        # Determine if BOS is stale (>15 bars old) - stale BOS should not cause rejection
        bos_is_stale = False
        if bos_age is not None and not pd.isna(bos_age):
            bos_is_stale = int(bos_age) > 15

        logger.debug(
            f"VWAP_RECLAIM direction check: direction={direction}, "
            f"bos_direction={bos_direction}, bos_recent={bos_recent}, bos_age={bos_age}, "
            f"bos_stale={bos_is_stale}, choch={choch_detected}, choch_dir={choch_direction}"
        )

        # Only reject if there's an EXPLICIT directional conflict AND BOS is recent
        # None/unknown BOS direction is allowed (matches backtester where micro_bos was null)
        # Stale BOS is also allowed through (not relevant to current setup)
        if direction == "long":
            # Reject only if BOS is explicitly bearish AND recent AND no bullish CHoCH
            has_bearish_conflict = (
                bos_direction == "bearish"
                and not bos_is_stale  # Only reject if BOS is recent
                and not (choch_detected and choch_direction == "bullish")
            )
            if has_bearish_conflict:
                logger.debug(
                    f"VWAP_RECLAIM SAFETY REJECT: recent bearish BOS conflicts with long reclaim"
                )
                return ReclaimContextResult(
                    context_valid=False,
                    reason=f"SAFETY: Recent bearish BOS conflicts with long reclaim "
                    f"(bos={bos_direction}, age={bos_age}, choch={choch_direction})",
                    sweep_detected=sweep_detected,
                    structure_clarity=structure_clarity,
                    quality_flags=quality_flags,
                )
        elif direction == "short":
            # Reject only if BOS is explicitly bullish AND recent AND no bearish CHoCH
            has_bullish_conflict = (
                bos_direction == "bullish"
                and not bos_is_stale  # Only reject if BOS is recent
                and not (choch_detected and choch_direction == "bearish")
            )
            if has_bullish_conflict:
                logger.debug(
                    f"VWAP_RECLAIM SAFETY REJECT: recent bullish BOS conflicts with short reclaim"
                )
                return ReclaimContextResult(
                    context_valid=False,
                    reason=f"SAFETY: Recent bullish BOS conflicts with short reclaim "
                    f"(bos={bos_direction}, age={bos_age}, choch={choch_direction})",
                    sweep_detected=sweep_detected,
                    structure_clarity=structure_clarity,
                    quality_flags=quality_flags,
                )

        # SAFETY CHECK 2: Structure conflict
        # This is a SAFETY gate - conflict indicates unreliable structure
        structure_conflict = features.get("structure_conflict_flag", False)
        if structure_conflict:
            logger.debug("VWAP_RECLAIM SAFETY REJECT: structure conflict flag is True")
            return ReclaimContextResult(
                context_valid=False,
                reason="SAFETY: Structure conflict detected (mixed HH/LL signals)",
                sweep_detected=sweep_detected,
                structure_clarity=structure_clarity,
                quality_flags=quality_flags,
            )

        # SAFETY CHECK 3: Minimum VWAP deviation (structure_label check moved outside features block)
        # Entry should not be at/near VWAP - needs meaningful deviation
        # SOP requires price to "trade below/above VWAP" before reclaim
        vwap_deviation = features.get("vwap_deviation")
        if vwap_deviation is not None and not pd.isna(vwap_deviation):
            if abs(vwap_deviation) < MIN_VWAP_DEVIATION_PCT:
                logger.debug(
                    f"VWAP_RECLAIM SAFETY REJECT: VWAP deviation {vwap_deviation:.3f}% "
                    f"< minimum {MIN_VWAP_DEVIATION_PCT}% (entry too close to VWAP)"
                )
                return ReclaimContextResult(
                    context_valid=False,
                    reason=f"SAFETY: VWAP deviation too small ({vwap_deviation:.3f}% < {MIN_VWAP_DEVIATION_PCT}%)",
                    sweep_detected=sweep_detected,
                    structure_clarity=structure_clarity,
                    quality_flags=quality_flags,
                )

    # All SAFETY gates passed - return valid context with quality flags
    logger.info(
        f"VWAP_RECLAIM context VALID (safety gates passed), "
        f"quality_flags={quality_flags}"
    )
    return ReclaimContextResult(
        context_valid=True,
        reason=None,
        sweep_detected=sweep_detected,
        structure_clarity=structure_clarity,
        quality_flags=quality_flags,
    )


def evaluate_entry_readiness(
    features: pd.Series,
    htf_bias: HTFBias,
    config: dict,
) -> EntryReadinessResult:
    """Evaluate if a valid VWAP_RECLAIM context is ready for trade execution.

    Entry readiness checks timing factors that determine if NOW is the right
    moment to enter. Unlike context validation, these can apply penalties rather
    than hard rejections.

    Requirements (for full readiness):
        1. Expansion gate must pass (any expansion signal present)
        2. BOS recency affects score (penalty if stale, but not rejection)

    Args:
        features: Feature series with BOS age and expansion signals
        htf_bias: HTFBias object with structure information
        config: Configuration dict with thresholds

    Returns:
        EntryReadinessResult with readiness evaluation

    Example:
        >>> config = {"bos_recency_threshold": 10, ...}
        >>> result = evaluate_entry_readiness(features, htf_bias, config)
        >>> if result.entry_ready:
        ...     # Entry timing is good
        ...     if result.penalties:
        ...         # Apply score penalties
        ...         pass
    """
    # Evaluate expansion gate
    expansion_gate = evaluate_expansion_gate(features, htf_bias, config)

    # Get BOS age
    bos_age = features.get("bos_age")
    if bos_age is None or pd.isna(bos_age):
        bos_age = htf_bias.bars_since_bos

    # Calculate penalties for late entry
    penalties: dict[str, float] = {}
    bos_recency_threshold = config.get("bos_recency_threshold", 10)

    if bos_age is not None and bos_age > bos_recency_threshold:
        # Apply graduated penalties based on BOS staleness
        if bos_age <= 15:
            penalties["late_bos"] = -0.5
        elif bos_age <= 20:
            penalties["late_bos"] = -1.0
        else:
            penalties["late_bos"] = -1.5
        logger.debug(f"Late BOS penalty: {penalties['late_bos']} (age={bos_age})")

    # Entry is ready if expansion gate passed
    # Even with stale BOS, expansion signals indicate safe entry timing
    entry_ready = expansion_gate.passed

    if entry_ready:
        logger.info(
            f"Entry readiness: READY (expansion satisfied, "
            f"bos_age={bos_age}, penalties={penalties})"
        )
    else:
        logger.debug(
            f"Entry readiness: NOT READY (no expansion signals, bos_age={bos_age})"
        )

    return EntryReadinessResult(
        entry_ready=entry_ready,
        expansion_satisfied=expansion_gate.passed,
        expansion_reasons=expansion_gate.reasons,
        bos_age=bos_age,
        penalties=penalties,
    )


def detect_vwap_reclaim(
    df: pd.DataFrame,
    htf_bias: HTFBias,
    lookback: int = 5,
) -> tuple[bool, VWAPReclaimState]:
    """Detect complete VWAP reclaim sequence (direction-aware).

    Scans the last N bars to verify:
    LONG: 1. Price started below VWAP, 2. Cross from below to above, 3. Close above
    SHORT: 1. Price started above VWAP, 2. Cross from above to below, 3. Close below
    Plus: Liquidity sweep detected and displacement candle present (both directions)

    Args:
        df: DataFrame with OHLC + VWAP columns
        htf_bias: HTFBias object with sweep detection and direction
        lookback: Number of bars to scan (default: 5)

    Returns:
        Tuple of (is_valid_reclaim, state)

    Example:
        >>> is_reclaim, state = detect_vwap_reclaim(df, htf_bias, lookback=5)
        >>> if is_reclaim:
        ...     print("Valid VWAP reclaim detected")
    """
    state = VWAPReclaimState()

    # Get trade direction from HTF bias
    direction = htf_bias.direction  # "long" or "short"

    # Validate required columns
    required_cols = {"open", "high", "low", "close", "vwap"}
    if not required_cols.issubset(df.columns):
        logger.warning(f"Missing required columns: {required_cols - set(df.columns)}")
        return False, state

    # Need at least lookback bars + dwell bars
    MIN_DWELL_BARS = 30  # SOP: 30-60 bars minimum
    min_required_bars = lookback + MIN_DWELL_BARS

    if len(df) < lookback:
        return False, state

    # DWELL GATE: Check if price spent sufficient time on dwell side
    # This prevents premature reclaim signals on brief touches of VWAP
    if len(df) >= min_required_bars:
        # Count bars spent on dwell side in the window BEFORE the recent lookback
        dwell_df = df.iloc[-(lookback + MIN_DWELL_BARS) : -lookback]

        if direction == "long":
            dwell_bars = (dwell_df["close"] < dwell_df["vwap"]).sum()
        else:  # short
            dwell_bars = (dwell_df["close"] > dwell_df["vwap"]).sum()

        if dwell_bars < MIN_DWELL_BARS:
            logger.debug(
                f"VWAP_RECLAIM rejected: insufficient dwell time "
                f"({dwell_bars} < {MIN_DWELL_BARS} bars on {'below' if direction == 'long' else 'above'} VWAP)"
            )
            return False, state

        logger.debug(
            f"VWAP_RECLAIM dwell gate passed: {dwell_bars} bars on dwell side "
            f"(direction={direction})"
        )

    # Get recent bars
    recent_df = df.iloc[-lookback:]

    # Check 1: Price was on dwell side (below for long, above for short)
    if direction == "long":
        was_on_side = (recent_df["close"] < recent_df["vwap"]).any()
    else:  # short
        was_on_side = (recent_df["close"] > recent_df["vwap"]).any()

    # Convert numpy.bool_ to Python bool for proper identity comparison
    state.started_on_dwell_side = bool(was_on_side)

    if not was_on_side:
        logger.debug(
            f"VWAP_RECLAIM rejected: price not on dwell side (direction={direction})"
        )
        return False, state

    # Check 2: Liquidity sweep detected (from HTF bias)
    state.sweep_detected = htf_bias.liquidity_sweep_detected

    if not state.sweep_detected:
        return False, state

    # Check 3: Displacement candle present
    # Find the bar that crossed VWAP in the correct direction
    reclaim_bar_idx = None
    for i in range(len(recent_df) - 1):
        curr_close = recent_df["close"].iloc[i]
        next_close = recent_df["close"].iloc[i + 1]
        curr_vwap = recent_df["vwap"].iloc[i]
        next_vwap = recent_df["vwap"].iloc[i + 1]

        # Direction-aware cross detection
        if direction == "long":
            # Crossed from below to above
            crossed = curr_close < curr_vwap and next_close > next_vwap
        else:  # short
            # Crossed from above to below
            crossed = curr_close > curr_vwap and next_close < next_vwap

        if crossed:
            reclaim_bar_idx = i + 1  # The bar that crossed
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
            # Convert numpy.bool_ to Python bool for proper identity comparison
            state.displacement_detected = bool(reclaim_body > avg_body)
        else:
            state.displacement_detected = False
    else:
        state.displacement_detected = False

    if not state.displacement_detected:
        return False, state

    # Check 4: Currently closed on reclaim side (above for long, below for short)
    current_close = recent_df["close"].iloc[-1]
    current_vwap = recent_df["vwap"].iloc[-1]

    # Convert numpy.bool_ to Python bool for proper identity comparison
    if direction == "long":
        state.reclaim_confirmed = bool(current_close > current_vwap)
    else:  # short
        state.reclaim_confirmed = bool(current_close < current_vwap)

    if not state.reclaim_confirmed:
        return False, state

    # All checks passed
    logger.debug(
        f"Valid VWAP reclaim detected (direction={direction}): "
        f"started_on_dwell_side={state.started_on_dwell_side}, "
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
    2. Structure clarity >= 0.4 (lowered from 0.5)
    3. BOS detected recently (within 20 bars, increased from 15)
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
    # Thresholds (loosened for better signal detection)
    CLARITY_THRESHOLD = 0.4  # Lowered from 0.5
    BOS_STALENESS_LIMIT = 20  # Increased from 15

    # Get structure_clarity from features (1M) as primary source (warms up faster)
    # Fallback to htf_bias.structure_clarity (1H) if features not available
    if features is not None:
        structure_clarity = features.get(
            "structure_clarity", htf_bias.structure_clarity
        )
    else:
        structure_clarity = htf_bias.structure_clarity

    # Similarly, get BOS/sweep info from features if available (more responsive)
    if features is not None:
        bos_age = features.get("bos_age")
        if bos_age is not None and not pd.isna(bos_age):
            bars_since_bos = int(bos_age)
            bos_age_valid = True
        else:
            bars_since_bos = htf_bias.bars_since_bos
            bos_age_valid = False
        # BOS exists if: bos_recent=True, htf_bias.bos_detected=True, OR bos_age is valid
        bos_detected = (
            features.get("bos_recent", False) or htf_bias.bos_detected or bos_age_valid
        )
        sweep_detected = (
            features.get("liquidity_sweep", False) or htf_bias.liquidity_sweep_detected
        )
    else:
        bos_detected = htf_bias.bos_detected
        bars_since_bos = htf_bias.bars_since_bos
        sweep_detected = htf_bias.liquidity_sweep_detected

    # Get BOS/CHoCH direction early for logging
    bos_direction_log = features.get("bos_direction") if features is not None else None
    choch_detected_log = (
        features.get("choch_detected", False) if features is not None else False
    )
    choch_direction_log = (
        features.get("choch_direction") if features is not None else None
    )

    # Log all values for debugging
    logger.info(
        f"VWAP_RECLAIM prereq check: "
        f"sweep={sweep_detected}, "
        f"clarity={structure_clarity:.2f}, "
        f"bos={bos_detected}, "
        f"bars_since_bos={bars_since_bos}, "
        f"direction={htf_bias.direction}, "
        f"bos_dir={bos_direction_log}, "
        f"choch={choch_detected_log}/{choch_direction_log}"
    )

    # Check 1: Liquidity sweep
    if not sweep_detected:
        logger.debug("VWAP_RECLAIM rejected: no liquidity sweep detected")
        return False, "No liquidity sweep detected"

    # Check 2: Structure clarity (lowered threshold)
    if structure_clarity < CLARITY_THRESHOLD:
        logger.debug(
            f"VWAP_RECLAIM rejected: clarity {structure_clarity:.2f} < {CLARITY_THRESHOLD}"
        )
        return (
            False,
            f"Structure clarity too low: {structure_clarity:.2f} < {CLARITY_THRESHOLD}",
        )

    # Check 3: Recent BOS
    if not bos_detected:
        logger.debug("VWAP_RECLAIM rejected: no BOS detected")
        return False, "No BOS detected"

    if bars_since_bos is None:
        logger.debug("VWAP_RECLAIM rejected: BOS timing unknown")
        return False, "BOS timing unknown"

    if bars_since_bos > BOS_STALENESS_LIMIT:
        logger.debug(
            f"VWAP_RECLAIM rejected: BOS too stale ({bars_since_bos} > {BOS_STALENESS_LIMIT})"
        )
        return (
            False,
            f"BOS too stale: {bars_since_bos} bars ago (>{BOS_STALENESS_LIMIT})",
        )

    # Enhanced checks if features are provided
    if features is not None:
        # Check 4: BOS or CHoCH alignment with trade direction
        # Only reject when there's an EXPLICIT directional conflict
        # Allow through when BOS direction is unknown (None) - matches backtester behavior
        bos_direction = features.get("bos_direction")
        bos_age = features.get("bos_age")
        choch_detected = features.get("choch_detected", False)
        choch_direction = features.get("choch_direction")

        direction = htf_bias.direction

        # Determine if BOS is stale (>15 bars old) - stale BOS should not cause rejection
        # This matches the staleness logic in validate_reclaim_context for consistency
        bos_is_stale = False
        if bos_age is not None and not pd.isna(bos_age):
            bos_is_stale = int(bos_age) > 15

        logger.debug(
            f"VWAP_RECLAIM direction check: direction={direction}, "
            f"bos_direction={bos_direction}, bos_age={bos_age}, bos_stale={bos_is_stale}, "
            f"choch={choch_detected}, choch_dir={choch_direction}"
        )

        # Only reject if there's an EXPLICIT directional conflict AND BOS is recent
        # None/unknown BOS direction is allowed (matches backtester where micro_bos was null)
        # Stale BOS (>15 bars) is also allowed through (not relevant to current setup)
        if direction == "long":
            has_bearish_conflict = (
                bos_direction == "bearish"
                and not bos_is_stale  # Only reject if BOS is recent
                and not (choch_detected and choch_direction == "bullish")
            )
            if has_bearish_conflict:
                logger.debug(
                    f"VWAP_RECLAIM rejected: recent bearish BOS conflicts with long reclaim"
                )
                return (
                    False,
                    f"Recent bearish BOS conflicts with long reclaim "
                    f"(bos={bos_direction}, age={bos_age}, choch={choch_direction})",
                )
        elif direction == "short":
            has_bullish_conflict = (
                bos_direction == "bullish"
                and not bos_is_stale  # Only reject if BOS is recent
                and not (choch_detected and choch_direction == "bearish")
            )
            if has_bullish_conflict:
                logger.debug(
                    f"VWAP_RECLAIM rejected: recent bullish BOS conflicts with short reclaim"
                )
                return (
                    False,
                    f"Recent bullish BOS conflicts with short reclaim "
                    f"(bos={bos_direction}, age={bos_age}, choch={choch_direction})",
                )

        # Check 5: Reject if excessive structure conflict
        # Note: VWAP_RECLAIM can work during micro chop, but not during conflict
        structure_conflict = features.get("structure_conflict_flag", False)
        if structure_conflict:
            logger.debug("VWAP_RECLAIM rejected: structure conflict flag is True")
            return False, "Structure conflict detected (mixed HH/LL signals)"

        # Check 6: Noise zone now handled as score penalty (not hard-block)
        # See calculate_noise_penalty() in scoring.py for setup-aware noise handling
        # Note: VWAP_RECLAIM allows micro chop, and noise is now penalized not blocked

    # All prerequisites met
    logger.info("VWAP_RECLAIM prerequisites PASSED")
    return True, None


def evaluate_expansion_gate(
    features: pd.Series,
    htf_bias: HTFBias,
    config: dict,
) -> ExpansionGate:
    """Evaluate expansion gate for VWAP_RECLAIM entry readiness.

    Checks for expansion signals that indicate market is resolving out of
    compression, making it appropriate timing for VWAP_RECLAIM entry.

    Args:
        features: Feature series containing BOS age, expansion signals, etc.
        htf_bias: HTFBias object with structure information
        config: Configuration dict with expansion gate thresholds:
            - bos_recency_threshold: Maximum BOS age to consider recent (default: 10)
            - range_expansion_ratio: Range expansion ratio threshold (default: 1.5)
            - atr_expansion_threshold: ATR ratio threshold for expansion (default: 0.7)
            - displacement_body_ratio: Body ratio for displacement (default: 2.0)

    Returns:
        ExpansionGate object with expansion evaluation results

    Expansion signals (any one qualifies):
        1. Recent BOS: BOS detected within bos_recency_threshold bars
        2. Range expansion: Detected via StructureContext.detect_expansion()
        3. ATR expansion: Detected via StructureContext.detect_expansion()
        4. Displacement candle: Detected via StructureContext.detect_expansion()

    Example:
        >>> config = {"bos_recency_threshold": 10, ...}
        >>> gate = evaluate_expansion_gate(features, htf_bias, config)
        >>> if gate.passed:
        ...     print(f"Expansion detected: {gate.reasons}")
    """
    gate = ExpansionGate()

    # Get config thresholds
    bos_recency_threshold = config.get("bos_recency_threshold", 10)

    # Check 1: Recent BOS (from HTF bias or features)
    # Prefer features (1M) as they're more responsive than HTF (1H)
    bos_age = features.get("bos_age")
    if bos_age is None or pd.isna(bos_age):
        bos_age = htf_bias.bars_since_bos

    if bos_age is not None and bos_age <= bos_recency_threshold:
        gate.recent_bos = True
        gate.reasons.append("recent_bos")
        logger.debug(f"Expansion gate: recent BOS detected (age={bos_age})")

    # Check 2-4: Expansion signals from StructureContext
    # These are computed by StructureContextTracker.detect_expansion()
    expansion_detected = features.get("expansion_detected", False)
    expansion_reasons = features.get("expansion_reasons", [])

    if expansion_detected and expansion_reasons:
        # Map expansion reasons to gate fields
        if "range_expansion" in expansion_reasons:
            gate.range_expansion = True
            gate.reasons.append("range_expansion")
            logger.debug("Expansion gate: range expansion detected")

        if "atr_expansion" in expansion_reasons:
            gate.atr_expansion = True
            gate.reasons.append("atr_expansion")
            logger.debug("Expansion gate: ATR expansion detected")

        if "displacement_candle" in expansion_reasons:
            gate.displacement_candle = True
            gate.reasons.append("displacement_candle")
            logger.debug("Expansion gate: displacement candle detected")

    # Gate passes if any expansion signal is present
    gate.passed = len(gate.reasons) > 0

    if gate.passed:
        logger.info(f"Expansion gate PASSED: {gate.reasons}")
    else:
        logger.debug("Expansion gate FAILED: no expansion signals detected")

    return gate
