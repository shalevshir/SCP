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
    structure_1h = (
        features_1h.get("structure_label")
        or features_1h.get("structure_type", "")
    )
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
    structure_15m = (
        features_15m.get("structure_label")
        or features_15m.get("structure_type", "")
    )
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
        f"bullish={bullish_signals}, bearish={bearish_signals}, "
        f"score={total_score:.1f})"
    )

    return htf_bias, htf_direction, total_score


def compute_htf_bias(
    features_1h: pd.Series,
    features_15m: pd.Series,
    dxy_1h: pd.DataFrame | None = None,
    df_15m: pd.DataFrame | None = None,
    df_1h: pd.DataFrame | None = None,
    sweep_events_15m: pd.Series | None = None,
    timestamp: pd.Timestamp | None = None,
) -> HTFBias:
    """Compute comprehensive HTF bias with all components.

    This is the new interface that returns a full HTFBias object with all
    structure, VWAP, DXY, seasonality, and conflict detection components.

    Args:
        features_1h: 1h timeframe features
        features_15m: 15m timeframe features
        dxy_1h: Optional DXY 1h DataFrame for chop detection (needs OHLC columns)
        df_15m: Optional 15M price DataFrame for price chop detection (needs OHLC columns)
        df_1h: Optional 1H price DataFrame for BOS/CHoCH/FVG detection (needs OHLC columns)
        sweep_events_15m: Optional Series with liquidity sweep events from detect_liquidity_sweeps()
        timestamp: Current timestamp for seasonality

    Returns:
        HTFBias object with all components populated including conflict detection

    Task: Create final HTFBias object
    Epic: Full HTF Bias Engine Upgrade
    Status: In Progress
    """
    from rule_engine.htf.dxy import detect_dxy_chop
    from rule_engine.htf.seasonality import (
        apply_seasonality_adjustment,
        get_seasonality_period,
    )
    from rule_engine.htf.structure import (
        detect_swings,
        detect_bos,
        detect_choch,
        detect_fvg,
        check_fvg_filled,
    )
    from rule_engine.htf.vwap.fvg import score_fvg_alignment
    
    # Use legacy logic to compute base bias and score
    bias, direction, score = compute_htf_bias_multi_timeframe(features_1h, features_15m)
    
    # Store original bias before any neutralization for conflict detection
    original_bias = bias
    original_score = score
    
    # Detect DXY chop if data provided
    dxy_chop_detected = False
    if dxy_1h is not None and len(dxy_1h) > 0:
        try:
            chop_series = detect_dxy_chop(dxy_1h)
            # Get the latest chop detection value
            if len(chop_series) > 0:
                dxy_chop_detected = bool(chop_series.iloc[-1])
                
                if dxy_chop_detected:
                    # Force HTF bias to neutral when DXY is in chop
                    logger.warning(
                        "DXY chop detected - forcing HTF bias to neutral "
                        f"(original: {bias}, score: {score:.1f})"
                    )
                    bias = "neutral"
                    direction = "neutral"
                    # Optionally reduce score to reflect uncertainty
                    score = min(score, 5.0)
        except Exception as e:
            logger.error(f"Error detecting DXY chop: {e}")
            # Continue without chop detection rather than failing
    
    # Check for conflicts between timeframes
    # Use ORIGINAL bias (before DXY chop neutralization) for conflict detection
    from rule_engine.htf.conflicts import (
        detect_structure_conflict,
        detect_price_chop_15m,
        detect_sweep_against_trend,
    )
    
    conflict_detected = False
    conflict_reason = None
    
    # Rule 1: Structure conflict between 1H and 15M
    is_conflict, reason = detect_structure_conflict(
        structure_1h=features_1h.get("structure_label") or features_1h.get("structure_type"),
        structure_15m=features_15m.get("structure_label") or features_15m.get("structure_type"),
    )
    if is_conflict:
        conflict_detected = True
        conflict_reason = reason
    
    # Rule 2: 15M price chop
    if not conflict_detected and df_15m is not None and len(df_15m) > 0:
        try:
            if detect_price_chop_15m(df_15m):
                conflict_detected = True
                conflict_reason = "15M price action in chop"
        except Exception as e:
            logger.error(f"Error detecting 15M price chop: {e}")
            # Continue without chop detection
    
    # Rule 3: Liquidity sweep against trend
    # IMPORTANT: Use original_bias (before DXY chop neutralization)
    # to detect sweep conflicts based on the actual market structure
    if not conflict_detected and sweep_events_15m is not None:
        try:
            is_conflict, reason = detect_sweep_against_trend(
                bias=original_bias,  # Use original bias, not neutralized one
                sweep_events=sweep_events_15m,
            )
            if is_conflict:
                conflict_detected = True
                conflict_reason = reason
        except Exception as e:
            logger.error(f"Error detecting sweep conflict: {e}")
            # Continue without sweep conflict detection
    
    # Apply neutralization if conflict detected
    if conflict_detected:
        logger.warning(
            f"Conflict detected - forcing HTF bias to neutral: {conflict_reason} "
            f"(original: {original_bias}, score: {original_score:.1f})"
        )
        bias = "neutral"
        direction = "neutral"
        score = min(score, 5.0)
    
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
    
    # Re-cap score after seasonality if neutralization conditions exist
    if dxy_chop_detected or conflict_detected:
        # Re-cap score after any post-processing to enforce neutral bias
        score = min(score, 5.0)
    
    # Determine confidence based on adjusted score
    if score >= 8.0:
        confidence = "high"
    elif score >= 6.0:
        confidence = "medium"
    else:
        confidence = "low"
    
    # === POPULATE MISSING FIELDS ===
    
    # 1. BOS/CHoCH detection from 1H data
    bos_detected = False
    choch_detected = False
    if df_1h is not None and len(df_1h) > 0:
        try:
            swing_highs_1h, swing_lows_1h = detect_swings(df_1h, lookback=5)
            
            # Detect BOS events
            bos_series = detect_bos(df_1h, swing_highs_1h, swing_lows_1h)
            # Check if any BOS detected in recent bars
            if len(bos_series) > 0 and pd.notna(bos_series.iloc[-1]):
                bos_detected = True
            
            # Detect CHoCH events
            choch_series = detect_choch(df_1h, swing_highs_1h, swing_lows_1h)
            # Check if any CHoCH detected in recent bars
            if len(choch_series) > 0 and pd.notna(choch_series.iloc[-1]):
                choch_detected = True
                
        except Exception as e:
            logger.error(f"Error detecting BOS/CHoCH: {e}")
            # Continue without BOS/CHoCH detection
    
    # 2. Liquidity sweep detection from sweep_events_15m
    liquidity_sweep_detected = False
    liquidity_sweep_type = None
    if sweep_events_15m is not None and len(sweep_events_15m) > 0:
        try:
            # Get the most recent sweep event
            latest_sweep = sweep_events_15m.iloc[-1]
            if pd.notna(latest_sweep):
                liquidity_sweep_detected = True
                # Determine sweep type based on event label
                if latest_sweep == "sweep_high":
                    liquidity_sweep_type = "bearish"  # Sweep high = bearish sweep
                elif latest_sweep == "sweep_low":
                    liquidity_sweep_type = "bullish"  # Sweep low = bullish sweep
        except Exception as e:
            logger.error(f"Error extracting liquidity sweep: {e}")
            # Continue without sweep detection
    
    # 3. VWAP metrics from features_1h
    vwap_1h = features_1h.get("vwap")
    vwap_distance_1h = None
    vwap_slope_1h = None
    vwap_trend_confirmed = False
    
    if vwap_1h is not None and not pd.isna(vwap_1h):
        # Calculate VWAP distance as percentage
        close_1h = features_1h.get("close")
        if close_1h is not None and not pd.isna(close_1h) and vwap_1h > 0:
            vwap_distance_1h = ((close_1h - vwap_1h) / vwap_1h) * 100
        
        # Extract VWAP slope from features if available
        vwap_slope_1h = features_1h.get("vwap_slope")
        
        # Determine VWAP trend confirmation
        # IMPORTANT: Use original_bias to reflect underlying market structure
        # even when bias is neutralized due to DXY chop or conflicts
        if original_bias == "bullish" and vwap_distance_1h is not None and vwap_distance_1h > 0:
            vwap_trend_confirmed = True
        elif original_bias == "bearish" and vwap_distance_1h is not None and vwap_distance_1h < 0:
            vwap_trend_confirmed = True
    
    # 4. FVG alignment score
    fvg_alignment_score = 0.0
    if df_1h is not None and len(df_1h) >= 3:
        try:
            # Detect FVGs on 1H timeframe
            fvg_df = detect_fvg(df_1h)
            if len(fvg_df) > 0:
                # Check which FVGs are filled
                fvg_df = check_fvg_filled(df_1h, fvg_df)
                # Score FVG alignment with current bias
                fvg_alignment_score = score_fvg_alignment(fvg_df, original_bias)
        except Exception as e:
            logger.error(f"Error calculating FVG alignment: {e}")
            # Continue with 0.0 score
    
    # 5. DXY alignment flag
    dxy_alignment = False
    dxy_corr_1h = features_1h.get("dxy_corr")
    dxy_corr_15m = features_15m.get("dxy_corr")
    
    # DXY alignment: strong negative correlation expected for both bull and bear bias
    # Gold typically moves inverse to DXY
    # IMPORTANT: Use original_bias to reflect underlying market structure
    # even when bias is neutralized due to DXY chop or conflicts
    if original_bias != "neutral":
        if (dxy_corr_1h is not None and not pd.isna(dxy_corr_1h) and dxy_corr_1h < -0.6 and
            dxy_corr_15m is not None and not pd.isna(dxy_corr_15m) and dxy_corr_15m < -0.6):
            dxy_alignment = True
    
    return HTFBias(
        bias=bias,
        direction=direction,
        score=score,
        confidence=confidence,
        structure_1h=(
            features_1h.get("structure_label")
            or features_1h.get("structure_type")
        ),
        structure_15m=(
            features_15m.get("structure_label")
            or features_15m.get("structure_type")
        ),
        bos_detected=bos_detected,
        choch_detected=choch_detected,
        liquidity_sweep_detected=liquidity_sweep_detected,
        liquidity_sweep_type=liquidity_sweep_type,
        vwap_1h=vwap_1h,
        vwap_distance_1h=vwap_distance_1h,
        vwap_slope_1h=vwap_slope_1h,
        vwap_trend_confirmed=vwap_trend_confirmed,
        fvg_alignment_score=fvg_alignment_score,
        dxy_corr_1h=dxy_corr_1h,
        dxy_corr_15m=dxy_corr_15m,
        dxy_chop_detected=dxy_chop_detected,
        dxy_alignment=dxy_alignment,
        seasonality_period=seasonality_period,
        seasonality_adjustment=seasonality_adjustment,
        conflict_detected=conflict_detected,
        conflict_reason=conflict_reason,
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

