"""HTF Bias Processor wrapper for service use.

This module wraps the StreamingHTFBiasCalculator to convert between
message types (CandleMessage <-> Candle) and handle service-level concerns.
"""

from scp_shared.rule_engine.htf.streaming import StreamingHTFBiasCalculator
from scp_shared.messaging.schemas import CandleMessage, HTFBiasMessage
from scp_shared.common.types import Candle


class HTFBiasProcessor:
    """Wrapper around StreamingHTFBiasCalculator for service use.
    
    Handles conversion between:
    - Input: CandleMessage (from Redis streams)
    - Internal: Candle (for StreamingHTFBiasCalculator)
    - Output: HTFBiasMessage (for Redis streams)
    """
    
    def __init__(self):
        """Initialize HTF bias processor."""
        self.calculator = StreamingHTFBiasCalculator()
    
    def _convert_confidence(self, htf_confidence: str, score: float) -> str:
        """Convert HTFBias confidence to signal confidence format.
        
        HTFBias uses: "low", "medium", "high"
        HTFBiasMessage uses: "A+", "A", "B", "C"
        
        Args:
            htf_confidence: HTFBias confidence ("low", "medium", "high")
            score: HTFBias score (0-10)
            
        Returns:
            Signal confidence ("A+", "A", "B", "C")
        """
        # Map based on both confidence and score
        if htf_confidence == "high" and score >= 8:
            return "A+"
        elif htf_confidence == "high" or (htf_confidence == "medium" and score >= 7):
            return "A"
        elif htf_confidence == "medium":
            return "B"
        else:  # low
            return "C"
    
    def process(
        self,
        gc_message: CandleMessage,
        dxy_message: CandleMessage,
    ) -> HTFBiasMessage | None:
        """Process candle pair and return HTF bias message if boundary reached.
        
        Args:
            gc_message: Gold candle message (1m timeframe)
            dxy_message: DXY candle message (1m timeframe)
            
        Returns:
            HTFBiasMessage if HTF boundary reached and bias computed, None otherwise
        """
        # Convert CandleMessage to internal Candle type
        gc_candle = Candle(
            timestamp=gc_message.timestamp,
            open=gc_message.open,
            high=gc_message.high,
            low=gc_message.low,
            close=gc_message.close,
            volume=gc_message.volume,
            symbol=gc_message.symbol,
            timeframe=gc_message.timeframe,
            source="STREAM",
        )
        dxy_candle = Candle(
            timestamp=dxy_message.timestamp,
            open=dxy_message.open,
            high=dxy_message.high,
            low=dxy_message.low,
            close=dxy_message.close,
            volume=dxy_message.volume,
            symbol=dxy_message.symbol,
            timeframe=dxy_message.timeframe,
            source="STREAM",
        )
        
        # Process through StreamingHTFBiasCalculator
        htf_bias = self.calculator.update(gc_candle, dxy_candle)
        
        # Return None if no bias computed yet (not at boundary or insufficient data)
        if htf_bias is None:
            return None
        
        # Convert HTFBias to HTFBiasMessage
        return HTFBiasMessage(
            timestamp=gc_message.timestamp,
            bias=htf_bias.bias,  # "bullish" | "bearish" | "neutral"
            score=htf_bias.score,
            confidence=self._convert_confidence(htf_bias.confidence, htf_bias.score),
            structure_15m=htf_bias.structure_15m,
            structure_1h=htf_bias.structure_1h,
            dxy_aligned=htf_bias.dxy_alignment,  # Use dxy_alignment from HTFBias
            chop_detected=htf_bias.chop_detected,
        )

