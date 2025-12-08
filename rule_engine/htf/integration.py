"""RuleEngine integration for HTF Bias.

Handles integration of HTF bias into RuleEngine scoring and validation.

Task: Integrate into RuleEngine scoring
Epic: Full HTF Bias Engine Upgrade
Status: Not started
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

import pandas as pd
from common.logger import get_logger

from data_layer.multi_timeframe_helpers import build_htf_dataframe_from_candles
from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar
from rule_engine.htf.calculator import compute_htf_bias
from rule_engine.htf.features import (
    StreamingHTFFeatureComputer,
    _precompute_htf_features,
)
from rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


def validate_signal_with_htf(
    signal_direction: str,
    htf_bias: HTFBias,
) -> tuple[bool, str]:
    """Validate trading signal against HTF bias.

    Args:
        signal_direction: Signal direction ("long", "short")
        htf_bias: HTF bias object

    Returns:
        Tuple of (is_valid, rejection_reason)

    Logic:
        - Reject signals opposing strong HTF bias
        - Allow signals aligned with HTF bias
        - Cautious on neutral HTF bias

    DoD:
        - RuleEngine rejects signals when HTF invalid
        - RuleEngine boosts signals when HTF strongly aligned
        - End-to-end test passes
    """
    # Rule 1: Reject if conflict detected
    if htf_bias.conflict_detected:
        reason = f"HTF conflict detected: {htf_bias.conflict_reason}"
        logger.info(f"Signal rejected - {reason}")
        return False, reason
    
    # Rule 2: Reject if DXY chop detected
    if htf_bias.dxy_chop_detected:
        reason = "DXY in chop mode - no directional bias"
        logger.info(f"Signal rejected - {reason}")
        return False, reason
    
    # Rule 3: Reject signals opposing strong HTF bias (high confidence)
    if htf_bias.confidence == "high":
        # Check if signal direction opposes HTF direction
        if signal_direction == "long" and htf_bias.direction == "short":
            reason = f"Signal direction (long) opposes strong HTF bias (bearish, score={htf_bias.score:.1f})"
            logger.info(f"Signal rejected - {reason}")
            return False, reason
        elif signal_direction == "short" and htf_bias.direction == "long":
            reason = f"Signal direction (short) opposes strong HTF bias (bullish, score={htf_bias.score:.1f})"
            logger.info(f"Signal rejected - {reason}")
            return False, reason
    
    # Rule 4: Warn on neutral HTF bias but allow signal
    if htf_bias.bias == "neutral":
        reason = f"HTF bias is neutral (score={htf_bias.score:.1f})"
        logger.debug(f"Signal allowed with caution - {reason}")
        return True, ""  # Allow but flag for lower confidence
    
    # Rule 5: Allow signals aligned with HTF
    if signal_direction == htf_bias.direction:
        logger.debug(
            f"Signal validated - direction ({signal_direction}) aligns with HTF "
            f"({htf_bias.direction}, {htf_bias.confidence} confidence)"
        )
        return True, ""
    
    # Default: Allow if no strong rejection criteria
    return True, ""


def adjust_score_with_htf(
    base_score: float,
    htf_bias: HTFBias,
    signal_direction: str,
) -> tuple[float, dict]:
    """Adjust signal score based on HTF bias alignment.

    Args:
        base_score: Base signal score before HTF adjustment
        htf_bias: HTF bias object
        signal_direction: Signal direction ("long", "short")

    Returns:
        Tuple of (adjusted_score, adjustment_details)

    Logic:
        - Strong alignment: Boost score
        - Weak alignment: Minimal adjustment
        - Misalignment: Reduce score or reject

    DoD:
        - RuleEngine rejects signals when HTF invalid
        - RuleEngine boosts signals when HTF strongly aligned
        - End-to-end test passes
    """
    adjusted_score = base_score
    adjustments = {}
    
    # 1. Apply seasonality adjustment (already calculated in HTFBias)
    if htf_bias.seasonality_adjustment != 0.0:
        adjusted_score += htf_bias.seasonality_adjustment
        adjustments["seasonality"] = htf_bias.seasonality_adjustment
        logger.debug(
            f"Applied seasonality adjustment: {htf_bias.seasonality_adjustment:+.2f} "
            f"(period={htf_bias.seasonality_period})"
        )
    
    # 2. Apply FVG alignment score
    if htf_bias.fvg_alignment_score != 0.0:
        adjusted_score += htf_bias.fvg_alignment_score
        adjustments["fvg_alignment"] = htf_bias.fvg_alignment_score
        logger.debug(
            f"Applied FVG alignment: {htf_bias.fvg_alignment_score:+.2f}"
        )
    
    # 3. Boost for strong HTF alignment (high confidence + matching direction)
    # Only boost when both have clear directional alignment (not neutral)
    if (htf_bias.confidence == "high" and 
        signal_direction == htf_bias.direction and
        signal_direction != "neutral" and htf_bias.direction != "neutral"):
        boost = 1.0  # Strong alignment bonus
        adjusted_score += boost
        adjustments["htf_strong_alignment"] = boost
        logger.debug(
            f"Applied strong HTF alignment boost: +{boost:.2f} "
            f"(HTF {htf_bias.confidence} confidence, score={htf_bias.score:.1f})"
        )
    
    # 4. Moderate boost for medium confidence alignment
    # Only boost when both have clear directional alignment (not neutral)
    elif (htf_bias.confidence == "medium" and 
          signal_direction == htf_bias.direction and
          signal_direction != "neutral" and htf_bias.direction != "neutral"):
        boost = 0.5  # Medium alignment bonus
        adjusted_score += boost
        adjustments["htf_medium_alignment"] = boost
        logger.debug(
            f"Applied medium HTF alignment boost: +{boost:.2f} "
            f"(HTF {htf_bias.confidence} confidence, score={htf_bias.score:.1f})"
        )
    
    # 5. Penalty for neutral HTF or low confidence
    if htf_bias.bias == "neutral" or htf_bias.confidence == "low":
        penalty = -0.5
        adjusted_score += penalty
        adjustments["htf_weak_bias"] = penalty
        logger.debug(
            f"Applied weak HTF bias penalty: {penalty:.2f} "
            f"(bias={htf_bias.bias}, confidence={htf_bias.confidence})"
        )
    
    # 6. Bonus for VWAP trend confirmation
    # Only boost when both have clear directional alignment (not neutral)
    if (htf_bias.vwap_trend_confirmed and 
        signal_direction == htf_bias.direction and
        signal_direction != "neutral" and htf_bias.direction != "neutral"):
        bonus = 0.5
        adjusted_score += bonus
        adjustments["vwap_confirmation"] = bonus
        logger.debug(f"Applied VWAP trend confirmation bonus: +{bonus:.2f}")
    
    # 7. Bonus for DXY alignment
    # Only boost when both have clear directional alignment (not neutral)
    if (htf_bias.dxy_alignment and 
        signal_direction == htf_bias.direction and
        signal_direction != "neutral" and htf_bias.direction != "neutral"):
        bonus = 0.5
        adjusted_score += bonus
        adjustments["dxy_alignment"] = bonus
        logger.debug(f"Applied DXY alignment bonus: +{bonus:.2f}")
    
    # 8. Bonus for structure events (BOS indicates continuation)
    # Only boost when both have clear directional alignment (not neutral)
    if (htf_bias.bos_detected and 
        signal_direction == htf_bias.direction and
        signal_direction != "neutral" and htf_bias.direction != "neutral"):
        bonus = 0.3
        adjusted_score += bonus
        adjustments["bos_detected"] = bonus
        logger.debug(f"Applied BOS detection bonus: +{bonus:.2f}")
    
    # 9. Penalty for CHoCH (indicates potential reversal)
    if htf_bias.choch_detected:
        penalty = -0.3
        adjusted_score += penalty
        adjustments["choch_detected"] = penalty
        logger.debug(f"Applied CHoCH detection penalty: {penalty:.2f}")
    
    # Cap final score at 10.0
    adjusted_score = min(adjusted_score, 10.0)
    
    # Log final adjustment
    total_adjustment = adjusted_score - base_score
    logger.info(
        f"HTF score adjustment: {base_score:.2f} → {adjusted_score:.2f} "
        f"(delta: {total_adjustment:+.2f})"
    )
    
    return adjusted_score, adjustments


def create_htf_bias_func_with_sync_layer(
    multi_tf_data: MultiTimeframeData,
    approach: str = "streaming",
    rsi_period: int = 14,
    ema_periods: Optional[list[int]] = None,
    dxy_window: int = 50,
    swing_window: int = 5,
) -> Callable[[pd.Series, dict], HTFBias]:
    """Factory to create HTF bias function with MultiTimeframeData access.
    
    Creates a closure that has access to the synchronized multi-timeframe data
    and computes HTF features either incrementally (streaming) or from
    pre-computed features (vectorized).
    
    Args:
        multi_tf_data: Synchronized multi-timeframe data
        approach: "streaming" (incremental) or "vectorized" (pre-computed)
        rsi_period: RSI calculation period (default: 14)
        ema_periods: List of EMA periods (default: [9, 20, 50])
        dxy_window: DXY correlation window (default: 50)
        swing_window: Structure label swing window (default: 5)
    
    Returns:
        Function with signature (features_1m, context) -> HTFBias
        
    Example:
        >>> from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
        >>> sync_layer = MultiTimeframeSyncLayer("data/gc_dx_ohlcv")
        >>> multi_tf_data = sync_layer.load(start, end)
        >>> htf_bias_func = create_htf_bias_func_with_sync_layer(
        ...     multi_tf_data, approach="streaming"
        ... )
        >>> htf_bias = htf_bias_func(features_1m, context)
    """
    if approach == "streaming":
        # Create streaming feature computer
        htf_computer = StreamingHTFFeatureComputer(
            rsi_period=rsi_period,
            ema_periods=ema_periods,
            dxy_window=dxy_window,
            swing_window=swing_window,
        )
        
        # Track previous sync bar to detect changes
        prev_sync_bar: Optional[SynchronizedBar] = None
        
        # Buffer for 15m candles (for liquidity sweep detection)
        # Need enough history for swing detection
        candle_buffer_15m: list = []
        max_buffer_size = swing_window * 3  # Keep 3x swing window for context
        
        def htf_bias_func(features_1m: pd.Series, context: dict) -> HTFBias:
            """Compute HTF bias using streaming approach."""
            nonlocal prev_sync_bar, candle_buffer_15m
            
            timestamp = features_1m["timestamp"]
            if isinstance(timestamp, pd.Timestamp):
                timestamp_dt = timestamp.to_pydatetime()
            else:
                timestamp_dt = timestamp
            
            # Get synchronized bar for this timestamp
            sync_bar = multi_tf_data.get_bar(timestamp_dt)
            if not sync_bar:
                logger.warning(
                    f"No synchronized bar found for timestamp {timestamp_dt}, "
                    "returning neutral bias"
                )
                return HTFBias(bias="neutral", direction="neutral", score=0.0, confidence="low")
            
            # Update HTF features incrementally
            features_15m, features_1h = htf_computer.update_from_sync_bar(
                sync_bar, prev_sync_bar
            )
            
            # Update prev_sync_bar for next iteration
            prev_sync_bar = sync_bar
            
            # Check if we have valid features
            if features_15m.empty or features_1h.empty:
                logger.debug(
                    f"HTF features not yet available at {timestamp_dt}, "
                    "returning neutral bias"
                )
                return HTFBias(bias="neutral", direction="neutral", score=0.0, confidence="low")
            
            # Build HTF DataFrames from candles for structure detection
            # These are needed for BOS/CHoCH/FVG detection in compute_htf_bias
            df_15m = None
            df_1h = None
            dxy_1h = None
            sweep_events_15m = None
            
            if sync_bar.htf_15m:
                # Update 15m candle buffer
                current_15m_candle = sync_bar.htf_15m[0]
                
                # Only add if it's a new candle (different timestamp from last)
                if not candle_buffer_15m or candle_buffer_15m[-1].timestamp != current_15m_candle.timestamp:
                    candle_buffer_15m.append(current_15m_candle)
                    
                    # Keep buffer size manageable
                    if len(candle_buffer_15m) > max_buffer_size:
                        candle_buffer_15m.pop(0)
                
                # Build DataFrame from buffered candles for structure detection
                if len(candle_buffer_15m) > swing_window * 2:  # Need enough for swing detection
                    df_15m = build_htf_dataframe_from_candles(
                        candle_buffer_15m, "15m"
                    )
                    
                    # Detect liquidity sweeps on 15m
                    try:
                        from rule_engine.htf.structure import detect_swings, detect_liquidity_sweeps
                        
                        swing_highs_15m, swing_lows_15m = detect_swings(df_15m, lookback=swing_window)
                        sweep_events, sweep_success = detect_liquidity_sweeps(
                            df_15m, swing_highs_15m, swing_lows_15m
                        )
                        sweep_events_15m = sweep_events
                    except Exception as e:
                        logger.debug(f"Failed to detect liquidity sweeps in streaming mode: {e}")
                        sweep_events_15m = None
            
            if sync_bar.htf_1h:
                df_1h = build_htf_dataframe_from_candles([sync_bar.htf_1h[0]], "1h")
                dxy_1h = build_htf_dataframe_from_candles([sync_bar.htf_1h[1]], "1h")
            
            # Compute HTF bias
            return compute_htf_bias(
                features_1h=features_1h,
                features_15m=features_15m,
                dxy_1h=dxy_1h,
                df_15m=df_15m,
                df_1h=df_1h,
                sweep_events_15m=sweep_events_15m,
                timestamp=pd.Timestamp(timestamp_dt),
            )
        
        return htf_bias_func
    
    elif approach == "vectorized":
        # Pre-compute all HTF features
        logger.info("Pre-computing HTF features (vectorized approach)...")
        features_15m_df, features_1h_df = _precompute_htf_features(
            multi_tf_data,
            rsi_period=rsi_period,
            ema_periods=ema_periods,
            dxy_window=dxy_window,
            swing_window=swing_window,
        )
        
        # Extract HTF candles for structure detection
        from data_layer.multi_timeframe_helpers import extract_htf_candles_by_timeframe
        
        gc_15m, dxy_15m = extract_htf_candles_by_timeframe(multi_tf_data, "15m")
        gc_1h, dxy_1h = extract_htf_candles_by_timeframe(multi_tf_data, "1h")
        
        df_15m = build_htf_dataframe_from_candles(gc_15m, "15m") if gc_15m else None
        df_1h = build_htf_dataframe_from_candles(gc_1h, "1h") if gc_1h else None
        dxy_1h = build_htf_dataframe_from_candles(dxy_1h, "1h") if dxy_1h else None
        
        # Pre-compute liquidity sweeps on 15m timeframe
        sweep_events_15m_series = None
        if df_15m is not None and len(df_15m) > 0:
            try:
                from rule_engine.htf.structure import detect_swings, detect_liquidity_sweeps
                
                # Detect swings on 15m data
                swing_highs_15m, swing_lows_15m = detect_swings(df_15m, lookback=swing_window)
                
                # Detect liquidity sweeps
                sweep_events, sweep_success = detect_liquidity_sweeps(
                    df_15m, swing_highs_15m, swing_lows_15m
                )
                sweep_events_15m_series = sweep_events
                
                logger.info(
                    f"Detected {sweep_events.notna().sum()} liquidity sweeps on 15m timeframe"
                )
            except Exception as e:
                logger.warning(f"Failed to detect liquidity sweeps: {e}")
                sweep_events_15m_series = None
        
        logger.info(
            f"Pre-computed HTF features: 15m={len(features_15m_df) if features_15m_df is not None else 0} rows, "
            f"1h={len(features_1h_df) if features_1h_df is not None else 0} rows"
        )
        
        def htf_bias_func(features_1m: pd.Series, context: dict) -> HTFBias:
            """Compute HTF bias using vectorized approach."""
            timestamp = features_1m["timestamp"]
            if isinstance(timestamp, pd.Timestamp):
                timestamp_ts = timestamp
            else:
                timestamp_ts = pd.Timestamp(timestamp)
            
            # Get synchronized bar to find HTF bar timestamp
            timestamp_dt = timestamp_ts.to_pydatetime()
            sync_bar = multi_tf_data.get_bar(timestamp_dt)
            if not sync_bar:
                logger.warning(
                    f"No synchronized bar found for timestamp {timestamp_dt}, "
                    "returning neutral bias"
                )
                return HTFBias(bias="neutral", direction="neutral", score=0.0, confidence="low")
            
            # Lookup pre-computed features by HTF bar timestamp
            features_15m = None
            features_1h = None
            
            if sync_bar.htf_15m and features_15m_df is not None:
                htf_15m_ts = pd.Timestamp(sync_bar.htf_15m[0].timestamp)
                if htf_15m_ts in features_15m_df.index:
                    features_15m = features_15m_df.loc[htf_15m_ts]
                else:
                    # Find closest timestamp (forward-fill behavior)
                    valid_timestamps = features_15m_df.index[features_15m_df.index <= htf_15m_ts]
                    if len(valid_timestamps) > 0:
                        closest_ts = valid_timestamps.max()
                        features_15m = features_15m_df.loc[closest_ts]
            
            if sync_bar.htf_1h and features_1h_df is not None:
                htf_1h_ts = pd.Timestamp(sync_bar.htf_1h[0].timestamp)
                if htf_1h_ts in features_1h_df.index:
                    features_1h = features_1h_df.loc[htf_1h_ts]
                else:
                    # Find closest timestamp (forward-fill behavior)
                    valid_timestamps = features_1h_df.index[features_1h_df.index <= htf_1h_ts]
                    if len(valid_timestamps) > 0:
                        closest_ts = valid_timestamps.max()
                        features_1h = features_1h_df.loc[closest_ts]
            
            # Check if we have valid features
            if features_15m is None or features_1h is None:
                logger.debug(
                    f"HTF features not available at {timestamp_dt}, "
                    "returning neutral bias"
                )
                return HTFBias(bias="neutral", direction="neutral", score=0.0, confidence="low")
            
            # Extract liquidity sweep events up to current timestamp
            sweep_events_for_timestamp = None
            if sweep_events_15m_series is not None and sync_bar.htf_15m:
                htf_15m_ts = pd.Timestamp(sync_bar.htf_15m[0].timestamp)
                # Get all sweep events up to and including current HTF timestamp
                if htf_15m_ts in sweep_events_15m_series.index:
                    sweep_events_for_timestamp = sweep_events_15m_series.loc[:htf_15m_ts]
                else:
                    # Find closest timestamp (forward-fill behavior)
                    valid_timestamps = sweep_events_15m_series.index[
                        sweep_events_15m_series.index <= htf_15m_ts
                    ]
                    if len(valid_timestamps) > 0:
                        sweep_events_for_timestamp = sweep_events_15m_series.loc[:valid_timestamps.max()]
            
            # Compute HTF bias
            return compute_htf_bias(
                features_1h=features_1h,
                features_15m=features_15m,
                dxy_1h=dxy_1h,
                df_15m=df_15m,
                df_1h=df_1h,
                sweep_events_15m=sweep_events_for_timestamp,
                timestamp=timestamp_ts,
            )
        
        return htf_bias_func
    
    else:
        raise ValueError(
            f"Invalid approach: {approach}. Must be 'streaming' or 'vectorized'"
        )

