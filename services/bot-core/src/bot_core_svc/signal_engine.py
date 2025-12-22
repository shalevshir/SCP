"""Signal engine wrapper for Bot Core service."""

import uuid
from typing import Any

import pandas as pd
from scp_shared.common.logger import get_logger
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage, SignalMessage
from scp_shared.rule_engine import Signal, score_signal
from scp_shared.rule_engine.htf.types import HTFBias

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
    
    return HTFBias(
        bias=msg.bias,  # type: ignore
        direction=direction_map[msg.bias],  # type: ignore
        score=msg.score,
        confidence=confidence_map.get(msg.confidence, "low"),  # type: ignore
        structure_15m=msg.structure_15m,
        structure_1h=msg.structure_1h,
        dxy_alignment=msg.dxy_aligned,
        chop_detected=msg.chop_detected,
        # Other fields use defaults from HTFBias dataclass
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
        "close": msg.close,
        "vwap": msg.vwap,
        "rsi": msg.rsi,
        "ema_9": msg.ema_9,
        "ema_20": msg.ema_20,
        "ema_50": msg.ema_50,
        "dxy_corr": msg.dxy_correlation,  # Map dxy_correlation to dxy_corr for scoring
        "structure_label": msg.structure_label,
        "vwap_deviation": msg.vwap_deviation,
    })


def signal_to_message(signal: Signal, features: FeaturesMessage) -> SignalMessage:
    """Convert Signal to SignalMessage.
    
    Args:
        signal: Signal object from score_signal
        features: Features message containing price data for entry/SL/TP calculation
        
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
    
    if setup_type == "VWAP_RECLAIM" and features.vwap is not None:
        # VWAP-zone SL: VWAP ± buffer ticks
        buffer_amount = VWAP_SL_BUFFER_TICKS * TICK_SIZE_GC
        if direction == "long":
            sl_price = features.vwap - buffer_amount
        else:  # short
            sl_price = features.vwap + buffer_amount
        
        # Ensure minimum 20-tick distance from entry
        risk_distance = abs(entry_price - sl_price)
        risk_ticks = risk_distance / TICK_SIZE_GC
        if risk_ticks < MIN_SL_TICKS_VWAP_RECLAIM:
            if direction == "long":
                sl_price = entry_price - (MIN_SL_TICKS_VWAP_RECLAIM * TICK_SIZE_GC)
            else:
                sl_price = entry_price + (MIN_SL_TICKS_VWAP_RECLAIM * TICK_SIZE_GC)
    
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
    
    # Get alignment flags from diagnostics or signal
    htf_aligned = signal.diagnostics.get("htf_aligned", False)
    dxy_aligned = signal.diagnostics.get("dxy_aligned", False)
    
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
    
    # Calculate take profit: entry ± (risk_distance × R_multiple)
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
    
    def generate(
        self,
        features: FeaturesMessage,
        htf_bias: HTFBiasMessage,
        context: dict,
    ) -> SignalMessage | None:
        """Generate signal from features and bias.
        
        Args:
            features: Features message
            htf_bias: HTF bias message
            context: Context dict with session_ok, enforcer_tier
            
        Returns:
            SignalMessage if A+ signal generated, None otherwise
        """
        # Convert messages to expected types
        features_series = features_message_to_series(features)
        htf_bias_obj = htf_bias_message_to_htf_bias(htf_bias)
        
        # Generate signal
        signal = score_signal(features_series, htf_bias_obj, context)
        
        # Filter for A+ signals only
        if signal.confidence != "A+":
            logger.debug(
                f"Signal rejected (confidence={signal.confidence}): "
                f"{signal.direction} {signal.setup_type} score={signal.score:.1f}"
            )
            return None
        
        # Filter out neutral signals (SignalMessage only accepts "long" or "short")
        # This can occur when close == vwap exactly (very rare edge case)
        if signal.direction == "neutral":
            logger.warning(
                f"Signal rejected (neutral direction): "
                f"{signal.setup_type} score={signal.score:.1f} "
                f"(close={features.close}, vwap={features.vwap})"
            )
            return None
        
        # Convert to message
        signal_msg = signal_to_message(signal, features)
        
        logger.info(
            f"A+ signal generated: {signal.direction} {signal.setup_type} "
            f"(score: {signal.score:.1f}, timestamp: {signal.timestamp})"
        )
        
        return signal_msg

