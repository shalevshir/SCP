"""Unit tests for signal engine."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage
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
        
        # Should return None (filtered out) instead of raising ValidationError
        result = engine.generate(features, htf_bias, context)
        
        assert result is None
        mock_score_signal.assert_called_once()


class TestSignalToMessage:
    """Test signal_to_message function with SL/TP calculations."""
    
    @pytest.fixture
    def base_signal(self) -> Signal:
        """Create base signal for testing."""
        return Signal(
            timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={
                "structure_alignment": 2.0,
                "vwap_relation": 2.0,
                "htf_aligned": True,
                "dxy_aligned": True,
            },
            rationale="VWAP reclaim with HTF alignment",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
    
    @pytest.fixture
    def base_features(self) -> FeaturesMessage:
        """Create base features message."""
        return FeaturesMessage(
            timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2050.0,
            vwap=2045.0,
            rsi=55.0,
            ema_9=2048.0,
            ema_20=2045.0,
            ema_50=2040.0,
            dxy_correlation=-0.75,
            structure_label="HH",
            vwap_deviation=0.5,
        )
    
    # SL/TP calculation tests (from backtester/trade.py SOP rules)
    
    def test_signal_to_message_calculates_vwap_reclaim_sl(
        self,
        base_signal: Signal,
        base_features: FeaturesMessage,
    ) -> None:
        """VWAP zone SL with 30-tick buffer."""
        # Long signal: SL = VWAP - (30 ticks * 0.1)
        signal_msg = signal_to_message(base_signal, base_features)
        
        assert signal_msg.direction == "long"
        assert signal_msg.entry_price == 2050.0
        # VWAP = 2045.0, buffer = 30 * 0.1 = 3.0
        # SL = 2045.0 - 3.0 = 2042.0
        assert signal_msg.sl_price == 2042.0
    
    def test_signal_to_message_enforces_min_sl_20_ticks_vwap_reclaim(
        self,
        base_signal: Signal,
    ) -> None:
        """Minimum 20-tick SL distance enforced when VWAP-based SL is too close.
        
        For long trades, the minimum is enforced when:
        entry - (VWAP - 30_ticks) < 20_ticks
        
        This happens when VWAP is above entry - 10 ticks, i.e., when VWAP > 2049.0
        """
        # Use VWAP above entry to trigger minimum enforcement
        # Entry = 2050.0, VWAP = 2051.5 (above entry)
        features = FeaturesMessage(
            timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2050.0,
            vwap=2051.5,  # Above entry - will trigger minimum
            rsi=55.0,
        )
        
        signal_msg = signal_to_message(base_signal, features)
        
        # Calculation:
        # Step 1: VWAP - 30 ticks = 2051.5 - 3.0 = 2048.5
        # Step 2: Risk distance = 2050.0 - 2048.5 = 1.5 = 15 ticks
        # Step 3: Since 15 < 20, enforce minimum: SL = 2050.0 - 2.0 = 2048.0
        assert signal_msg.sl_price == 2048.0
    
    def test_signal_to_message_calculates_vwap_fade_sl(
        self,
        base_features: FeaturesMessage,
    ) -> None:
        """15-tick minimum for fade."""
        fade_signal = Signal(
            timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="Fade test",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
        
        signal_msg = signal_to_message(fade_signal, base_features)
        
        # Short fade: SL = entry + (15 ticks * 0.1)
        # Entry = 2050.0, SL = 2050.0 + 1.5 = 2051.5
        assert signal_msg.sl_price == 2051.5
    
    def test_signal_to_message_calculates_dxy_continuation_sl(
        self,
        base_features: FeaturesMessage,
    ) -> None:
        """25-tick minimum for DXY continuation."""
        dxy_signal = Signal(
            timestamp=datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="DXY continuation test",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
        
        signal_msg = signal_to_message(dxy_signal, base_features)
        
        # Long continuation: SL = entry - (25 ticks * 0.1)
        # Entry = 2050.0, SL = 2050.0 - 2.5 = 2047.5
        assert signal_msg.sl_price == 2047.5
    
    def test_signal_to_message_calculates_tp_with_r_multiple(
        self,
        base_signal: Signal,
        base_features: FeaturesMessage,
    ) -> None:
        """R-multiple based TP calculation."""
        signal_msg = signal_to_message(base_signal, base_features)
        
        # Long: Risk = entry - SL = 2050.0 - 2042.0 = 8.0
        # TP = entry + (risk * R_multiple) = 2050.0 + (8.0 * 3.0) = 2074.0
        risk = signal_msg.entry_price - signal_msg.sl_price
        assert risk == 8.0
        
        # Default continuation R-multiple = 3.0 for non-September months
        expected_tp = signal_msg.entry_price + (risk * 3.0)
        assert signal_msg.tp_price == expected_tp
    
    # Seasonal R-multiple tests
    
    def test_signal_to_message_september_uses_2r(
        self,
        base_features: FeaturesMessage,
    ) -> None:
        """September defensive: 2R."""
        sept_signal = Signal(
            timestamp=datetime(2024, 9, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="September test",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )
        
        signal_msg = signal_to_message(sept_signal, base_features)
        
        # Risk = 2050.0 - 2047.5 = 2.5
        # TP = 2050.0 + (2.5 * 2.0) = 2055.0 (September uses 2R)
        risk = signal_msg.entry_price - signal_msg.sl_price
        expected_tp = signal_msg.entry_price + (risk * 2.0)
        assert signal_msg.tp_price == expected_tp
    
    def test_signal_to_message_november_december_uses_3r_with_alignment(
        self,
        base_features: FeaturesMessage,
    ) -> None:
        """Trend season upgrade to 3R with alignment."""
        nov_fade_signal = Signal(
            timestamp=datetime(2024, 11, 15, 10, 30, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="November fade with alignment",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
            diagnostics={
                "htf_aligned": True,
                "dxy_aligned": True,
            },
        )
        
        signal_msg = signal_to_message(nov_fade_signal, base_features)
        
        # Fade in Nov/Dec with alignment: upgrade to 3R
        # Risk = 2050.0 - (2050.0 - 1.5) = 1.5
        # TP = 2050.0 + (1.5 * 3.0) = 2054.5
        risk = signal_msg.entry_price - signal_msg.sl_price
        expected_tp = signal_msg.entry_price + (risk * 3.0)
        assert signal_msg.tp_price == expected_tp
    
    def test_signal_to_message_default_continuation_uses_3r(
        self,
        base_signal: Signal,
        base_features: FeaturesMessage,
    ) -> None:
        """Default continuation R-multiple = 3R."""
        signal_msg = signal_to_message(base_signal, base_features)
        
        # Non-September, non-fade: default 3R
        risk = signal_msg.entry_price - signal_msg.sl_price
        expected_tp = signal_msg.entry_price + (risk * 3.0)
        assert signal_msg.tp_price == expected_tp
    
    # Edge cases
    
    def test_signal_to_message_generates_unique_id(
        self,
        base_signal: Signal,
        base_features: FeaturesMessage,
    ) -> None:
        """UUID generation for each signal."""
        signal_msg1 = signal_to_message(base_signal, base_features)
        signal_msg2 = signal_to_message(base_signal, base_features)
        
        # Each message should have unique ID
        assert signal_msg1.id != signal_msg2.id
        # Should be valid UUID format (36 chars with dashes)
        assert len(signal_msg1.id) == 36
        assert signal_msg1.id.count("-") == 4
    
    def test_signal_to_message_includes_all_factors(
        self,
        base_signal: Signal,
        base_features: FeaturesMessage,
    ) -> None:
        """Factors dict with htf_bias, rationale, etc."""
        signal_msg = signal_to_message(base_signal, base_features)
        
        # Verify all expected fields in factors
        assert "htf_bias" in signal_msg.factors
        assert signal_msg.factors["htf_bias"] == "bullish"
        
        assert "symbol" in signal_msg.factors
        assert signal_msg.factors["symbol"] == "GC"
        
        assert "timeframe" in signal_msg.factors
        assert signal_msg.factors["timeframe"] == "1m"
        
        assert "rationale" in signal_msg.factors
        assert signal_msg.factors["rationale"] == "VWAP reclaim with HTF alignment"
        
        assert "validation_flags" in signal_msg.factors
        assert signal_msg.factors["validation_flags"]["session_ok"] is True
        
        assert "enforcer_tier" in signal_msg.factors
        assert signal_msg.factors["enforcer_tier"] == "Conservative"
        
        # Original signal factors should also be included
        assert "structure_alignment" in signal_msg.factors
        assert signal_msg.factors["structure_alignment"] == 2.0

