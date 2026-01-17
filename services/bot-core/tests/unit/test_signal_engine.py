"""Unit tests for signal engine."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage, SignalMessage
from scp_shared.rule_engine.signal import Signal

from bot_core_svc.signal_engine import (
    SignalEngine,
    features_message_to_series,
    htf_bias_message_to_htf_bias,
    signal_to_message,
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
        assert series["dxy_corr"] == -0.75  # Mapped from dxy_correlation to dxy_corr
        assert series["structure_label"] == "HH"
        assert series["vwap_deviation"] == 0.5
    
    @patch("bot_core_svc.signal_engine.score_signal")
    def test_neutral_direction_signal_filtered(self, mock_score_signal: Mock) -> None:
        """Neutral direction signals are filtered out even if confidence is A+.
        
        This test verifies the fix for the edge case where score_signal returns
        a signal with direction="neutral" (when close == vwap exactly) and
        confidence="A+". Such signals should be rejected because SignalMessage
        only accepts "long" or "short" directions.
        """
        # Create a signal with neutral direction but A+ confidence
        # This can occur when close == vwap exactly (very rare edge case)
        neutral_signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="neutral",  # This would cause ValidationError in SignalMessage
            setup_type="VWAP_RECLAIM",
            htf_bias="neutral",
            score=8.5,  # High enough for A+ confidence
            confidence="A+",
            factors={"structure_alignment": 2.0, "vwap_relation": 2.0},
            rationale="Test neutral signal",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
        
        mock_score_signal.return_value = neutral_signal
        
        engine = SignalEngine()
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,  # Equal to vwap to trigger neutral
            vwap=2650.0,
            rsi=55.0,
            ema_9=2648.0,
            ema_20=2645.0,
            ema_50=2640.0,
            dxy_correlation=-0.75,
            structure_label="HH",
            vwap_deviation=0.0,
        )
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="neutral",
            score=5.0,
            confidence="C",
            dxy_aligned=False,
            chop_detected=True,
        )
        context = {"session_ok": True, "enforcer_tier": "Conservative"}
        
        # Should return (None, rejection_reason) instead of raising ValidationError
        result, rejection_reason = engine.generate(features, htf_bias, context)
        
        assert result is None
        assert rejection_reason == "neutral_direction"
        mock_score_signal.assert_called_once()


class TestSignalToMessage:
    """Test signal_to_message conversion function."""
    
    def test_signal_to_message_long_vwap_reclaim(self) -> None:
        """Convert long VWAP_RECLAIM signal to message."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"structure_alignment": 2.0, "vwap_relation": 2.0},
            rationale="Strong bullish confluence",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"htf_aligned": True, "dxy_aligned": True, "month": 11},
        )
        features = FeaturesMessage(
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
        
        msg = signal_to_message(signal, features)
        
        assert isinstance(msg, SignalMessage)
        assert msg.direction == "long"
        assert msg.setup_type == "VWAP_RECLAIM"
        assert msg.score == 8.5
        assert msg.confidence == "A+"
        assert msg.entry_price == 2650.0  # Close price
        # SL should be VWAP - buffer (30 ticks = 3.0 for GC)
        assert msg.sl_price == 2645.0 - 3.0  # VWAP - 30 ticks
        # TP should be entry + 3R (htf_aligned and dxy_aligned in Nov)
        expected_risk = 2650.0 - msg.sl_price
        assert msg.tp_price == pytest.approx(2650.0 + expected_risk * 3.0, rel=0.01)
        assert msg.id  # Should have a UUID
    
    def test_signal_to_message_short_vwap_reclaim(self) -> None:
        """Convert short VWAP_RECLAIM signal to message."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_RECLAIM",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={"structure_alignment": 2.0, "vwap_relation": 2.0},
            rationale="Strong bearish confluence",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"month": 3},
        )
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2640.0,
            vwap=2645.0,
            rsi=45.0,
            ema_9=2642.0,
            ema_20=2645.0,
            ema_50=2650.0,
            dxy_correlation=-0.75,
            structure_label="LL",
            vwap_deviation=-0.5,
        )
        
        msg = signal_to_message(signal, features)
        
        assert msg.direction == "short"
        assert msg.setup_type == "VWAP_RECLAIM"
        assert msg.entry_price == 2640.0
        # SL should be VWAP + buffer (30 ticks = 3.0)
        assert msg.sl_price == 2645.0 + 3.0  # VWAP + 30 ticks
        # TP should be entry - 3R
        expected_risk = msg.sl_price - 2640.0
        assert msg.tp_price == pytest.approx(2640.0 - expected_risk * 3.0, rel=0.01)
    
    def test_signal_to_message_vwap_fade(self) -> None:
        """Convert VWAP_FADE signal to message."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"rejection_candle": 2.0, "volume_spike": 1.5},
            rationale="Strong fade setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"htf_aligned": True, "dxy_aligned": True, "month": 11},
        )
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            rsi=28.0,  # Oversold
            ema_9=2648.0,
            ema_20=2645.0,
            ema_50=2640.0,
            dxy_correlation=-0.75,
            structure_label="HH",
            vwap_deviation=0.5,
        )
        
        msg = signal_to_message(signal, features)
        
        assert msg.direction == "long"
        assert msg.setup_type == "VWAP_FADE"
        # VWAP_FADE uses 15-tick minimum SL
        assert msg.sl_price == 2650.0 - 1.5  # entry - 15 ticks
        # Nov with alignment = 3R
        expected_risk = 2650.0 - msg.sl_price
        assert msg.tp_price == pytest.approx(2650.0 + expected_risk * 3.0, rel=0.01)
    
    def test_signal_to_message_dxy_continuation(self) -> None:
        """Convert DXY_CONTINUATION signal to message."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"dxy_corr": 1.5},
            rationale="DXY continuation setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"month": 3},
        )
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            rsi=55.0,
            ema_9=2648.0,
            ema_20=2645.0,
            ema_50=2640.0,
            dxy_correlation=-0.85,
            structure_label="HH",
            vwap_deviation=0.5,
        )
        
        msg = signal_to_message(signal, features)
        
        assert msg.direction == "long"
        assert msg.setup_type == "DXY_CONTINUATION"
        # DXY_CONTINUATION uses 25-tick minimum SL
        assert msg.sl_price == 2650.0 - 2.5  # entry - 25 ticks
        # Not September, so 3R
        expected_risk = 2650.0 - msg.sl_price
        assert msg.tp_price == pytest.approx(2650.0 + expected_risk * 3.0, rel=0.01)
    
    def test_signal_to_message_september_2r(self) -> None:
        """September uses 2R target."""
        signal = Signal(
            timestamp=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="September setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"month": 9},  # September
        )
        features = FeaturesMessage(
            timestamp=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
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
        
        msg = signal_to_message(signal, features)
        
        # September uses 2R
        expected_risk = 2650.0 - msg.sl_price
        assert msg.tp_price == pytest.approx(2650.0 + expected_risk * 2.0, rel=0.01)
    
    def test_signal_to_message_uses_timestamp_month_fallback(self) -> None:
        """Uses signal timestamp month when diagnostics month is missing."""
        signal = Signal(
            timestamp=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="No month in diagnostics",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={},  # No month
        )
        features = FeaturesMessage(
            timestamp=datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc),
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
        
        msg = signal_to_message(signal, features)
        
        # Should use timestamp month (September = 2R)
        expected_risk = 2650.0 - msg.sl_price
        assert msg.tp_price == pytest.approx(2650.0 + expected_risk * 2.0, rel=0.01)
    
    def test_signal_to_message_factors_include_metadata(self) -> None:
        """Factors dict includes signal metadata."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"structure_alignment": 2.0, "vwap_relation": 2.0},
            rationale="Strong setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
        features = FeaturesMessage(
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
        
        msg = signal_to_message(signal, features)
        
        # Should include original factors and metadata
        assert "structure_alignment" in msg.factors
        assert "vwap_relation" in msg.factors
        assert msg.factors["htf_bias"] == "bullish"
        assert msg.factors["symbol"] == "GC"
        assert msg.factors["timeframe"] == "1m"
        assert msg.factors["rationale"] == "Strong setup"
        assert msg.factors["validation_flags"] == {"session_ok": True}
        assert msg.factors["enforcer_tier"] == "Conservative"
    
    def test_signal_to_message_minimum_sl_distance(self) -> None:
        """Ensure minimum SL distance is enforced for VWAP_RECLAIM."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Close to VWAP",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
        # Entry very close to VWAP
        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2645.5,  # Only 0.5 above VWAP
            vwap=2645.0,
            rsi=55.0,
            ema_9=2648.0,
            ema_20=2645.0,
            ema_50=2640.0,
            dxy_correlation=-0.75,
            structure_label="HH",
            vwap_deviation=0.1,
        )
        
        msg = signal_to_message(signal, features)
        
        # VWAP - 30 ticks = 2642.0, but minimum is 20 ticks from entry
        # Entry 2645.5, so minimum SL = 2645.5 - 2.0 = 2643.5
        # VWAP-based SL = 2645.0 - 3.0 = 2642.0
        # Since 2642.0 is more than 20 ticks (2.0) away, use VWAP-based
        assert msg.sl_price == 2645.0 - 3.0


class TestSignalEngineGenerate:
    """Test SignalEngine.generate method."""
    
    @patch("bot_core_svc.signal_engine.score_signal")
    def test_generate_returns_none_for_low_confidence(
        self, mock_score_signal: Mock
    ) -> None:
        """Generate returns None for non-A+ signals."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=6.5,  # Below A+ threshold
            confidence="Watch",
            factors={"structure_alignment": 1.5},
            rationale="Watchlist signal",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
        mock_score_signal.return_value = signal
        
        engine = SignalEngine()
        features = FeaturesMessage(
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
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        result, rejection_reason = engine.generate(features, htf_bias, {"session_ok": True})
        
        assert result is None
        assert rejection_reason == "confidence_filter"
    
    @patch("bot_core_svc.signal_engine.score_signal")
    def test_generate_returns_none_for_htf_validity_failure(
        self, mock_score_signal: Mock
    ) -> None:
        """Generate returns None with htf_validity reason when conflict or chop detected."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,  # High score but HTF invalid
            confidence="A+",
            factors={"structure_alignment": 2.5},
            rationale="Strong signal but HTF conflict",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
        mock_score_signal.return_value = signal
        
        engine = SignalEngine()
        features = FeaturesMessage(
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
        # HTF bias with conflict detected
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
            conflict_detected=True,
            conflict_reason="15m/1h structure mismatch",
        )
        
        result, rejection_reason = engine.generate(features, htf_bias, {"session_ok": True})
        
        assert result is None
        assert rejection_reason == "htf_validity"
    
    @patch("bot_core_svc.signal_engine.score_signal")
    def test_generate_returns_signal_for_a_plus(
        self, mock_score_signal: Mock
    ) -> None:
        """Generate returns SignalMessage for A+ signals."""
        signal = Signal(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={"structure_alignment": 2.5, "vwap_relation": 2.0},
            rationale="Strong A+ signal",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={"month": 1},
        )
        mock_score_signal.return_value = signal
        
        engine = SignalEngine()
        features = FeaturesMessage(
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
        htf_bias = HTFBiasMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        result, rejection_reason = engine.generate(features, htf_bias, {"session_ok": True})
        
        assert result is not None
        assert rejection_reason is None
        assert isinstance(result, SignalMessage)
        assert result.direction == "long"
        assert result.setup_type == "VWAP_RECLAIM"
        assert result.score == 8.5
        assert result.confidence == "A+"


class TestHTFBiasConversion:
    """Additional HTF bias conversion tests."""
    
    def test_bearish_bias_to_short_direction(self) -> None:
        """Bearish bias converts to short direction."""
        msg = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bearish",
            score=8.0,
            confidence="A",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        htf_bias = htf_bias_message_to_htf_bias(msg)
        
        assert htf_bias.bias == "bearish"
        assert htf_bias.direction == "short"
        assert htf_bias.confidence == "high"
    
    def test_confidence_b_to_medium(self) -> None:
        """Confidence B converts to medium."""
        msg = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bullish",
            score=7.0,
            confidence="B",
            dxy_aligned=True,
            chop_detected=False,
        )
        
        htf_bias = htf_bias_message_to_htf_bias(msg)
        
        assert htf_bias.confidence == "medium"
    
    def test_c_confidence_to_low(self) -> None:
        """C confidence converts to low."""
        msg = HTFBiasMessage(
            timestamp=datetime.now(timezone.utc),
            bias="bullish",
            score=5.0,
            confidence="C",  # Low confidence
            dxy_aligned=False,
            chop_detected=True,
        )
        
        htf_bias = htf_bias_message_to_htf_bias(msg)
        
        assert htf_bias.confidence == "low"

