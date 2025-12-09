"""RuleEngine scoring functions.

This module implements the core scoring logic that transforms feature data
into Signal objects with SOP-compliant scoring and classification.
"""

import pandas as pd
from common.logger import get_logger

from rule_engine.config_loader import load_scoring_config
from rule_engine.htf.integration import adjust_score_with_htf, validate_signal_with_htf
from rule_engine.htf.types import HTFBias
from rule_engine.signal import Signal

logger = get_logger(__name__)


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
        )

    # Load scoring configuration
    config = load_scoring_config()

    # Determine setup type based on features
    setup_type = determine_setup_type(features, htf_bias)

    # Get setup configuration and weights
    setup_config = config.setup_types[setup_type]
    weights = setup_config["weights"]

    # Calculate individual factor scores
    factor_scores = calculate_factor_scores(features, htf_bias, weights, setup_type)

    # Calculate base score (sum of all factors, capped at 10)
    base_score = min(sum(factor_scores.values()), 10.0)

    # Apply HTF-based score adjustments
    adjusted_score, htf_adjustments = adjust_score_with_htf(
        base_score, htf_bias, signal_direction
    )

    # Add HTF adjustments to factor scores for transparency
    factor_scores.update(htf_adjustments)

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
        f"htf_bonus={factor_scores.get('htf_bonus', 0):.2f} | "
        f"base={base_score:.2f}, final={adjusted_score:.2f}"
    )

    # Classify confidence level based on adjusted score
    confidence = classify_confidence(adjusted_score, setup_type)

    # Generate human-readable rationale
    rationale = build_rationale(features, htf_bias, factor_scores, setup_type)

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
    )


def determine_setup_type(features: pd.Series, htf_bias: HTFBias) -> str:
    """Determine setup type based on market features.

    Args:
        features: Feature data including VWAP, RSI, DXY correlation
        htf_bias: HTFBias object

    Returns:
        Setup type name: "VWAP_RECLAIM", "VWAP_FADE", or "DXY_CONTINUATION"

    Logic:
        - VWAP_FADE: RSI extreme (<30 or >70) with significant VWAP deviation
        - DXY_CONTINUATION: Strong DXY correlation (<-0.8)
        - VWAP_RECLAIM: Default continuation setup
    """
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)
    rsi = features.get("rsi", 50)
    dxy_corr = features.get("dxy_corr")

    # Calculate VWAP deviation percentage
    vwap_dev = abs((close - vwap) / vwap * 100) if vwap != 0 else 0

    # VWAP_FADE: Extreme RSI with large VWAP deviation
    if (rsi < 30 or rsi > 70) and vwap_dev > 0.5:
        return "VWAP_FADE"

    # DXY_CONTINUATION: Very strong inverse correlation
    if dxy_corr is not None and dxy_corr < -0.8:
        return "DXY_CONTINUATION"

    # Default: VWAP_RECLAIM (continuation setup)
    return "VWAP_RECLAIM"


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
            features, htf_bias, weights["structure_alignment"]
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
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate structure alignment score with BOS bonus.

    Base: Direction matches HTF bias (70% of max)
    Bonus: BOS detected (+15%)

    Note: CHoCH (Change of Character) indicates potential reversal and is
    penalized in adjust_score_with_htf, not rewarded here.

    Args:
        features: Feature data for determining signal direction
        htf_bias: HTFBias object containing structure information
        max_points: Maximum points this factor can contribute

    Returns:
        Score contribution (0 to max_points)
    """
    direction = determine_direction(features, htf_bias)

    # Base alignment
    if htf_bias.direction == direction and direction != "neutral":
        score = max_points * 0.7
    else:
        return 0.0

    # BOS bonus (indicates continuation)
    if htf_bias.bos_detected:
        score += max_points * 0.15

    # CHoCH is NOT rewarded here - it indicates potential reversal
    # and is penalized in adjust_score_with_htf instead

    return min(score, max_points)


def calculate_vwap_relation(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate VWAP relation score.

    Awards points if price is correctly positioned relative to VWAP.
    """
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)

    if htf_bias.direction == "long" and close > vwap:
        return max_points
    elif htf_bias.direction == "short" and close < vwap:
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
    """
    ema_9 = features.get("ema_9", 0)
    ema_20 = features.get("ema_20", 0)
    ema_50 = features.get("ema_50", 0)

    # Bullish: 9 > 20 > 50
    if htf_bias.direction == "long" and ema_9 > ema_20 > ema_50:
        return max_points

    # Bearish: 9 < 20 < 50
    if htf_bias.direction == "short" and ema_9 < ema_20 < ema_50:
        return max_points

    # Partial alignment gets partial points
    if htf_bias.direction == "long" and ema_9 > ema_20:
        return max_points / 2

    if htf_bias.direction == "short" and ema_9 < ema_20:
        return max_points / 2

    return 0.0


def calculate_dxy_correlation(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate DXY correlation score.

    Awards points if inverse correlation is strong (<-0.6).
    """
    dxy_corr = features.get("dxy_corr")

    if dxy_corr is not None and dxy_corr < -0.6:
        return max_points

    return 0.0


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
    Penalty if sweep opposes direction.
    Returns 0.0 for ambiguous cases (neutral direction or None sweep type).

    Args:
        features: Feature data for determining signal direction
        htf_bias: HTFBias object containing sweep information
        max_points: Maximum points this factor can contribute

    Returns:
        Score contribution (can be negative for opposing sweeps)
    """
    if not htf_bias.liquidity_sweep_detected:
        return 0.0

    direction = determine_direction(features, htf_bias)
    sweep_type = htf_bias.liquidity_sweep_type

    # Ambiguous cases: can't determine alignment, return 0.0
    if direction == "neutral" or sweep_type is None:
        return 0.0

    # Aligned sweep: bullish sweep + long OR bearish sweep + short
    if sweep_type == "bullish" and direction == "long":
        return max_points
    elif sweep_type == "bearish" and direction == "short":
        return max_points

    # Opposing sweep gets penalty (negative points)
    return -max_points / 2


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

    Simplified: Awards points if conditions suggest rejection.
    """
    # Placeholder: In real implementation, would analyze candle pattern
    # For now, award partial points
    return max_points / 2


def calculate_volume_spike(
    features: pd.Series, htf_bias: HTFBias, max_points: float
) -> float:
    """Calculate volume spike score for fade setups.

    Simplified: Awards points if volume conditions met.
    """
    # Placeholder: In real implementation, would compare volume to average
    # For now, award partial points
    return max_points / 2


def determine_direction(features: pd.Series, htf_bias: HTFBias) -> str:
    """Determine trade direction based on features.

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

    if bullish_signals > bearish_signals:
        return "long"
    elif bearish_signals > bullish_signals:
        return "short"

    return "neutral"


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
