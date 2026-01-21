"""Signal engine wrapper for Bot Core service."""

import uuid
from typing import Any

import pandas as pd
from scp_shared.common.logger import get_logger
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage, SignalMessage
from scp_shared.rule_engine import Signal, score_signal
from scp_shared.rule_engine.htf.types import HTFBias
from bot_core_svc import metrics

logger = get_logger(__name__)


def htf_bias_message_to_htf_bias(msg: HTFBiasMessage) -> HTFBias:
    """Convert HTFBiasMessage to HTFBias object.
    
    Args:
        msg: HTF bias message from stream
        
    Returns:
        HTFBias object for score_signal
    """
    # Map confidence levels
    confidence_map = {
        "A+": "high",
        "A": "high",
        "B": "medium",
        "C": "low",
    }
    
    # Determine direction from bias
    direction_map = {
        "bullish": "long",
        "bearish": "short",
        "neutral": "neutral",
    }
    
    # DEBUG: Log received HTFBiasMessage fields
    logger.info(
        f"HTFBiasMessage received: seasonality_adj={msg.seasonality_adjustment}, "
        f"seasonality_period={msg.seasonality_period}, "
        f"vwap_confirmed={msg.vwap_trend_confirmed}"
    )
    
    return HTFBias(
        bias=msg.bias,  # type: ignore
        direction=direction_map[msg.bias],  # type: ignore
        score=msg.score,
        confidence=confidence_map.get(msg.confidence, "low"),  # type: ignore
        structure_15m=msg.structure_15m,
        structure_1h=msg.structure_1h,
        dxy_alignment=msg.dxy_aligned,
        chop_detected=msg.chop_detected,
        # Additional fields for scoring bonuses
        seasonality_adjustment=msg.seasonality_adjustment,
        seasonality_period=msg.seasonality_period,  # type: ignore (string Literal)
        vwap_trend_confirmed=msg.vwap_trend_confirmed,
        # Structure quality fields for calculate_structure_alignment scoring
        bos_detected=msg.bos_detected,
        bars_since_bos=msg.bars_since_bos,
        structure_clarity=msg.structure_clarity,
        liquidity_sweep_detected=msg.liquidity_sweep_detected,
        # Conflict/chop fields for htf_valid validation
        conflict_detected=msg.conflict_detected,
        conflict_reason=msg.conflict_reason,
        dxy_chop_detected=msg.dxy_chop_detected,
        # DXY correlation and structure fields for DXY_CONTINUATION detection
        dxy_corr_1m=msg.dxy_corr_1m,
        dxy_corr_5m=msg.dxy_corr_5m,
        dxy_corr_15m=msg.dxy_corr_15m,
        dxy_corr_1h=msg.dxy_corr_1h,
        dxy_structure=msg.dxy_structure,
        dxy_chop_5m=msg.dxy_chop_5m,
    )


def features_message_to_series(msg: FeaturesMessage) -> pd.Series:
    """Convert FeaturesMessage to pandas Series.
    
    Args:
        msg: Features message from stream
        
    Returns:
        Pandas Series with features
    """
    return pd.Series({
        "timestamp": msg.timestamp,
        "symbol": msg.symbol,
        "timeframe": msg.timeframe,
        # OHLC data (needed for VWAP_FADE rejection candle checks)
        "open": msg.open,
        "high": msg.high,
        "low": msg.low,
        "close": msg.close,
        "vwap": msg.vwap,
        "rsi": msg.rsi,
        "ema_9": msg.ema_9,
        "ema_20": msg.ema_20,
        "ema_50": msg.ema_50,
        "dxy_corr": msg.dxy_correlation,  # Map dxy_correlation to dxy_corr for scoring
        "structure_label": msg.structure_label,
        "last_structure_label": msg.structure_label,  # Alias for VWAP_FADE detector
        "vwap_deviation": msg.vwap_deviation,
        # BOS/CHoCH fields for VWAP_RECLAIM validation
        "bos_direction": msg.bos_direction,
        "bos_recent": msg.bos_recent,
        "bos_age": msg.bos_age,
        "choch_detected": msg.choch_detected,
        "choch_direction": msg.choch_direction,
        "structure_clarity": msg.structure_clarity,
        "trend_confidence": msg.trend_confidence,
        "liquidity_sweep": msg.liquidity_sweep,
        "sweep_age": msg.sweep_age,
        # Expansion fields for late_reclaim_penalty calculation
        "expansion_detected": msg.expansion_detected,
        "expansion_reasons": msg.expansion_reasons,
    })


def validate_tp_target(
    direction: str,
    entry_price: float,
    sl_price: float,
    features: FeaturesMessage,
    min_rr: float = 3.0,
) -> tuple[float | None, str | None]:
    """Validate structural TP target exists at minimum R:R.
    
    Returns:
        (tp_price, None) if valid target found
        (None, rejection_reason) if no valid target
    
    Args:
        direction: Trade direction ("long" or "short")
        entry_price: Entry price
        sl_price: Stop loss price
        features: Features message containing target data
        min_rr: Minimum R:R ratio (default: 3.0)
    
    Returns:
        Tuple of (tp_price, rejection_reason)
    """
    # ========================================================================
    # SOP CRITICAL: Validate SL placement BEFORE any R:R calculations
    # ========================================================================
    # Long trades: SL must be BELOW entry (sl_price < entry_price)
    # This also catches zero-risk trades (sl_price == entry_price)
    if direction == "long" and sl_price >= entry_price:
        return None, "Invalid SL: long trade SL must be below entry"
    
    # Short trades: SL must be ABOVE entry (sl_price > entry_price)
    # This also catches zero-risk trades (sl_price == entry_price)
    if direction == "short" and sl_price <= entry_price:
        return None, "Invalid SL: short trade SL must be above entry"
    
    # ========================================================================
    # Compute risk distance (now safe after validation)
    # ========================================================================
    risk_distance = abs(entry_price - sl_price)
    min_tp_distance = risk_distance * min_rr
    
    if direction == "long":
        min_tp_price = entry_price + min_tp_distance
        
        # Check structural targets in priority order
        candidates = [
            ("nearest_liquidity", features.nearest_liquidity_long),
            ("prior_session_high", features.prior_session_high),
        ]
        for target_name, target in candidates:
            if target is not None and target >= min_tp_price:
                return target, None
        
        # No valid target found
        return None, f"No structural target at ≥{min_rr}R (min_tp={min_tp_price:.2f})"
    
    else:  # short
        max_tp_price = entry_price - min_tp_distance
        
        candidates = [
            ("nearest_liquidity", features.nearest_liquidity_short),
            ("prior_session_low", features.prior_session_low),
        ]
        for target_name, target in candidates:
            if target is not None and target <= max_tp_price:
                return target, None
        
        return None, f"No structural target at ≥{min_rr}R (max_tp={max_tp_price:.2f})"


def calculate_sl_price_vwap_reclaim(
    direction: str,
    entry_price: float,
    features: FeaturesMessage,
    sl_buffer_ticks: int = 30,
    min_sl_ticks: int = 20,
) -> float:
    """Calculate SL using priority system per SOP for VWAP_RECLAIM.
    
    Priority A: Structure-based (HL/LH anchor)
    Priority B: Reclaim candle extreme
    Priority C: VWAP zone (last resort)
    
    Args:
        direction: Trade direction ("long" or "short")
        entry_price: Entry price
        features: Features message containing structure and VWAP data
        sl_buffer_ticks: Buffer in ticks (default: 30)
        min_sl_ticks: Minimum SL distance in ticks (default: 20)
    
    Returns:
        SL price
    """
    TICK_SIZE = 0.1
    buffer = sl_buffer_ticks * TICK_SIZE
    min_distance = min_sl_ticks * TICK_SIZE
    
    sl_price = None
    
    if direction == "long":
        # Priority A: HL swing low
        if features.swing_hl_low is not None:
            sl_price = features.swing_hl_low - buffer
        # Priority B: Reclaim candle low
        elif features.reclaim_candle_low is not None:
            sl_price = features.reclaim_candle_low - buffer
        # Priority C: VWAP zone bottom
        elif features.vwap is not None:
            sl_price = features.vwap - buffer
        
        # Ensure minimum distance from entry
        if sl_price is not None:
            if entry_price - sl_price < min_distance:
                sl_price = entry_price - min_distance
    
    else:  # short
        # Priority A: LH swing high
        if features.swing_lh_high is not None:
            sl_price = features.swing_lh_high + buffer
        # Priority B: Reclaim candle high
        elif features.reclaim_candle_high is not None:
            sl_price = features.reclaim_candle_high + buffer
        # Priority C: VWAP zone top
        elif features.vwap is not None:
            sl_price = features.vwap + buffer
        
        # Ensure minimum distance from entry
        if sl_price is not None:
            if sl_price - entry_price < min_distance:
                sl_price = entry_price + min_distance
    
    # Fallback if no valid SL method available
    if sl_price is None:
        if direction == "long":
            sl_price = entry_price - min_distance
        else:
            sl_price = entry_price + min_distance
    
    return sl_price


def signal_to_message(signal: Signal, features: FeaturesMessage, htf_bias: HTFBiasMessage) -> SignalMessage:
    """Convert Signal to SignalMessage.
    
    Args:
        signal: Signal object from score_signal
        features: Features message containing price data for entry/SL/TP calculation
        htf_bias: HTF bias message containing alignment data
        
    Returns:
        SignalMessage for publishing
        
    Note:
        SL/TP are calculated using SOP rules. For VWAP_RECLAIM, uses VWAP-zone SL.
        Execution service will refine these based on actual candle structure.
    """
    # Generate unique signal ID
    signal_id = str(uuid.uuid4())
    
    # Use close price as suggested entry price
    # Execution service will use next bar open for actual entry
    entry_price = features.close
    
    # Constants from backtester/trade.py
    TICK_SIZE_GC = 0.1  # Gold futures tick size
    VWAP_SL_BUFFER_TICKS = 30
    MIN_SL_TICKS_VWAP_RECLAIM = 20
    MIN_SL_TICKS_VWAP_FADE = 15
    MIN_SL_TICKS_DXY_CONTINUATION = 25
    
    # Calculate stop loss based on setup type and SOP rules
    setup_type = signal.setup_type
    direction = signal.direction
    
    if setup_type == "VWAP_RECLAIM":
        # Priority-based SL: Structure (HL/LH) -> Reclaim candle -> VWAP zone
        sl_price = calculate_sl_price_vwap_reclaim(
            direction=direction,
            entry_price=entry_price,
            features=features,
            sl_buffer_ticks=VWAP_SL_BUFFER_TICKS,
            min_sl_ticks=MIN_SL_TICKS_VWAP_RECLAIM,
        )
    
    elif setup_type == "VWAP_FADE":
        # Fade: minimum 15-tick buffer
        if direction == "long":
            sl_price = entry_price - (MIN_SL_TICKS_VWAP_FADE * TICK_SIZE_GC)
        else:  # short
            sl_price = entry_price + (MIN_SL_TICKS_VWAP_FADE * TICK_SIZE_GC)
    
    elif setup_type == "DXY_CONTINUATION":
        # Continuation: minimum 25-tick buffer
        if direction == "long":
            sl_price = entry_price - (MIN_SL_TICKS_DXY_CONTINUATION * TICK_SIZE_GC)
        else:  # short
            sl_price = entry_price + (MIN_SL_TICKS_DXY_CONTINUATION * TICK_SIZE_GC)
    
    else:
        # Default fallback: 20-tick buffer
        if direction == "long":
            sl_price = entry_price - (MIN_SL_TICKS_VWAP_RECLAIM * TICK_SIZE_GC)
        else:  # short
            sl_price = entry_price + (MIN_SL_TICKS_VWAP_RECLAIM * TICK_SIZE_GC)
    
    # Calculate risk distance
    if direction == "long":
        risk_distance = entry_price - sl_price
    else:  # short
        risk_distance = sl_price - entry_price
    
    # Determine R-multiple based on setup type and seasonality
    # Get month from signal diagnostics or use current month as fallback
    month = signal.diagnostics.get("month")
    if month is None:
        month = signal.timestamp.month
    
    # Get alignment flags from htf_bias message
    # HTF aligned: signal direction matches HTF bias direction
    # Map bias to direction: bullish -> long, bearish -> short
    bias_direction_map = {"bullish": "long", "bearish": "short", "neutral": "neutral"}
    htf_aligned = signal.direction == bias_direction_map.get(htf_bias.bias, "neutral")
    # DXY aligned: direct field from HTF bias message
    dxy_aligned = htf_bias.dxy_aligned
    
    # Determine R-multiple per SOP (from backtester/trade.py:671-688)
    if setup_type == "VWAP_FADE":
        # Fade: default 2R, upgrade to 3R with alignment
        if month in [11, 12] and htf_aligned and dxy_aligned:
            r_multiple = 3.0
        else:
            r_multiple = 2.0
    else:
        # Continuation: default 3R, except September (2R)
        if month == 9:
            r_multiple = 2.0
        else:
            r_multiple = 3.0
    
    # TP Structural Target Validation (SOP Section 4.3)
    # For VWAP_RECLAIM, validate structural target exists at minimum R:R
    if setup_type == "VWAP_RECLAIM":
        tp_price, rejection = validate_tp_target(
            direction=direction,
            entry_price=entry_price,
            sl_price=sl_price,
            features=features,
            min_rr=r_multiple,
        )
        if rejection:
            logger.info(f"VWAP_RECLAIM signal rejected: {rejection}")
            # Return None to indicate signal rejection
            # The caller (SignalEngine.generate) should handle this
            raise ValueError(f"Signal rejected: {rejection}")
    else:
        # For non-VWAP_RECLAIM setups, use simple R-multiple calculation
        # (TP validation not required for FADE/DXY_CONTINUATION per SOP)
        if direction == "long":
            tp_price = entry_price + (risk_distance * r_multiple)
        else:  # short
            tp_price = entry_price - (risk_distance * r_multiple)
    
    # Build factors dict from signal data
    # Include relevant signal metadata in factors for Execution service
    factors: dict[str, Any] = {
        **signal.factors,  # Include scoring factors
        "htf_bias": signal.htf_bias,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "rationale": signal.rationale,
        "validation_flags": signal.validation_flags,
        "enforcer_tier": signal.enforcer_tier,
    }
    
    return SignalMessage(
        id=signal_id,
        timestamp=signal.timestamp,
        direction=signal.direction,
        setup_type=signal.setup_type,
        score=signal.score,
        confidence=signal.confidence,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
        factors=factors,
    )


class SignalEngine:
    """Signal generation engine.
    
    Wraps score_signal function, converting between message types
    and filtering for A+ signals only.
    
    Example:
        >>> engine = SignalEngine()
        >>> signal_msg = engine.generate(features_msg, bias_msg, context)
        >>> if signal_msg is not None:
        ...     print(f"A+ signal generated: {signal_msg.direction}")
    """
    
    def __init__(self, service_mode: str = "dev", service_name: str = "bot-core") -> None:
        """Initialize signal engine.
        
        Args:
            service_mode: Service mode for metrics (dev/test/replay/paper/live)
            service_name: Service name for metrics (default: bot-core)
        """
        self._service_mode = service_mode
        self._service_name = service_name
    
    def generate(
        self,
        features: FeaturesMessage,
        htf_bias: HTFBiasMessage,
        context: dict,
    ) -> tuple[SignalMessage | None, str | None]:
        """Generate signal from features and bias.
        
        Args:
            features: Features message
            htf_bias: HTF bias message
            context: Context dict with session_ok, enforcer_tier
            
        Returns:
            Tuple of (SignalMessage, rejection_reason):
                - SignalMessage if A+ signal generated, None otherwise
                - rejection_reason if signal rejected, None if signal generated
        """
        # Convert messages to expected types
        features_series = features_message_to_series(features)
        htf_bias_obj = htf_bias_message_to_htf_bias(htf_bias)
        
        # Generate signal
        signal = score_signal(features_series, htf_bias_obj, context)
        
        # Record signal score metrics (for all signals, not just A+)
        metrics.signal_score.labels(
            mode=self._service_mode, service=self._service_name
        ).set(signal.score)
        metrics.last_signal_score.labels(
            mode=self._service_mode, service=self._service_name
        ).set(signal.score)
        
        # HTF validity check (must reject if conflict or DXY chop detected)
        # This matches the backtester's validate_signal_with_sop behavior
        htf_valid = not htf_bias_obj.conflict_detected and not htf_bias_obj.dxy_chop_detected
        if not htf_valid:
            rejection_reasons = []
            if htf_bias_obj.conflict_detected:
                rejection_reasons.append(f"HTF conflict: {htf_bias_obj.conflict_reason}")
            if htf_bias_obj.dxy_chop_detected:
                rejection_reasons.append("DXY in chop mode")
            logger.debug(
                f"Signal rejected (htf_valid=False): {signal.direction} {signal.setup_type} "
                f"score={signal.score:.1f} - {', '.join(rejection_reasons)}"
            )
            return None, "htf_validity"
        
        # Filter for A+ signals only
        if signal.confidence != "A+":
            logger.debug(
                f"Signal rejected (confidence={signal.confidence}): "
                f"{signal.direction} {signal.setup_type} score={signal.score:.1f}"
            )
            return None, "confidence_filter"
        
        # Filter out neutral signals (SignalMessage only accepts "long" or "short")
        # This can occur when close == vwap exactly (very rare edge case)
        if signal.direction == "neutral":
            logger.warning(
                f"Signal rejected (neutral direction): "
                f"{signal.setup_type} score={signal.score:.1f} "
                f"(close={features.close}, vwap={features.vwap})"
            )
            return None, "neutral_direction"
        
        # Convert to message (may raise ValueError if TP validation fails)
        try:
            signal_msg = signal_to_message(signal, features, htf_bias)
        except ValueError as e:
            # TP validation failed - signal rejected
            logger.info(
                f"Signal rejected (TP validation): {signal.direction} {signal.setup_type} "
                f"score={signal.score:.1f} - {str(e)}"
            )
            return None, "tp_validation"
        
        logger.info(
            f"A+ signal generated: {signal.direction} {signal.setup_type} "
            f"(score: {signal.score:.1f}, timestamp: {signal.timestamp})"
        )
        
        return signal_msg, None

