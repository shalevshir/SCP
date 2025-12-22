"""RuleEngine scoring functions.

This module implements the core scoring logic that transforms feature data
into Signal objects with SOP-compliant scoring and classification.
"""

from typing import Any

import pandas as pd
from scp_shared.common.logger import get_logger
from scp_shared.rule_engine.config_loader import load_scoring_config
from scp_shared.rule_engine.htf.validation import adjust_score_with_htf, validate_signal_with_htf
from scp_shared.rule_engine.htf.types import ChopSeverity, HTFBias
from scp_shared.rule_engine.signal import Signal

logger = get_logger(__name__)


def build_rejection_analysis(
    factor_scores: dict[str, float],
    adjusted_score: float,
    min_score: float,
) -> dict[str, Any]:
    """Analyze rejection causes and what would make signal pass.
    
    Args:
        factor_scores: Dict of factor names to scores (including penalties)
        adjusted_score: Final adjusted score
        min_score: Minimum score required to pass (typically 8.0)
    
    Returns:
        Dict with rejection analysis fields
    """
    if adjusted_score >= min_score:
        return {"passed": True}
    
    # Sort penalties by magnitude (most negative first)
    penalties = {k: v for k, v in factor_scores.items() if v < 0}
    sorted_penalties = sorted(penalties.items(), key=lambda x: x[1])
    
    primary = sorted_penalties[0] if sorted_penalties else None
    secondary = sorted_penalties[1:3] if len(sorted_penalties) > 1 else []
    
    # Calculate what would pass
    gap = min_score - adjusted_score
    would_pass_if = []
    if primary and abs(primary[1]) >= gap:
        would_pass_if.append(f"{primary[0]}_relaxed")
    
    return {
        "passed": False,
        "primary_rejection_reason": primary[0] if primary else "score_too_low",
        "primary_penalty": round(primary[1], 2) if primary else 0,
        "secondary_factors": [p[0] for p in secondary],
        "score_gap": round(gap, 2),
        "would_pass_if": would_pass_if,
    }


def build_diagnostics(
    features: pd.Series, htf_bias: HTFBias, direction: str | None = None
) -> dict[str, Any]:
    """Build diagnostics dict with structure parameters for debugging.

    Extracts all relevant structure, RSI, BOS, CHoCH, sweep, and DXY data
    that can help understand why a setup passed or failed.

    Args:
        features: Feature series with structure and indicator data
        htf_bias: HTFBias object with HTF structure info
        direction: Signal direction ("long" or "short") for mapping
            direction-specific fields to generic keys. If None, uses htf_bias.direction.

    Returns:
        Dict with all diagnostic fields for debugging (JSON serializable)
    """
    # Use htf_bias.direction as fallback if direction not provided
    effective_direction = direction if direction is not None else htf_bias.direction

    diag = {
        # Structure fields
        "structure_label": features.get("last_structure_label"),
        "structure_clarity": _safe_round(features.get("structure_clarity"), 3),
        "is_structural_chop": _to_python_bool(features.get("is_structural_chop", False)),
        "atr_compression_ratio": _safe_round(features.get("atr_compression_ratio", 1.0), 3),
        # BOS fields
        "bos_detected": _to_python_bool(features.get("bos_recent", False)),
        "bos_direction": features.get("bos_direction"),
        "bos_age": _to_python_int(features.get("bos_age")),
        "bars_since_bos": _to_python_int(features.get("bars_since_bos")),
        # CHoCH fields
        "choch_detected": _to_python_bool(features.get("choch_detected", False)),
        "choch_direction": features.get("choch_direction"),
        # Liquidity sweep
        "liquidity_sweep": _to_python_bool(features.get("liquidity_sweep", False)),
        "htf_liquidity_sweep": _to_python_bool(htf_bias.liquidity_sweep_detected),
        # Trend fields
        "trend_confidence": _safe_round(features.get("trend_confidence"), 3),
        "trend_direction": features.get("trend_direction"),
        # Indicators
        "rsi": _safe_round(features.get("rsi"), 2),
        "vwap": _safe_round(features.get("vwap"), 2),
        "close": _safe_round(features.get("close"), 2),
        "vwap_deviation_pct": _safe_round(
            _calc_vwap_deviation(features.get("close"), features.get("vwap")), 3
        ),
        # DXY fields
        "dxy_corr_1m": _safe_round(features.get("dxy_corr"), 3),
        "dxy_corr_5m": _safe_round(features.get("dxy_5m_corr"), 3),
        "dxy_structure": features.get("dxy_structure_label"),
        "dxy_alignment": _to_python_bool(htf_bias.dxy_alignment),
        # HTF bias info
        "htf_direction": htf_bias.direction,
        "htf_bias": htf_bias.bias,
        "htf_score": htf_bias.score,
        "htf_confidence": htf_bias.confidence,
        # Chop info
        "chop_detected": _to_python_bool(
            htf_bias.chop_severity != ChopSeverity.NONE
            if htf_bias.chop_severity
            else False
        ),
        "chop_severity": htf_bias.chop_severity.value
        if htf_bias.chop_severity
        else "none",
        # Structure 1H/15M from HTF
        "structure_1h": htf_bias.structure_1h,
        "structure_15m": htf_bias.structure_15m,
        # Expansion gate diagnostics (for VWAP_RECLAIM entry quality)
        "expansion_detected": _to_python_bool(features.get("expansion_detected", False)),
        "expansion_reasons": features.get("expansion_reasons", []) if features.get("expansion_reasons") else [],
    }

    # Map direction-specific second confirmation fields to generic keys
    # streaming.py computes: second_confirmation_long/short, bars_since_vwap_reclaim
    # entry_model.py expects: second_confirmation_satisfied, bars_since_reclaim
    if effective_direction == "long":
        diag["second_confirmation_satisfied"] = _to_python_bool(
            features.get("second_confirmation_long", False)
        )
        diag["second_confirmation_type"] = features.get("second_confirmation_long_type")
        # Sprint 2 Task 4: Add full list of confirmations
        diag["second_confirmation_types"] = features.get("second_confirmation_long_types", [])
        reasons = features.get("second_confirmation_long_reasons", [])
        diag["second_confirmation_reasons"] = list(reasons) if reasons else []
    elif effective_direction == "short":
        diag["second_confirmation_satisfied"] = _to_python_bool(
            features.get("second_confirmation_short", False)
        )
        diag["second_confirmation_type"] = features.get("second_confirmation_short_type")
        # Sprint 2 Task 4: Add full list of confirmations
        diag["second_confirmation_types"] = features.get("second_confirmation_short_types", [])
        reasons = features.get("second_confirmation_short_reasons", [])
        diag["second_confirmation_reasons"] = list(reasons) if reasons else []
    else:
        # Unknown direction - default to False
        diag["second_confirmation_satisfied"] = False
        diag["second_confirmation_type"] = None
        diag["second_confirmation_types"] = []
        diag["second_confirmation_reasons"] = []

    # Map bars_since_vwap_reclaim to bars_since_reclaim
    bars_since = features.get("bars_since_vwap_reclaim")
    diag["bars_since_reclaim"] = _to_python_int(bars_since) if bars_since is not None else 0

    return diag


def _safe_round(value: Any, decimals: int = 2) -> Any:
    """Safely round a value, returning None if not a number."""
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return value


def _to_python_bool(value: Any) -> bool:
    """Convert numpy bool or any value to native Python bool."""
    if value is None:
        return False
    return bool(value)


def _to_python_int(value: Any) -> int | None:
    """Convert numpy int or any value to native Python int."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _calc_vwap_deviation(close: Any, vwap: Any) -> float | None:
    """Calculate VWAP deviation percentage safely."""
    if close is None or vwap is None or vwap == 0:
        return None
    try:
        return ((float(close) - float(vwap)) / float(vwap)) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def calculate_chop_penalty(htf_bias: HTFBias, setup_type: str) -> float:
    """Calculate score penalty based on chop severity and setup type.
    
    This function implements setup-aware chop handling via score modification
    rather than hard rejection, per the SOP principle: "Chop is information, not prohibition."
    
    Args:
        htf_bias: HTFBias object containing chop severity classification
        setup_type: Setup type name ("VWAP_FADE", "VWAP_RECLAIM", "DXY_CONTINUATION")
    
    Returns:
        Score penalty (negative value) to apply to base score
    
    Logic:
        VWAP_FADE: No penalty (chop is preferred environment for fades)
        VWAP_RECLAIM: -1.5 penalty in SOFT_CHOP (reduces max attainable score)
        DXY_CONTINUATION: No penalty (hard-blocked in validation, never reaches scoring)
    
    Example:
        >>> penalty = calculate_chop_penalty(htf_bias, "VWAP_RECLAIM")
        >>> adjusted_score = base_score + penalty
    """
    if setup_type == "VWAP_FADE":
        # No penalty - chop is preferred environment for fade setups
        return 0.0
    
    if setup_type == "VWAP_RECLAIM":
        # Penalize VWAP_RECLAIM in SOFT_CHOP (structural setup needs some clarity)
        if htf_bias.chop_severity == ChopSeverity.SOFT_CHOP:
            logger.debug(
                f"VWAP_RECLAIM chop penalty: -1.5 (SOFT_CHOP, "
                f"consecutive={htf_bias.chop_consecutive_count})"
            )
            return -1.5
        # HARD_CHOP is blocked in validation, so no penalty needed here
        return 0.0
    
    # DXY_CONTINUATION blocked in validation for any chop, so no penalty here
    return 0.0


def _is_bos_still_valid(features: pd.Series, htf_bias: HTFBias) -> bool:
    """Check if BOS is still valid despite age.
    
    BOS remains valid if:
    1. No counter-CHoCH detected (no reversal signal), AND
    2. Structure clarity maintained (>= 0.4)
    
    Args:
        features: Feature series with CHoCH and clarity data
        htf_bias: HTFBias object with structure information
    
    Returns:
        True if BOS still valid
    """
    # Check for counter-CHoCH
    choch_detected = features.get("choch_detected", False)
    choch_direction = features.get("choch_direction")
    bos_direction = features.get("bos_direction")
    
    # Counter-CHoCH invalidates BOS
    if choch_detected and choch_direction is not None and bos_direction is not None:
        if choch_direction != bos_direction:
            return False  # Counter-CHoCH detected
    
    # Check structure clarity
    clarity = features.get("structure_clarity", 0)
    if clarity < 0.4:
        return False  # Structure degraded
    
    return True  # BOS still valid


def calculate_late_reclaim_penalty(
    features: pd.Series,
    htf_bias: HTFBias,
    setup_type: str,
) -> float:
    """Calculate score penalty for late VWAP_RECLAIM entries.

    This function implements graduated penalties for VWAP_RECLAIM entries that
    occur late in the structure sequence or far from VWAP. Unlike hard rejection,
    these penalties allow the trade but reduce the score to reflect reduced quality.

    Args:
        features: Feature series containing BOS age, VWAP data, expansion signals
        htf_bias: HTFBias object with structure information
        setup_type: Setup type name ("VWAP_RECLAIM", "VWAP_FADE", etc.)

    Returns:
        Score penalty (negative value) to apply to base score

    Penalties (cumulative for VWAP_RECLAIM only):
        - BOS invalid (counter-CHoCH or clarity < 0.4):
          - Age 11-15: -0.5
          - Age 16-20: -1.0
          - Age > 20: -1.5
        - BOS valid (no counter-CHoCH, clarity >= 0.4): NO age penalty
        - VWAP distance 0.3-0.5%: -0.15, >0.5%: -0.3 (late reclaim, price already moved)
        - No expansion signal: -0.5 (entering without confirmation)

    Example:
        >>> penalty = calculate_late_reclaim_penalty(features, htf_bias, "VWAP_RECLAIM")
        >>> adjusted_score = base_score + penalty  # penalty is negative
    """
    # Only apply to VWAP_RECLAIM setups
    if setup_type != "VWAP_RECLAIM":
        return 0.0

    total_penalty = 0.0

    # Penalty 1: BOS staleness (graduated) - ONLY if BOS invalid
    bos_age = features.get("bos_age")
    if bos_age is None or pd.isna(bos_age):
        bos_age = htf_bias.bars_since_bos

    if bos_age is not None and bos_age > 10:
        # Check if BOS is still valid
        bos_valid = _is_bos_still_valid(features, htf_bias)
        
        if not bos_valid:
            # BOS invalidated - apply age-based penalty
            if 11 <= bos_age <= 15:
                total_penalty += -0.5
                logger.debug(f"Late BOS penalty -0.5 (age={bos_age}, invalid)")
            elif 16 <= bos_age <= 20:
                total_penalty += -1.0
                logger.debug(f"Late BOS penalty -1.0 (age={bos_age}, invalid)")
            elif bos_age > 20:
                total_penalty += -1.5
                logger.debug(f"Late BOS penalty -1.5 (age={bos_age}, invalid)")
        else:
            # BOS still valid - no age penalty
            logger.debug(f"BOS age {bos_age} but still valid (no penalty)")

    # Penalty 2: VWAP distance (late reclaim - price already moved significantly)
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)

    if vwap != 0:
        vwap_deviation_pct = abs((close - vwap) / vwap * 100)
        # Graduated penalty: mild for 0.3-0.5%, full for >0.5%
        if vwap_deviation_pct > 0.5:
            total_penalty += -0.3
            logger.debug(
                f"VWAP distance penalty -0.3 (deviation={vwap_deviation_pct:.2f}% > 0.5%)"
            )
        elif vwap_deviation_pct > 0.3:
            total_penalty += -0.15
            logger.debug(
                f"VWAP distance penalty -0.15 (deviation={vwap_deviation_pct:.2f}% > 0.3%)"
            )

    # Penalty 3: No expansion signal (entering during compression)
    expansion_detected = features.get("expansion_detected", False)

    if not expansion_detected:
        total_penalty += -0.5
        logger.debug("No expansion penalty -0.5")

    if total_penalty < 0:
        logger.info(f"Late reclaim penalty total: {total_penalty:.2f}")

    return total_penalty


def calculate_noise_penalty(features: pd.Series, setup_type: str) -> float:
    """Calculate score penalty for structural chop with ATR as modifier.
    
    This function implements setup-aware chop handling via score modification
    rather than hard rejection, per the SOP principle: "Chop is information, not prohibition."
    
    Per Shir Capital SOP: Noise means structural disorder, not low volatility.
    - Primary gate: is_structural_chop (overlapping swings, failed follow-through, wick dominance)
    - Supporting modifier: atr_compression_ratio (amplifies penalty when combined with structural chop)
    
    Args:
        features: Feature series containing is_structural_chop and atr_compression_ratio
        setup_type: Setup type name ("VWAP_FADE", "VWAP_RECLAIM", "DXY_CONTINUATION")
    
    Returns:
        Score penalty (negative value) to apply to base score
    
    Logic:
        Structural chop alone:
            VWAP_FADE: -0.5 penalty (tolerates chop, often works in ranging conditions)
            VWAP_RECLAIM: -1.5 penalty (needs clearer structure for BOS validation)
            DXY_CONTINUATION: -1.5 penalty (needs clear displacement and structure)
        
        ATR compression amplifier:
            If ATR compressed (<0.4 of baseline) AND structural chop detected:
            - Additional -0.5 penalty (total: -1.0 for FADE, -2.0 for RECLAIM/CONT)
            
            If ATR compressed but NO structural chop:
            - Minor -0.2 penalty only (ATR alone cannot block trades)
    
    Example:
        >>> penalty = calculate_noise_penalty(features, "VWAP_RECLAIM")
        >>> adjusted_score = base_score + penalty
    """
    is_structural_chop = features.get("is_structural_chop", False)
    atr_compression_ratio = features.get("atr_compression_ratio", 1.0)
    
    # Base penalty for structural chop
    base_penalty = 0.0
    if is_structural_chop:
        if setup_type == "VWAP_FADE":
            base_penalty = -0.5
            logger.debug("VWAP_FADE structural chop penalty: -0.5 (range trading viable)")
        elif setup_type in ["VWAP_RECLAIM", "DXY_CONTINUATION"]:
            base_penalty = -1.5
            logger.debug(
                f"{setup_type} structural chop penalty: -1.5 "
                "(structure/displacement unreliable)"
            )
    
    # ATR compression modifier (supporting filter, not primary gate)
    atr_modifier = 0.0
    ATR_SEVERE_COMPRESSION = 0.4
    
    if atr_compression_ratio < ATR_SEVERE_COMPRESSION:
        if is_structural_chop:
            # ATR compression amplifies structural chop penalty
            atr_modifier = -0.5
            logger.debug(
                f"ATR compression amplifier: -0.5 "
                f"(ratio={atr_compression_ratio:.2f}, combined with structural chop)"
            )
        else:
            # ATR compression alone = small modifier, not rejection
            atr_modifier = -0.2
            logger.debug(
                f"ATR compression modifier: -0.2 "
                f"(ratio={atr_compression_ratio:.2f}, no structural chop)"
            )
    
    total_penalty = base_penalty + atr_modifier
    return total_penalty


def calculate_structure_quality_penalty(
    features: pd.Series,
    htf_bias: HTFBias,
    setup_type: str,
    quality_flags: dict[str, bool] | None = None,
) -> float:
    """Calculate score penalty for structure quality issues (moved from hard rejection).

    This function applies penalties for quality issues that were previously hard rejections,
    allowing more setup candidates to reach scoring while appropriately penalizing poor quality.

    Args:
        features: Feature series containing structure and BOS data
        htf_bias: HTFBias object with structure information
        setup_type: Setup type name ("VWAP_RECLAIM", "VWAP_FADE", "DXY_CONTINUATION")
        quality_flags: Optional dict of quality flags from validate_reclaim_context:
            - no_sweep: bool - no liquidity sweep detected
            - low_clarity: bool - structure clarity below threshold
            - no_bos: bool - no BOS detected
            - bos_stale: bool - BOS age exceeds threshold

    Returns:
        Score penalty (negative value) to apply to base score

    Penalties (cumulative):
        - No liquidity sweep: -1.5 (major quality issue)
        - Low clarity (0.3-0.4): -1.0, (0.4-0.6): -0.5
        - No BOS detected: -2.0 (critical structural component missing)
        - BOS stale (>15 bars): -0.5 to -1.5 graduated

    Note:
        Only applies to VWAP_RECLAIM. Other setups use different quality gates.

    Example:
        >>> quality_flags = {"no_sweep": True, "low_clarity": False, "no_bos": False}
        >>> penalty = calculate_structure_quality_penalty(features, htf_bias, "VWAP_RECLAIM", quality_flags)
        >>> # penalty = -1.5 (no sweep)
    """
    # Only apply to VWAP_RECLAIM (other setups have different quality checks)
    if setup_type != "VWAP_RECLAIM":
        return 0.0

    # If no quality_flags provided, extract from features/htf_bias
    if quality_flags is None:
        quality_flags = {
            "no_sweep": not (
                features.get("liquidity_sweep", False)
                or htf_bias.liquidity_sweep_detected
            ),
            "low_clarity": htf_bias.structure_clarity < 0.4,
            "no_bos": not (features.get("bos_recent", False) or htf_bias.bos_detected),
            "bos_stale": False,
        }
        # Check BOS age for staleness
        bos_age = features.get("bos_age")
        if bos_age is None or pd.isna(bos_age):
            bos_age = htf_bias.bars_since_bos
        if bos_age is not None and bos_age > 15:
            quality_flags["bos_stale"] = True


    total_penalty = 0.0

    # Penalty 1: No liquidity sweep (-1.5)
    if quality_flags.get("no_sweep", False):
        total_penalty += -1.5
        logger.debug("Structure quality penalty: -1.5 (no liquidity sweep)")

    # Penalty 2: Low structure clarity (graduated based on actual clarity)
    structure_clarity = htf_bias.structure_clarity
    if quality_flags.get("low_clarity", False):
        if structure_clarity < 0.3:
            total_penalty += -1.5
            logger.debug(
                f"Structure quality penalty: -1.5 (very low clarity={structure_clarity:.2f})"
            )
        elif structure_clarity < 0.4:
            total_penalty += -1.0
            logger.debug(
                f"Structure quality penalty: -1.0 (low clarity={structure_clarity:.2f})"
            )
        elif structure_clarity < 0.6:
            total_penalty += -0.5
            logger.debug(
                f"Structure quality penalty: -0.5 (moderate clarity={structure_clarity:.2f})"
            )

    # Penalty 3: No BOS detected (-2.0)
    if quality_flags.get("no_bos", False):
        total_penalty += -2.0
        logger.debug("Structure quality penalty: -2.0 (no BOS detected)")

    # Penalty 4: BOS stale (graduated based on age) - ONLY if BOS invalid
    if quality_flags.get("bos_stale", False):
        bos_age = features.get("bos_age")
        if bos_age is None or pd.isna(bos_age):
            bos_age = htf_bias.bars_since_bos
        
        if bos_age is not None:
            # Check if BOS is still valid
            bos_valid = _is_bos_still_valid(features, htf_bias)
            
            if not bos_valid:
                # BOS invalidated - apply age-based penalty
                if bos_age > 25:
                    total_penalty += -1.5
                    logger.debug(f"Structure quality penalty: -1.5 (very stale BOS, age={bos_age}, invalid)")
                elif bos_age > 20:
                    total_penalty += -1.0
                    logger.debug(f"Structure quality penalty: -1.0 (stale BOS, age={bos_age}, invalid)")
                elif bos_age > 15:
                    total_penalty += -0.5
                    logger.debug(f"Structure quality penalty: -0.5 (aging BOS, age={bos_age}, invalid)")
            else:
                # BOS still valid - minimal penalty
                logger.debug(f"BOS age {bos_age} but still valid (minimal penalty)")

    if total_penalty < 0:
        logger.info(
            f"Structure quality penalty total: {total_penalty:.2f} "
            f"(sweep={not quality_flags.get('no_sweep', False)}, "
            f"clarity={structure_clarity:.2f}, "
            f"bos={not quality_flags.get('no_bos', False)})"
        )

    return total_penalty


def score_signal(features: pd.Series, htf_bias: HTFBias, context: dict) -> Signal:
    """Calculate SOP-compliant signal score and create Signal object.

    Args:
        features: Pandas Series containing engineered features:
            - timestamp: Signal timestamp
            - symbol: Asset symbol (e.g., "GC")
            - timeframe: Candle period (e.g., "1m")
            - close: Close price
            - vwap: Volume-weighted average price
            - rsi: Relative strength index
            - ema_9, ema_20, ema_50: Exponential moving averages
            - dxy_corr: DXY correlation coefficient
        htf_bias: HTFBias object containing HTF analysis results
        context: Dict containing contextual data:
            - session_ok: Whether current session is valid for trading
            - enforcer_tier: Active enforcer tier

    Returns:
        Signal object with score, confidence, and detailed breakdown

    Example:
        >>> features = pd.Series({
        ...     "timestamp": datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        ...     "symbol": "GC",
        ...     "timeframe": "1m",
        ...     "close": 2650.0,
        ...     "vwap": 2645.0,
        ...     "rsi": 55.0,
        ...     "ema_9": 2648.0,
        ...     "ema_20": 2645.0,
        ...     "ema_50": 2640.0,
        ...     "dxy_corr": -0.75,
        ... })
        >>> htf_bias = HTFBias(
        ...     bias="bullish",
        ...     direction="long",
        ...     score=8.5,
        ...     confidence="high"
        ... )
        >>> context = {
        ...     "session_ok": True,
        ...     "enforcer_tier": "Early Mild",
        ... }
        >>> signal = score_signal(features, htf_bias, context)
    """
    # Determine signal direction from features
    signal_direction = determine_direction(features, htf_bias)

    # Validate signal against HTF bias
    is_valid, rejection_reason = validate_signal_with_htf(signal_direction, htf_bias)

    # Build diagnostics for all signal outputs
    diagnostics = build_diagnostics(features, htf_bias, direction=signal_direction)

    if not is_valid:
        # Return rejected signal with reason
        logger.warning(f"Signal rejected: {rejection_reason}")
        return Signal(
            timestamp=features["timestamp"],
            symbol=features["symbol"],
            timeframe=features["timeframe"],
            direction=signal_direction,
            setup_type="REJECTED",
            htf_bias=htf_bias.bias,
            score=0.0,
            confidence="Reject",
            factors={},
            rationale=f"Rejected: {rejection_reason}",
            validation_flags={"htf_valid": False},
            enforcer_tier=context.get("enforcer_tier", "Conservative"),
            diagnostics=diagnostics,
        )

    # Load scoring configuration
    config = load_scoring_config()

    # Determine setup type based on features
    setup_type = determine_setup_type(features, htf_bias)

    # Handle rejected setups
    if setup_type == "REJECTED":
        logger.warning("Setup type rejected - no valid setup detected")
        return Signal(
            timestamp=features["timestamp"],
            symbol=features["symbol"],
            timeframe=features["timeframe"],
            direction=signal_direction,
            setup_type="REJECTED",
            htf_bias=htf_bias.bias,
            score=0.0,
            confidence="Reject",
            factors={},
            rationale="Rejected: No valid setup type detected (failed prerequisites)",
            validation_flags={"htf_valid": False},
            enforcer_tier=context.get("enforcer_tier", "Conservative"),
            diagnostics=diagnostics,
        )

    # Get setup configuration and weights
    setup_config = config.setup_types[setup_type]
    weights = setup_config["weights"]

    # Calculate individual factor scores
    factor_scores = calculate_factor_scores(features, htf_bias, weights, setup_type)

    # Calculate base score (sum of all factors, capped at 10)
    base_score = min(sum(factor_scores.values()), 10.0)

    # Apply chop penalty (setup-aware score modification)
    chop_penalty = calculate_chop_penalty(htf_bias, setup_type)
    if chop_penalty != 0.0:
        factor_scores["chop_penalty"] = chop_penalty
        base_score += chop_penalty
        logger.debug(f"Applied chop penalty: {chop_penalty:.2f}")
    
    # Apply noise zone penalty (setup-aware score modification for volatility compression)
    noise_penalty = calculate_noise_penalty(features, setup_type)
    if noise_penalty != 0.0:
        factor_scores["noise_penalty"] = noise_penalty
        base_score += noise_penalty
        logger.debug(f"Applied noise penalty: {noise_penalty:.2f}")

    # Apply late reclaim penalty (VWAP_RECLAIM-specific penalties for timing)
    late_reclaim_penalty = calculate_late_reclaim_penalty(features, htf_bias, setup_type)
    if late_reclaim_penalty != 0.0:
        factor_scores["late_reclaim_penalty"] = late_reclaim_penalty
        base_score += late_reclaim_penalty
        logger.debug(f"Applied late reclaim penalty: {late_reclaim_penalty:.2f}")

    # Apply structure quality penalty (quality issues that were previously hard rejections)
    # Extract quality_flags from context validation if VWAP_RECLAIM
    quality_flags = None

    if setup_type == "VWAP_RECLAIM":
        from rule_engine.htf.vwap.reclaim import validate_reclaim_context

        context_result = validate_reclaim_context(htf_bias, features)
        quality_flags = context_result.quality_flags

    structure_quality_penalty = calculate_structure_quality_penalty(
        features, htf_bias, setup_type, quality_flags
    )
    if structure_quality_penalty != 0.0:
        factor_scores["structure_quality_penalty"] = structure_quality_penalty
        base_score += structure_quality_penalty
        logger.debug(f"Applied structure quality penalty: {structure_quality_penalty:.2f}")

    # Apply penalty capping to prevent runaway negative scores
    # Cap individual penalty domains
    structure_penalties = (
        factor_scores.get("chop_penalty", 0)
        + factor_scores.get("noise_penalty", 0)
        + factor_scores.get("structure_quality_penalty", 0)
    )
    timing_penalties = factor_scores.get("late_reclaim_penalty", 0)
    
    # Apply domain caps
    if structure_penalties < -2.5:
        # Redistribute penalties proportionally
        scale_factor = -2.5 / structure_penalties
        if "chop_penalty" in factor_scores:
            factor_scores["chop_penalty"] *= scale_factor
        if "noise_penalty" in factor_scores:
            factor_scores["noise_penalty"] *= scale_factor
        if "structure_quality_penalty" in factor_scores:
            factor_scores["structure_quality_penalty"] *= scale_factor
        logger.debug(
            f"Structure penalties capped: {structure_penalties:.2f} -> -2.5 "
            f"(scale={scale_factor:.2f})"
        )
        structure_penalties = -2.5
    
    if timing_penalties < -1.5:
        factor_scores["late_reclaim_penalty"] = -1.5
        logger.debug(f"Timing penalties capped: {timing_penalties:.2f} -> -1.5")
        timing_penalties = -1.5
    
    # Recalculate base score with capped penalties
    base_score = min(
        sum(v for v in factor_scores.values() if not v < 0), 10.0
    ) + structure_penalties + timing_penalties

    # Apply HTF-based score adjustments (pass context for tier-aware adjustments)
    adjusted_score, htf_adjustments = adjust_score_with_htf(
        base_score, htf_bias, signal_direction, context
    )

    # Add HTF adjustments to factor scores for transparency
    factor_scores.update(htf_adjustments)
    
    # Cap HTF penalties
    htf_penalties = htf_adjustments.get("htf_weak_bias", 0)
    if htf_penalties < -1.0:
        factor_scores["htf_weak_bias"] = -1.0
        adjusted_score = adjusted_score - htf_penalties - 1.0  # Adjust score
        logger.debug(f"HTF penalties capped: {htf_penalties:.2f} -> -1.0")
    
    # Apply total penalty cap
    all_penalties = structure_penalties + timing_penalties + min(htf_penalties, -1.0)
    if all_penalties < -4.0:
        # Scale all penalties proportionally to reach -4.0 total
        scale_factor = -4.0 / all_penalties
        
        # Rescale structure penalties
        if structure_penalties < 0:
            structure_scale = structure_penalties * scale_factor
            if "chop_penalty" in factor_scores:
                factor_scores["chop_penalty"] *= scale_factor
            if "noise_penalty" in factor_scores:
                factor_scores["noise_penalty"] *= scale_factor
            if "structure_quality_penalty" in factor_scores:
                factor_scores["structure_quality_penalty"] *= scale_factor
        
        # Rescale timing penalties
        if "late_reclaim_penalty" in factor_scores and timing_penalties < 0:
            factor_scores["late_reclaim_penalty"] *= scale_factor
        
        # Rescale HTF penalties
        if "htf_weak_bias" in factor_scores and htf_penalties < 0:
            factor_scores["htf_weak_bias"] *= scale_factor
        
        # Recalculate adjusted score
        adjusted_score = min(
            sum(v for v in factor_scores.values() if v > 0), 10.0
        ) + sum(v for v in factor_scores.values() if v < 0)
        
        logger.debug(
            f"Total penalties capped: {all_penalties:.2f} -> -4.0 "
            f"(scale={scale_factor:.2f})"
        )

    # Enhanced logging: Complete confluence breakdown
    logger.info(
        f"Confluence breakdown: "
        f"structure={factor_scores.get('structure_alignment', 0):.2f}, "
        f"vwap={factor_scores.get('vwap_relation', 0):.2f}, "
        f"rsi={factor_scores.get('rsi_state', 0):.2f}, "
        f"ema={factor_scores.get('ema_stack', 0):.2f}, "
        f"dxy={factor_scores.get('dxy_corr', 0):.2f}, "
        f"fvg={factor_scores.get('fvg_alignment', 0):.2f}, "
        f"sweep={factor_scores.get('liquidity_sweep', 0):.2f}, "
        f"htf_bonus={factor_scores.get('htf_bonus', 0):.2f}, "
        f"chop_penalty={factor_scores.get('chop_penalty', 0):.2f}, "
        f"noise_penalty={factor_scores.get('noise_penalty', 0):.2f}, "
        f"struct_quality_penalty={factor_scores.get('structure_quality_penalty', 0):.2f} | "
        f"base={base_score:.2f}, final={adjusted_score:.2f}"
    )

    # Classify confidence level based on adjusted score
    confidence = classify_confidence(adjusted_score, setup_type)

    # Generate human-readable rationale
    rationale = build_rationale(features, htf_bias, factor_scores, setup_type)
    
    # Add rejection analysis to diagnostics
    min_score = config.confidence["a_plus"]
    rejection_analysis = build_rejection_analysis(factor_scores, adjusted_score, min_score)
    diagnostics["rejection_analysis"] = rejection_analysis

    # Create validation flags
    features.get("dxy_corr")
    validation_flags = {
        "session_ok": context.get("session_ok", True),
        "tier_ok": True,
        "dxy_alignment_ok": htf_bias.dxy_alignment,
        "htf_bias_ok": signal_direction == htf_bias.direction,
        "htf_valid": is_valid,
    }

    # Create and return Signal object
    return Signal(
        timestamp=features["timestamp"],
        symbol=features["symbol"],
        timeframe=features["timeframe"],
        direction=signal_direction,
        setup_type=setup_type,
        htf_bias=htf_bias.bias,
        score=adjusted_score,
        confidence=confidence,
        factors=factor_scores,
        rationale=rationale,
        validation_flags=validation_flags,
        enforcer_tier=context.get("enforcer_tier", "Conservative"),
        diagnostics=diagnostics,
    )


def determine_setup_type(features: pd.Series, htf_bias: HTFBias) -> str:
    """Determine setup type based on market features with strict validation.

    Args:
        features: Feature data including VWAP, RSI, DXY correlation
        htf_bias: HTFBias object

    Returns:
        Setup type name: "VWAP_RECLAIM", "VWAP_FADE", "DXY_CONTINUATION", or "REJECTED"

    Logic:
        - VWAP_FADE: RSI extreme (<30 or >70) with significant VWAP deviation
        - DXY_CONTINUATION: Very strong inverse correlation (<-0.8)
        - VWAP_RECLAIM: Requires full reclaim sequence validation
        - REJECTED: No valid setup detected

    Note:
        VWAP_RECLAIM now requires:
        1. Liquidity sweep detected
        2. Structure clarity >= 0.7
        3. No chop detected
        4. BOS detected within 15 bars
    """
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)
    rsi = features.get("rsi", 50)
    dxy_corr = features.get("dxy_corr")

    # Calculate VWAP deviation percentage
    vwap_dev = abs((close - vwap) / vwap * 100) if vwap != 0 else 0

    # VWAP_FADE: Strict structure-based validation
    from rule_engine.setup_detectors.vwap_fade import detect_vwap_fade

    if detect_vwap_fade(features, htf_bias, df=None):
        return "VWAP_FADE"

    # DXY_CONTINUATION: Strict multi-factor validation
    from rule_engine.setup_detectors.dxy_continuation import detect_dxy_continuation

    if detect_dxy_continuation(features, htf_bias):
        return "DXY_CONTINUATION"

    # VWAP_RECLAIM: Check context validity (NOT entry readiness)
    # Context validation determines if setup type is VWAP_RECLAIM
    # Entry readiness is checked later in scoring to apply penalties
    # Import here to avoid circular dependency
    from rule_engine.htf.vwap.reclaim import validate_reclaim_context

    context_result = validate_reclaim_context(htf_bias, features)

    if context_result.context_valid:
        return "VWAP_RECLAIM"
    else:
        # Log rejection reason for debugging
        logger.debug(f"VWAP_RECLAIM rejected: {context_result.reason}")
        return "REJECTED"


def calculate_factor_scores(
    features: pd.Series, htf_bias: HTFBias, weights: dict, setup_type: str
) -> dict[str, float]:
    """Calculate individual factor scores based on setup type.

    Args:
        features: Feature data
        htf_bias: HTFBias object
        weights: Dict of factor weights from config
        setup_type: Setup type name

    Returns:
        Dict mapping factor names to their scores
    """
    scores = {}

    # Structure alignment: Price action matches HTF bias
    if "structure_alignment" in weights:
        scores["structure_alignment"] = calculate_structure_alignment(
            features, htf_bias, weights["structure_alignment"], setup_type
        )

    # VWAP relation: Position relative to VWAP
    if "vwap_relation" in weights:
        scores["vwap_relation"] = calculate_vwap_relation(
            features, htf_bias, weights["vwap_relation"]
        )

    # RSI state: RSI in optimal zone
    if "rsi_state" in weights:
        scores["rsi_state"] = calculate_rsi_state(
            features, htf_bias, weights["rsi_state"]
        )

    if "rsi_mid_reset" in weights:
        scores["rsi_mid_reset"] = calculate_rsi_state(
            features, htf_bias, weights["rsi_mid_reset"]
        )

    # EMA stack: EMA alignment
    if "ema_stack" in weights:
        scores["ema_stack"] = calculate_ema_stack(
            features, htf_bias, weights["ema_stack"]
        )

    # DXY correlation
    if "dxy_corr" in weights:
        scores["dxy_corr"] = calculate_dxy_correlation(
            features, htf_bias, weights["dxy_corr"]
        )

    # HTF bonus
    if "htf_bonus" in weights:
        scores["htf_bonus"] = calculate_htf_bonus(
            features, htf_bias, weights["htf_bonus"]
        )

    # FVG alignment
    if "fvg_alignment" in weights:
        scores["fvg_alignment"] = calculate_fvg_alignment(
            features, htf_bias, weights["fvg_alignment"]
        )

    # Liquidity sweep
    if "liquidity_sweep" in weights:
        scores["liquidity_sweep"] = calculate_liquidity_sweep(
            features, htf_bias, weights["liquidity_sweep"]
        )

    # Fade-specific factors
    if "vwap_deviation" in weights:
        scores["vwap_deviation"] = calculate_vwap_deviation(
            features, htf_bias, weights["vwap_deviation"]
        )

    if "rsi_extreme" in weights:
        scores["rsi_extreme"] = calculate_rsi_extreme(
            features, htf_bias, weights["rsi_extreme"]
        )

    if "rejection_candle" in weights:
        scores["rejection_candle"] = calculate_rejection_candle(
            features, htf_bias, weights["rejection_candle"]
        )

    if "volume_spike" in weights:
        scores["volume_spike"] = calculate_volume_spike(
            features, htf_bias, weights["volume_spike"]
        )

    return scores


def calculate_structure_alignment(
    features: pd.Series, htf_bias: HTFBias, max_points: float, setup_type: str
) -> float:
    """Calculate structure alignment score with setup-specific requirements.

    VWAP_RECLAIM (loosened per SOP):
    - Skips chop/clarity hard rejections
    - Minimum base score of 50% max_points (not 0)
    - Only requires: direction match, liquidity sweep, recent BOS

    DXY_CONTINUATION & VWAP_FADE (strict):
    - Requires clean structure (clarity >= 0.6)
    - No chop detected
    - Recent BOS (within 15 bars)
    - Liquidity sweep detected

    Args:
        features: Feature data for determining signal direction
        htf_bias: HTFBias object containing structure quality metrics
        max_points: Maximum points this factor can contribute
        setup_type: Setup type ("VWAP_RECLAIM", "DXY_CONTINUATION", "VWAP_FADE")

    Returns:
        Score contribution (0 to max_points)

    Example:
        >>> # VWAP_RECLAIM with chop - still scores
        >>> htf_bias = HTFBias(
        ...     direction="long", structure_clarity=0.4,
        ...     bars_since_bos=10, chop_detected=True,
        ...     liquidity_sweep_detected=True
        ... )
        >>> calculate_structure_alignment(features, htf_bias, 2.5, "VWAP_RECLAIM")
        1.25  # Gets minimum 50% of max_points

        >>> # DXY_CONTINUATION with chop - rejected
        >>> calculate_structure_alignment(features, htf_bias, 2.5, "DXY_CONTINUATION")
        0.0  # Zero points - fails hard rejections
    """
    direction = determine_direction(features, htf_bias)

    # Base requirement: signal direction must be clear (not neutral)
    if direction == "neutral":
        return 0.0

    # For VWAP_RECLAIM: Allow scoring even when HTF is neutral (warmup period)
    # HTF neutral means we can't confirm alignment, but VWAP_RECLAIM is a structural
    # setup that can work with local confluence (VWAP, EMA direction)
    if setup_type == "VWAP_RECLAIM" and htf_bias.direction == "neutral":
        # Reduced score for unconfirmed HTF alignment (40% of max)
        score = max_points * 0.4
        logger.debug(
            f"VWAP_RECLAIM structure: HTF neutral, scoring at reduced rate "
            f"({score:.2f}/{max_points})"
        )
        return score

    # For other setups: Require direction match
    if htf_bias.direction != direction:
        return 0.0

    # VWAP_RECLAIM: Loosened requirements per SOP
    if setup_type == "VWAP_RECLAIM":
        # Skip chop and clarity hard rejections
        # VWAP_RECLAIM can work during micro chop (reclaim is structural, not momentum)

        # Calculate base score for VWAP_RECLAIM (tolerant scoring)
        # Start with minimum base and add bonuses for quality factors
        score = max_points * 0.4  # Base score (40%) - allows scoring even without perfect conditions

        # Bonus for liquidity sweep detected
        if htf_bias.liquidity_sweep_detected:
            score += max_points * 0.2
            logger.debug("VWAP_RECLAIM structure: +20% for liquidity sweep")
        else:
            # Check 1M features for sweep indication
            sweep_direction = features.get("sweep_direction") if features is not None else None
            if sweep_direction is not None:
                score += max_points * 0.1  # Partial bonus for 1M sweep
                logger.debug("VWAP_RECLAIM structure: +10% for 1M sweep direction")

        # Bonus for recent BOS
        if htf_bias.bars_since_bos is not None:
            if htf_bias.bars_since_bos <= 10:
                score += max_points * 0.2
                logger.debug("VWAP_RECLAIM structure: +20% for recent BOS")
            elif htf_bias.bars_since_bos <= 15:
                score += max_points * 0.1
                logger.debug("VWAP_RECLAIM structure: +10% for moderately recent BOS")

        # Bonus for high clarity
        if htf_bias.structure_clarity is not None:
            if htf_bias.structure_clarity >= 0.7:
                score += max_points * 0.2
                logger.debug("VWAP_RECLAIM structure: +20% for high clarity")
            elif htf_bias.structure_clarity >= 0.5:
                score += max_points * 0.1
                logger.debug("VWAP_RECLAIM structure: +10% for moderate clarity")

        logger.debug(
            f"VWAP_RECLAIM structure (tolerant): clarity={htf_bias.structure_clarity}, "
            f"bars_since_bos={htf_bias.bars_since_bos}, "
            f"sweep={htf_bias.liquidity_sweep_detected}, score={score:.2f}/{max_points}"
        )

        return min(score, max_points)

    # STRICT REQUIREMENTS for DXY_CONTINUATION and VWAP_FADE
    # These setups need clean structure (no chop tolerance)

    # Rejection 1: Choppy structure
    if htf_bias.chop_detected:
        logger.debug(f"{setup_type} structure rejected: chop detected")
        return 0.0

    # Rejection 2: No recent BOS or BOS too stale
    if htf_bias.bars_since_bos is None or htf_bias.bars_since_bos > 15:
        logger.debug(
            f"{setup_type} structure rejected: BOS stale or missing "
            f"(bars_since_bos={htf_bias.bars_since_bos})"
        )
        return 0.0

    # Rejection 3: Low structure clarity
    if htf_bias.structure_clarity < 0.6:
        logger.debug(
            f"{setup_type} structure rejected: low clarity "
            f"({htf_bias.structure_clarity:.2f} < 0.6)"
        )
        return 0.0

    # Rejection 4: No liquidity sweep
    if not htf_bias.liquidity_sweep_detected:
        logger.debug(f"{setup_type} structure rejected: no liquidity sweep")
        return 0.0

    # All hard rejections passed - calculate score
    score = 0.0

    # Factor 1: Clean swing structure (40% of max)
    if htf_bias.structure_clarity >= 0.7:
        score += max_points * 0.4
    elif htf_bias.structure_clarity >= 0.6:
        score += max_points * 0.2

    # Factor 2: Recent structure event (30% of max)
    if htf_bias.bars_since_bos <= 10:
        score += max_points * 0.3
    elif htf_bias.bars_since_bos <= 15:
        score += max_points * 0.15

    # Factor 3: No chop detected (30% of max)
    score += max_points * 0.3

    logger.debug(
        f"{setup_type} structure (strict): clarity={htf_bias.structure_clarity:.2f}, "
        f"bars_since_bos={htf_bias.bars_since_bos}, chop={htf_bias.chop_detected}, "
        f"sweep={htf_bias.liquidity_sweep_detected}, score={score:.2f}/{max_points}"
    )

    return min(score, max_points)


def calculate_vwap_relation(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate VWAP relation score.

    Awards points if price is correctly positioned relative to VWAP.
    When HTF bias is neutral, uses VWAP position to determine direction.
    """
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)

    # Use HTF direction if available, otherwise infer from VWAP position
    effective_direction = htf_bias.direction
    if effective_direction == "neutral":
        # Infer direction from VWAP position when HTF is neutral
        if close > vwap:
            effective_direction = "long"
        elif close < vwap:
            effective_direction = "short"

    if effective_direction == "long" and close > vwap:
        return max_points
    elif effective_direction == "short" and close < vwap:
        return max_points

    return 0.0


def calculate_rsi_state(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate RSI state score.

    Awards points if RSI is in mid-reset zone (40-60) for continuations.
    """
    rsi = features.get("rsi", 50)

    if 40 <= rsi <= 60:
        return max_points

    return 0.0


def calculate_ema_stack(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate EMA stack score.

    Awards points if EMAs are properly aligned with HTF direction.
    When HTF is neutral, scores based on EMA stack quality alone.
    """
    ema_9 = features.get("ema_9", 0)
    ema_20 = features.get("ema_20", 0)
    ema_50 = features.get("ema_50", 0)

    # Determine effective direction
    effective_direction = htf_bias.direction
    if effective_direction == "neutral":
        # Infer direction from EMA stack when HTF is neutral
        if ema_9 > ema_20 > ema_50:
            effective_direction = "long"
        elif ema_9 < ema_20 < ema_50:
            effective_direction = "short"
        elif ema_9 > ema_20:
            effective_direction = "long"
        elif ema_9 < ema_20:
            effective_direction = "short"

    # Bullish: 9 > 20 > 50
    if effective_direction == "long" and ema_9 > ema_20 > ema_50:
        return max_points

    # Bearish: 9 < 20 < 50
    if effective_direction == "short" and ema_9 < ema_20 < ema_50:
        return max_points

    # Partial alignment gets partial points
    if effective_direction == "long" and ema_9 > ema_20:
        return max_points / 2

    if effective_direction == "short" and ema_9 < ema_20:
        return max_points / 2

    return 0.0


def calculate_dxy_correlation(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate DXY correlation score with graduated thresholds.

    Awards points based on inverse correlation strength:
    - Strong (<-0.6): Full points
    - Moderate (<-0.4): 75% points
    - Weak (<-0.2): 50% points
    - Very weak (<0): 25% points
    """
    dxy_corr = features.get("dxy_corr")

    if dxy_corr is None:
        return 0.0

    # Graduated scoring based on correlation strength
    if dxy_corr < -0.6:
        return max_points  # Strong inverse correlation
    elif dxy_corr < -0.4:
        return max_points * 0.75  # Moderate inverse correlation
    elif dxy_corr < -0.2:
        return max_points * 0.5  # Weak inverse correlation
    elif dxy_corr < 0:
        return max_points * 0.25  # Very weak inverse correlation

    return 0.0  # Positive correlation = no points


def calculate_htf_bonus(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate HTF bonus score.

    Awards bonus point if HTF bias score is >= 8.
    """
    if htf_bias.score >= 8.0:
        return max_points

    return 0.0


def calculate_fvg_alignment(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate FVG alignment score.

    Awards points if FVG gaps support the bias direction.
    FVG alignment score from HTF ranges -2 to +2.
    Only positive contributions are counted.

    Args:
        features: Feature data (unused, kept for signature consistency)
        htf_bias: HTFBias object containing fvg_alignment_score
        max_points: Maximum points this factor can contribute

    Returns:
        Score contribution (0 to max_points)
    """
    if htf_bias.fvg_alignment_score == 0.0:
        return 0.0

    # Normalize to max_points (only positive contributions)
    # FVG score ranges from -2 to +2, normalize to -1 to +1
    normalized = htf_bias.fvg_alignment_score / 2.0

    # Only positive contributions count, and enforce upper bound
    return min(max(0.0, normalized * max_points), max_points)


def calculate_liquidity_sweep(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate liquidity sweep alignment score.

    Awards points if sweep type matches signal direction.
    Also awards partial points for sweep_direction from features (1M data)
    even if HTF sweep not fully detected.

    Args:
        features: Feature data for determining signal direction
        htf_bias: HTFBias object containing sweep information
        max_points: Maximum points this factor can contribute

    Returns:
        Score contribution (can be negative for opposing sweeps)
    """
    direction = determine_direction(features, htf_bias)

    # Check HTF liquidity sweep first (full points)
    if htf_bias.liquidity_sweep_detected:
        sweep_type = htf_bias.liquidity_sweep_type

        if direction == "neutral" or sweep_type is None:
            return max_points * 0.25  # Sweep detected but direction unclear

        # Aligned sweep: bullish sweep + long OR bearish sweep + short
        if sweep_type == "bullish" and direction == "long":
            return max_points
        elif sweep_type == "bearish" and direction == "short":
            return max_points

        # Opposing sweep gets penalty (negative points)
        return -max_points / 2

    # Check 1M features for sweep_direction (partial points)
    # This allows scoring even when HTF sweep detection hasn't triggered
    sweep_direction = features.get("sweep_direction")
    if sweep_direction is not None:
        if direction == "long" and sweep_direction == "bullish":
            return max_points * 0.5  # Partial credit for 1M sweep alignment
        elif direction == "short" and sweep_direction == "bearish":
            return max_points * 0.5  # Partial credit for 1M sweep alignment

    # No sweep detected - give small base points if direction is clear
    # This softens the penalty for missing sweep data
    if direction in ("long", "short"):
        return max_points * 0.1  # Small base credit for clear direction

    return 0.0


def calculate_vwap_deviation(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate VWAP deviation score for fade setups."""
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)

    if vwap == 0:
        return 0.0

    deviation = abs((close - vwap) / vwap * 100)

    # Significant deviation (>0.5%)
    if deviation > 0.5:
        return max_points

    return 0.0


def calculate_rsi_extreme(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate RSI extreme score for fade setups."""
    rsi = features.get("rsi", 50)

    if rsi < 30 or rsi > 70:
        return max_points

    return 0.0


def calculate_rejection_candle(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate rejection candle score for fade setups.

    Analyzes candle structure to detect rejection patterns indicating
    potential reversal. Awards points for wicks indicating rejection
    in the direction supporting the fade setup, with confirmation from
    VWAP proximity and candle body direction.

    Criteria (all required for full points):
    - Strong rejection wick: Wick > 2x body size
    - VWAP proximity: Close within 0.15% of VWAP (rejection back into value)
    - Candle body direction: Closes in fade direction
      * Long fade: bullish close (close > open)
      * Short fade: bearish close (close < open)

    Scoring:
    - All 3 conditions met: full points
    - Wick + 1 other condition: half points
    - Wick only or no wick: 0 points

    Args:
        features: Feature series containing OHLC data and VWAP
        htf_bias: HTFBias object (direction indicates HTF bias direction)
        max_points: Maximum points this factor can contribute

    Returns:
        Score contribution (0 to max_points)

    Example:
        For HTF bullish (long direction), VWAP_FADE bounces from oversold
        → look for LOWER wick rejection + close near VWAP + bullish close

        For HTF bearish (short direction), VWAP_FADE pulls back from overbought
        → look for UPPER wick rejection + close near VWAP + bearish close
    """
    open_price = features.get("open", 0)
    high = features.get("high", 0)
    low = features.get("low", 0)
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)

    # Validate OHLC data
    if high == 0 or low == 0 or high < low or vwap == 0:
        return 0.0

    # Calculate body and wicks
    body = abs(close - open_price)
    upper_wick = high - max(open_price, close)
    lower_wick = min(open_price, close) - low

    # Avoid division by zero for very small bodies (near-doji candles)
    # For doji-like candles, check if wick is at least 0.1% of price
    min_wick_threshold = high * 0.001 if body < 0.01 else body

    # Check VWAP proximity (within 0.15%)
    vwap_proximity = abs(close - vwap) / vwap < 0.0015

    # Check candle body direction
    bullish_close = close > open_price
    bearish_close = close < open_price

    # HTF bullish (long): VWAP_FADE bounces from oversold
    # Need: lower wick + close near VWAP + bullish close
    if htf_bias.direction == "long":
        has_strong_wick = lower_wick > body * 2
        has_moderate_wick = lower_wick > max(body, min_wick_threshold)
        correct_body = bullish_close

        if has_strong_wick:
            # Strong wick exists, check other conditions
            conditions_met = sum([vwap_proximity, correct_body])
            if conditions_met == 2:
                # All 3 conditions: full points
                return max_points
            elif conditions_met == 1:
                # Wick + 1 condition: half points
                return max_points * 0.5
            # Wick only: no points (quality filter)
            return 0.0
        elif has_moderate_wick and vwap_proximity and correct_body:
            # Moderate wick with both confirmations: partial credit
            return max_points * 0.5

    # HTF bearish (short): VWAP_FADE pulls back from overbought
    # Need: upper wick + close near VWAP + bearish close
    elif htf_bias.direction == "short":
        has_strong_wick = upper_wick > body * 2
        has_moderate_wick = upper_wick > max(open_price, min_wick_threshold)
        correct_body = bearish_close

        if has_strong_wick:
            # Strong wick exists, check other conditions
            conditions_met = sum([vwap_proximity, correct_body])
            if conditions_met == 2:
                # All 3 conditions: full points
                return max_points
            elif conditions_met == 1:
                # Wick + 1 condition: half points
                return max_points * 0.5
            # Wick only: no points (quality filter)
            return 0.0
        elif has_moderate_wick and vwap_proximity and correct_body:
            # Moderate wick with both confirmations: partial credit
            return max_points * 0.5

    return 0.0


def calculate_volume_spike(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate volume spike score for fade setups.

    Analyzes volume relative to recent average to detect institutional
    participation. High volume on reversal candles indicates strong
    conviction and increases fade setup reliability.

    Criteria:
    - Strong spike: Volume >= 1.5x average (full points)
    - Moderate spike: Volume >= 1.2x average (partial points)
    - Normal/low volume: Below 1.2x average (no points)

    Args:
        features: Feature series containing volume and volume_sma_20
        htf_bias: HTFBias object (unused, kept for signature consistency)
        max_points: Maximum points this factor can contribute

    Returns:
        Score contribution (0 to max_points)

    Note:
        If volume_sma_20 is not available in features, gives partial credit
        for non-zero volume to avoid penalizing data availability issues.
    """
    volume = features.get("volume", 0)
    volume_sma = features.get("volume_sma_20", None)

    # If no SMA available, return 0.0 (strict scoring - no free points)
    # This ensures volume spike scoring is based on actual volume comparison
    if volume_sma is None or pd.isna(volume_sma) or volume_sma == 0:
        logger.debug("volume_sma_20 unavailable - no points for volume_spike")
        return 0.0

    # Calculate volume ratio
    volume_ratio = volume / volume_sma

    # Award points based on volume spike magnitude
    if volume_ratio >= 1.5:
        return max_points
    elif volume_ratio >= 1.2:
        return max_points * 0.5

    return 0.0


def determine_direction(features: pd.Series, htf_bias: HTFBias) -> str:
    """Determine trade direction based on features.

    Uses local indicators (VWAP, EMA) as primary signals, with HTF bias
    as a tie-breaker when local signals are inconclusive.

    Args:
        features: Feature data
        htf_bias: HTFBias object

    Returns:
        Direction: "long", "short", or "neutral"
    """
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)
    ema_9 = features.get("ema_9", 0)
    ema_20 = features.get("ema_20", 0)

    # Bullish indicators
    bullish_signals = 0
    if close > vwap:
        bullish_signals += 1
    if ema_9 > ema_20:
        bullish_signals += 1

    # Bearish indicators
    bearish_signals = 0
    if close < vwap:
        bearish_signals += 1
    if ema_9 < ema_20:
        bearish_signals += 1

    result = "neutral"
    if bullish_signals > bearish_signals:
        result = "long"
    elif bearish_signals > bullish_signals:
        result = "short"
    else:
        # Tie-breaker: Use HTF bias direction when local signals are tied
        # This prevents excessive "neutral" results that cascade to zero scores
        if htf_bias and htf_bias.direction in ("long", "short"):
            result = htf_bias.direction
            logger.debug(
                f"Direction tie-break: using HTF bias direction '{result}' "
                f"(local: bullish={bullish_signals}, bearish={bearish_signals})"
            )
        else:
            # If HTF is also neutral, use VWAP position as final tie-breaker
            # Close > VWAP suggests bullish bias, Close < VWAP suggests bearish
            if close > vwap:
                result = "long"
                logger.debug(
                    f"Direction tie-break: using VWAP position 'long' "
                    f"(close={close:.2f} > vwap={vwap:.2f})"
                )
            elif close < vwap:
                result = "short"
                logger.debug(
                    f"Direction tie-break: using VWAP position 'short' "
                    f"(close={close:.2f} < vwap={vwap:.2f})"
                )
            # If close == vwap exactly, remain neutral (very rare)

    return result


def classify_confidence(score: float, setup_type: str) -> str:
    """Classify confidence level based on score and setup type.

    Args:
        score: Numerical score (0-10)
        setup_type: Setup type name

    Returns:
        Confidence level: "A+", "Watch", or "Reject"

    Thresholds:
        - VWAP_FADE: A+ >= 9, Watch 6-8.9, Reject < 6
        - Others: A+ >= 8, Watch 6-7.9, Reject < 6
    """
    # Load config to get thresholds
    config = load_scoring_config()

    # Get min_score for this setup type
    min_score = config.setup_types[setup_type]["min_score"]

    if score >= min_score:
        return "A+"
    elif score >= 6.0:
        return "Watch"
    else:
        return "Reject"


def build_rationale(
    features: pd.Series, htf_bias: HTFBias, factor_scores: dict, setup_type: str
) -> str:
    """Build human-readable rationale for the signal.

    Args:
        features: Feature data
        htf_bias: HTFBias object
        factor_scores: Individual factor scores
        setup_type: Setup type name

    Returns:
        Human-readable rationale string
    """
    parts = []

    # Setup type
    parts.append(f"{setup_type} setup")

    # HTF bias
    parts.append(
        f"HTF {htf_bias.bias} ({htf_bias.confidence} confidence, score={htf_bias.score:.1f})"
    )

    # VWAP position
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)
    if close > vwap:
        parts.append("above VWAP")
    elif close < vwap:
        parts.append("below VWAP")

    # RSI state
    rsi = features.get("rsi", 50)
    if rsi < 30:
        parts.append(f"RSI oversold ({rsi:.1f})")
    elif rsi > 70:
        parts.append(f"RSI overbought ({rsi:.1f})")
    elif 40 <= rsi <= 60:
        parts.append(f"RSI mid-reset ({rsi:.1f})")

    # DXY alignment
    if (
        htf_bias.dxy_alignment
        and htf_bias.dxy_corr_1h is not None
        and htf_bias.dxy_corr_15m is not None
    ):
        parts.append(
            f"DXY aligned (1H:{htf_bias.dxy_corr_1h:.2f}, 15M:{htf_bias.dxy_corr_15m:.2f})"
        )

    # EMA alignment
    if factor_scores.get("ema_stack", 0) > 0:
        parts.append("EMA alignment confirmed")

    # VWAP trend confirmation
    if htf_bias.vwap_trend_confirmed:
        parts.append("VWAP trend confirmed")

    # Structure events
    if htf_bias.bos_detected:
        parts.append("BOS detected")
    if htf_bias.choch_detected:
        parts.append("CHoCH detected")

    return ", ".join(parts)
