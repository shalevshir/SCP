"""Unit tests for signal engine."""

from datetime import datetime, timezone

import pytest
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage

from bot_core_svc.signal_engine import (
    SignalEngine,
    features_message_to_series,
    htf_bias_message_to_htf_bias,
)


class TestSignalEngine:
    """Test signal engine wrapper."""
    
    def test_htf_bias_message_conversion(self) -> None:
        """HTF bias message converts to HTFBias object."""
        msg = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            structure_15m="HH",
            structure_1h="HL",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        htf_bias = htf_bias_message_to_htf_bias(msg)
        
        assert htf_bias.bias == "bullish"
        assert htf_bias.direction == "long"
        assert htf_bias.score == 8.5
        assert htf_bias.confidence == "high"
        assert htf_bias.structure_15m == "HH"
        assert htf_bias.structure_1h == "HL"
        assert htf_bias.dxy_alignment is True
        assert htf_bias.chop_detected is False
    
    def test_htf_bias_message_neutral_conversion(self) -> None:
        """Neutral bias converts to neutral direction."""
        msg = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="neutral",
            score=5.0,
            confidence="C",
            dxy_aligned=False,
            chop_detected=True,
        )
        
        htf_bias = htf_bias_message_to_htf_bias(msg)
        
        assert htf_bias.bias == "neutral"
        assert htf_bias.direction == "neutral"
        assert htf_bias.confidence == "low"
    
    def test_features_message_to_series(self) -> None:
        """Features message converts to pandas Series."""
        msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            rsi=55.0,
            ema_9=2648.0,
            ema_20=2645.0,
            ema_50=2640.0,
            dxy_correlation=-0.75,
            structure_label="HH",
            vwap_deviation=0.5,
        )
        
        series = features_message_to_series(msg)
        
        assert series["timestamp"] == msg.timestamp
        assert series["symbol"] == "GC"
        assert series["timeframe"] == "1m"
        assert series["close"] == 2650.0
        assert series["vwap"] == 2645.0
        assert series["rsi"] == 55.0
        assert series["ema_9"] == 2648.0
        assert series["ema_20"] == 2645.0
        assert series["ema_50"] == 2640.0
        assert series["dxy_correlation"] == -0.75
        assert series["structure_label"] == "HH"
        assert series["vwap_deviation"] == 0.5

