"""HTF Bias Calculator - Main orchestrator.

This module orchestrates all HTF components to produce the final HTFBias object.
Migrated from rule_engine/htf_calculator.py for better modularity.

Supports both vectorized (backtesting) and incremental (live) processing modes.
"""

from __future__ import annotations

import pandas as pd

from common.logger import get_logger
from rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


def compute_htf_bias_multi_timeframe(
    features_1h: pd.Series,
    features_15m: pd.Series,
) -> tuple[str, str, float]:
    """Compute HTF bias from 1h and 15m timeframe features.

    This is the legacy interface maintained for backward compatibility.
    New code should use compute_htf_bias() which returns HTFBias object.

    Uses structure labels, EMA alignment, and DXY correlation from both
    timeframes to determine overall market bias and score its strength.

    Args:
        features_1h: 1h timeframe features with structure, EMAs, DXY correlation
        features_15m: 15m timeframe features with structure, EMAs, DXY correlation

    Returns:
        Tuple of (htf_bias, htf_direction, htf_score):
        - htf_bias: "bullish", "bearish", or "neutral"
        - htf_direction: "long", "short", or "neutral"
        - htf_score: Float 0-10 indicating bias strength and alignment

    Logic:
        - 1h structure is primary signal (worth 3 points)
        - 1h EMA stack is secondary signal (worth 2 points)
        - 15m structure confirms (worth 2 points)
        - 15m EMA stack confirms (worth 1 point)
        - DXY correlation adds bonus (worth 2 points)
        - Total score 0-10, minimum 6 for directional bias
    """
    total_score = 0.0
    bullish_signals = 0
    bearish_signals = 0

    # === 1H STRUCTURE (Primary Signal, 3 points) ===
    structure_1h = features_1h.get("structure_label") or features_1h.get("structure_type", "")
    if structure_1h in ("HH", "HL"):
        bullish_signals += 1
        total_score += 3.0
    elif structure_1h in ("LH", "LL"):
        bearish_signals += 1
        total_score += 3.0
    # No score if structure is unclear

    # === 1H EMA STACK (Secondary Signal, 2 points) ===
    # Only evaluate EMAs if all values are present and valid (not None, not 0, not NaN)
    ema_9_1h = features_1h.get("ema_9")
    ema_20_1h = features_1h.get("ema_20")
    ema_50_1h = features_1h.get("ema_50")

    # Check if all EMAs are valid (present, non-zero, non-NaN)
    emas_1h_valid = (
        ema_9_1h is not None
        and ema_20_1h is not None
        and ema_50_1h is not None
        and not pd.isna(ema_9_1h)
        and not pd.isna(ema_20_1h)
        and not pd.isna(ema_50_1h)
        and ema_9_1h > 0
        and ema_20_1h > 0
        and ema_50_1h > 0
    )

    if emas_1h_valid:
        if ema_9_1h > ema_20_1h > ema_50_1h:
            bullish_signals += 1
            total_score += 2.0
        elif ema_9_1h < ema_20_1h < ema_50_1h:
            bearish_signals += 1
            total_score += 2.0

    # === 15M STRUCTURE (Confirmation, 2 points) ===
    structure_15m = features_15m.get("structure_label") or features_15m.get("structure_type", "")
    if structure_15m in ("HH", "HL"):
        if bullish_signals > bearish_signals:
            # Confirms bullish bias
            total_score += 2.0
        elif bullish_signals == bearish_signals:
            # Breaks tie toward bullish
            bullish_signals += 1
            total_score += 2.0
    elif structure_15m in ("LH", "LL"):
        if bearish_signals > bullish_signals:
            # Confirms bearish bias
            total_score += 2.0
        elif bullish_signals == bearish_signals:
            # Breaks tie toward bearish
            bearish_signals += 1
            total_score += 2.0

    # === 15M EMA STACK (Confirmation, 1 point) ===
    # Only evaluate EMAs if all values are present and valid (not None, not 0, not NaN)
    ema_9_15m = features_15m.get("ema_9")
    ema_20_15m = features_15m.get("ema_20")
    ema_50_15m = features_15m.get("ema_50")

    # Check if all EMAs are valid (present, non-zero, non-NaN)
    emas_15m_valid = (
        ema_9_15m is not None
        and ema_20_15m is not None
        and ema_50_15m is not None
        and not pd.isna(ema_9_15m)
        and not pd.isna(ema_20_15m)
        and not pd.isna(ema_50_15m)
        and ema_9_15m > 0
        and ema_20_15m > 0
        and ema_50_15m > 0
    )

    if emas_15m_valid:
        if ema_9_15m > ema_20_15m > ema_50_15m:
            if bullish_signals > bearish_signals:
                total_score += 1.0
        elif ema_9_15m < ema_20_15m < ema_50_15m:
            if bearish_signals > bullish_signals:
                total_score += 1.0

    # === DXY CORRELATION (Bonus, 2 points) ===
    # Strong inverse correlation on both timeframes adds confidence
    dxy_corr_1h = features_1h.get("dxy_corr")
    dxy_corr_15m = features_15m.get("dxy_corr")

    dxy_aligned = (
        dxy_corr_1h is not None
        and not pd.isna(dxy_corr_1h)
        and dxy_corr_1h < -0.6
        and dxy_corr_15m is not None
        and not pd.isna(dxy_corr_15m)
        and dxy_corr_15m < -0.6
    )

    if dxy_aligned and (bullish_signals > 0 or bearish_signals > 0):
        total_score += 2.0

    # === DETERMINE BIAS AND DIRECTION ===
    # Need at least 2 signals in same direction for bias
    if bullish_signals >= 2 and bullish_signals > bearish_signals:
        htf_bias = "bullish"
        htf_direction = "long"
    elif bearish_signals >= 2 and bearish_signals > bullish_signals:
        htf_bias = "bearish"
        htf_direction = "short"
    else:
        htf_bias = "neutral"
        htf_direction = "neutral"
        # Reduce score for neutral/conflicting bias
        total_score = min(total_score, 5.0)

    # Cap score at 10
    total_score = min(total_score, 10.0)

    logger.debug(
        f"HTF Bias: {htf_bias} (1h: {structure_1h}, 15m: {structure_15m}, "
        f"bullish={bullish_signals}, bearish={bearish_signals}, score={total_score:.1f})"
    )

    return htf_bias, htf_direction, total_score


def compute_htf_bias(
    features_1h: pd.Series,
    features_15m: pd.Series,
    dxy_1h: pd.Series | None = None,
    timestamp: pd.Timestamp | None = None,
) -> HTFBias:
    """Compute comprehensive HTF bias with all components.

    This is the new interface that returns a full HTFBias object with all
    structure, VWAP, DXY, and seasonality components.

    Args:
        features_1h: 1h timeframe features
        features_15m: 15m timeframe features
        dxy_1h: Optional DXY 1h data for chop detection
        timestamp: Current timestamp for seasonality

    Returns:
        HTFBias object with all components populated

    Task: Create final HTFBias object
    Epic: Full HTF Bias Engine Upgrade
    Status: Not started
    """
    from rule_engine.htf.seasonality import (
        get_seasonality_period,
        apply_seasonality_adjustment,
    )
    
    # Use legacy logic to compute base bias and score
    bias, direction, score = compute_htf_bias_multi_timeframe(features_1h, features_15m)
    
    # Apply seasonality adjustment if timestamp provided
    seasonality_period = None
    seasonality_adjustment = 0.0
    
    if timestamp is not None:
        # Convert pandas Timestamp to datetime if needed
        if hasattr(timestamp, 'to_pydatetime'):
            dt = timestamp.to_pydatetime()
        else:
            dt = timestamp
        
        seasonality_period = get_seasonality_period(dt)
        dxy_corr = features_1h.get("dxy_corr")
        
        score, seasonality_adjustment = apply_seasonality_adjustment(
            base_score=score,
            period=seasonality_period,
            dxy_corr=dxy_corr,
        )
        
        logger.debug(
            "Seasonality integrated: period=%s | adjustment=%.2f | final_score=%.2f",
            seasonality_period,
            seasonality_adjustment,
            score
        )
    
    # Determine confidence based on adjusted score
    if score >= 8.0:
        confidence = "high"
    elif score >= 6.0:
        confidence = "medium"
    else:
        confidence = "low"
    
    return HTFBias(
        bias=bias,
        direction=direction,
        score=score,
        confidence=confidence,
        structure_1h=features_1h.get("structure_label") or features_1h.get("structure_type"),
        structure_15m=features_15m.get("structure_label") or features_15m.get("structure_type"),
        dxy_corr_1h=features_1h.get("dxy_corr"),
        dxy_corr_15m=features_15m.get("dxy_corr"),
        seasonality_period=seasonality_period,
        seasonality_adjustment=seasonality_adjustment,
    )


def is_london_or_ny_session(timestamp: pd.Timestamp) -> bool:
    """Check if timestamp falls within London or NY trading sessions.

    Args:
        timestamp: Timestamp to check (must be timezone-aware UTC)

    Returns:
        True if within London (07:00-09:00 UTC) or NY (13:30-16:00 UTC) sessions
    """
    if timestamp.tz is None:
        raise ValueError("Timestamp must be timezone-aware (UTC)")

    hour = timestamp.hour
    minute = timestamp.minute

    # London Open: 07:00-09:00 UTC
    if 7 <= hour < 9:
        return True

    # NY Open: 13:30-16:00 UTC
    if hour == 13 and minute >= 30:
        return True
    if 14 <= hour < 16:
        return True

    return False

