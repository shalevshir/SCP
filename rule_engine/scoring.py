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
        )

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

    # VWAP_FADE: Extreme RSI with large VWAP deviation
    if (rsi < 30 or rsi > 70) and vwap_dev > 0.5:
        return "VWAP_FADE"

    # DXY_CONTINUATION: Strict multi-factor validation
    from rule_engine.setup_detectors.dxy_continuation import detect_dxy_continuation

    if detect_dxy_continuation(features, htf_bias):
        return "DXY_CONTINUATION"

    # VWAP_RECLAIM: Requires full reclaim sequence validation
    # Import here to avoid circular dependency
    from rule_engine.htf.vwap.reclaim import validate_reclaim_prerequisites

    is_valid, reason = validate_reclaim_prerequisites(htf_bias)

    if is_valid:
        return "VWAP_RECLAIM"
    else:
        # Log rejection reason for debugging
        logger.debug(f"VWAP_RECLAIM rejected: {reason}")
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

    # Base requirement: direction must match
    if htf_bias.direction != direction or direction == "neutral":
        return 0.0

    # VWAP_RECLAIM: Loosened requirements per SOP
    if setup_type == "VWAP_RECLAIM":
        # Skip chop and clarity hard rejections
        # VWAP_RECLAIM can work during micro chop (reclaim is structural, not momentum)

        # Still require liquidity sweep (prerequisite validates this)
        if not htf_bias.liquidity_sweep_detected:
            logger.debug("VWAP_RECLAIM structure: no liquidity sweep")
            return max_points * 0.3  # Reduced but not zero

        # Still require recent BOS
        if htf_bias.bars_since_bos is None or htf_bias.bars_since_bos > 15:
            logger.debug(
                f"VWAP_RECLAIM structure: BOS stale "
                f"(bars_since_bos={htf_bias.bars_since_bos})"
            )
            return max_points * 0.3  # Reduced but not zero

        # Calculate score for VWAP_RECLAIM (tolerant scoring)
        score = max_points * 0.5  # Minimum base (50%)

        # Bonus for high clarity (but not required)
        if htf_bias.structure_clarity >= 0.7:
            score += max_points * 0.3
        elif htf_bias.structure_clarity >= 0.5:
            score += max_points * 0.15

        # Bonus for very recent BOS
        if htf_bias.bars_since_bos <= 10:
            score += max_points * 0.2

        logger.debug(
            f"VWAP_RECLAIM structure (tolerant): clarity={htf_bias.structure_clarity:.2f}, "
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
