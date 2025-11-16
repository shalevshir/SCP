"""RuleEngine scoring functions.

This module implements the core scoring logic that transforms feature data
into Signal objects with SOP-compliant scoring and classification.
"""

from datetime import datetime

import pandas as pd

from rule_engine.config_loader import load_scoring_config
from rule_engine.signal import Signal


def score_signal(features: pd.Series, context: dict) -> Signal:
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
        context: Dict containing contextual data:
            - htf_bias: Higher timeframe bias ("bullish", "bearish", "neutral")
            - htf_direction: HTF direction ("long", "short", "neutral")
            - htf_score: Optional HTF bias score (for bonus calculation)
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
        >>> context = {
        ...     "htf_bias": "bullish",
        ...     "htf_direction": "long",
        ...     "session_ok": True,
        ...     "enforcer_tier": "Early Mild",
        ... }
        >>> signal = score_signal(features, context)
    """
    # Load scoring configuration
    config = load_scoring_config()

    # Determine setup type based on features
    setup_type = determine_setup_type(features, context)

    # Get setup configuration and weights
    setup_config = config.setup_types[setup_type]
    weights = setup_config["weights"]

    # Calculate individual factor scores
    factor_scores = calculate_factor_scores(features, context, weights, setup_type)

    # Calculate total score (sum of all factors, capped at 10)
    total_score = min(sum(factor_scores.values()), 10.0)

    # Classify confidence level
    confidence = classify_confidence(total_score, setup_type)

    # Generate human-readable rationale
    rationale = build_rationale(features, context, factor_scores, setup_type)

    # Create validation flags (initially True, will be validated later)
    validation_flags = {
        "session_ok": context.get("session_ok", True),
        "tier_ok": True,
        "dxy_alignment_ok": features.get("dxy_corr", 0) < -0.6,
        "htf_bias_ok": context.get("htf_direction") == determine_direction(features, context),
    }

    # Create and return Signal object
    return Signal(
        timestamp=features["timestamp"],
        symbol=features["symbol"],
        timeframe=features["timeframe"],
        direction=context.get("htf_direction", "neutral"),
        setup_type=setup_type,
        htf_bias=context.get("htf_bias", "neutral"),
        score=total_score,
        confidence=confidence,
        factors=factor_scores,
        rationale=rationale,
        validation_flags=validation_flags,
        enforcer_tier=context.get("enforcer_tier", "Conservative"),
    )


def determine_setup_type(features: pd.Series, context: dict) -> str:
    """Determine setup type based on market features.

    Args:
        features: Feature data including VWAP, RSI, DXY correlation
        context: Context including HTF direction

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
    dxy_corr = features.get("dxy_corr", 0)

    # Calculate VWAP deviation percentage
    vwap_dev = abs((close - vwap) / vwap * 100) if vwap != 0 else 0

    # VWAP_FADE: Extreme RSI with large VWAP deviation
    if (rsi < 30 or rsi > 70) and vwap_dev > 0.5:
        return "VWAP_FADE"

    # DXY_CONTINUATION: Very strong inverse correlation
    if dxy_corr < -0.8:
        return "DXY_CONTINUATION"

    # Default: VWAP_RECLAIM (continuation setup)
    return "VWAP_RECLAIM"


def calculate_factor_scores(
    features: pd.Series, context: dict, weights: dict, setup_type: str
) -> dict[str, float]:
    """Calculate individual factor scores based on setup type.

    Args:
        features: Feature data
        context: Context data
        weights: Dict of factor weights from config
        setup_type: Setup type name

    Returns:
        Dict mapping factor names to their scores
    """
    scores = {}

    # Structure alignment: Price action matches HTF bias
    if "structure_alignment" in weights:
        scores["structure_alignment"] = calculate_structure_alignment(
            features, context, weights["structure_alignment"]
        )

    # VWAP relation: Position relative to VWAP
    if "vwap_relation" in weights:
        scores["vwap_relation"] = calculate_vwap_relation(
            features, context, weights["vwap_relation"]
        )

    # RSI state: RSI in optimal zone
    if "rsi_state" in weights:
        scores["rsi_state"] = calculate_rsi_state(
            features, context, weights["rsi_state"]
        )

    if "rsi_mid_reset" in weights:
        scores["rsi_mid_reset"] = calculate_rsi_state(
            features, context, weights["rsi_mid_reset"]
        )

    # EMA stack: EMA alignment
    if "ema_stack" in weights:
        scores["ema_stack"] = calculate_ema_stack(
            features, context, weights["ema_stack"]
        )

    # DXY correlation
    if "dxy_corr" in weights:
        scores["dxy_corr"] = calculate_dxy_correlation(
            features, context, weights["dxy_corr"]
        )

    # HTF bonus
    if "htf_bonus" in weights:
        scores["htf_bonus"] = calculate_htf_bonus(
            features, context, weights["htf_bonus"]
        )

    # Fade-specific factors
    if "vwap_deviation" in weights:
        scores["vwap_deviation"] = calculate_vwap_deviation(
            features, context, weights["vwap_deviation"]
        )

    if "rsi_extreme" in weights:
        scores["rsi_extreme"] = calculate_rsi_extreme(
            features, context, weights["rsi_extreme"]
        )

    if "rejection_candle" in weights:
        scores["rejection_candle"] = calculate_rejection_candle(
            features, context, weights["rejection_candle"]
        )

    if "volume_spike" in weights:
        scores["volume_spike"] = calculate_volume_spike(
            features, context, weights["volume_spike"]
        )

    return scores


def calculate_structure_alignment(
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate structure alignment score.

    Awards points if direction matches HTF bias.
    """
    htf_direction = context.get("htf_direction", "neutral")
    direction = determine_direction(features, context)

    if htf_direction == direction and direction != "neutral":
        return max_points

    return 0.0


def calculate_vwap_relation(
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate VWAP relation score.

    Awards points if price is correctly positioned relative to VWAP.
    """
    close = features.get("close", 0)
    vwap = features.get("vwap", 0)
    htf_direction = context.get("htf_direction", "neutral")

    if htf_direction == "long" and close > vwap:
        return max_points
    elif htf_direction == "short" and close < vwap:
        return max_points

    return 0.0


def calculate_rsi_state(
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate RSI state score.

    Awards points if RSI is in mid-reset zone (40-60) for continuations.
    """
    rsi = features.get("rsi", 50)

    if 40 <= rsi <= 60:
        return max_points

    return 0.0


def calculate_ema_stack(
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate EMA stack score.

    Awards points if EMAs are properly aligned with HTF direction.
    """
    ema_9 = features.get("ema_9", 0)
    ema_20 = features.get("ema_20", 0)
    ema_50 = features.get("ema_50", 0)
    htf_direction = context.get("htf_direction", "neutral")

    # Bullish: 9 > 20 > 50
    if htf_direction == "long" and ema_9 > ema_20 > ema_50:
        return max_points

    # Bearish: 9 < 20 < 50
    if htf_direction == "short" and ema_9 < ema_20 < ema_50:
        return max_points

    # Partial alignment gets partial points
    if htf_direction == "long" and ema_9 > ema_20:
        return max_points / 2

    if htf_direction == "short" and ema_9 < ema_20:
        return max_points / 2

    return 0.0


def calculate_dxy_correlation(
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate DXY correlation score.

    Awards points if inverse correlation is strong (<-0.6).
    """
    dxy_corr = features.get("dxy_corr", 0)

    if dxy_corr < -0.6:
        return max_points

    return 0.0


def calculate_htf_bonus(
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate HTF bonus score.

    Awards bonus point if HTF bias score is >= 8.
    """
    htf_score = context.get("htf_score", 0)

    if htf_score >= 8.0:
        return max_points

    return 0.0


def calculate_vwap_deviation(
    features: pd.Series, context: dict, max_points: float
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
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate RSI extreme score for fade setups."""
    rsi = features.get("rsi", 50)

    if rsi < 30 or rsi > 70:
        return max_points

    return 0.0


def calculate_rejection_candle(
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate rejection candle score for fade setups.

    Simplified: Awards points if conditions suggest rejection.
    """
    # Placeholder: In real implementation, would analyze candle pattern
    # For now, award partial points
    return max_points / 2


def calculate_volume_spike(
    features: pd.Series, context: dict, max_points: float
) -> float:
    """Calculate volume spike score for fade setups.

    Simplified: Awards points if volume conditions met.
    """
    # Placeholder: In real implementation, would compare volume to average
    # For now, award partial points
    return max_points / 2


def determine_direction(features: pd.Series, context: dict) -> str:
    """Determine trade direction based on features.

    Args:
        features: Feature data
        context: Context data

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
    features: pd.Series, context: dict, factor_scores: dict, setup_type: str
) -> str:
    """Build human-readable rationale for the signal.

    Args:
        features: Feature data
        context: Context data
        factor_scores: Individual factor scores
        setup_type: Setup type name

    Returns:
        Human-readable rationale string
    """
    parts = []

    # Setup type
    parts.append(f"{setup_type} setup")

    # HTF bias
    htf_bias = context.get("htf_bias", "neutral")
    parts.append(f"HTF {htf_bias}")

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

    # DXY correlation
    dxy_corr = features.get("dxy_corr", 0)
    if dxy_corr < -0.6:
        parts.append(f"DXY correlation {dxy_corr:.2f}")

    # EMA alignment
    if factor_scores.get("ema_stack", 0) > 0:
        parts.append("EMA alignment confirmed")

    return ", ".join(parts)

