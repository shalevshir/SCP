"""Signal engine wrapper for Bot Core service."""

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


def signal_to_message(signal: Signal) -> SignalMessage:
    """Convert Signal to SignalMessage.
    
    Args:
        signal: Signal object from score_signal
        
    Returns:
        SignalMessage for publishing
    """
    return SignalMessage(
        timestamp=signal.timestamp,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        direction=signal.direction,
        setup_type=signal.setup_type,
        htf_bias=signal.htf_bias,
        score=signal.score,
        confidence=signal.confidence,
        factors=signal.factors,
        rationale=signal.rationale,
        validation_flags=signal.validation_flags,
        enforcer_tier=signal.enforcer_tier,
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
        
        # Convert to message
        signal_msg = signal_to_message(signal)
        
        logger.info(
            f"A+ signal generated: {signal.direction} {signal.setup_type} "
            f"(score: {signal.score:.1f}, timestamp: {signal.timestamp})"
        )
        
        return signal_msg

