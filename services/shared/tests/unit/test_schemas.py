"""Tests for Pydantic message schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scp_shared.messaging.schemas import (
    CandleMessage,
    FeaturesMessage,
    HTFBiasMessage,
    SignalMessage,
    TradeMessage,
)


class TestCandleMessage:
    """Test CandleMessage schema validation."""

    def test_valid_candle_message(self) -> None:
        """Valid candle message is accepted."""
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert candle.symbol == "GC"
        assert candle.timeframe == "1m"
        assert candle.open == 2650.0

    def test_negative_price_rejected(self) -> None:
        """Negative prices are rejected."""
        with pytest.raises(ValidationError):
            CandleMessage(
                timestamp=datetime.now(UTC),
                symbol="GC",
                timeframe="1m",
                open=-100.0,  # Invalid
                high=2652.0,
                low=2649.0,
                close=2651.0,
                volume=1000.0,
            )

    def test_negative_volume_rejected(self) -> None:
        """Negative volume is rejected."""
        with pytest.raises(ValidationError):
            CandleMessage(
                timestamp=datetime.now(UTC),
                symbol="GC",
                timeframe="1m",
                open=2650.0,
                high=2652.0,
                low=2649.0,
                close=2651.0,
                volume=-100.0,  # Invalid
            )

    def test_json_serialization(self) -> None:
        """Candle can be serialized to JSON."""
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        json_str = candle.model_dump_json()
        assert "GC" in json_str
        assert "2025-01-15" in json_str

        # Deserialize
        candle2 = CandleMessage.model_validate_json(json_str)
        assert candle2.symbol == candle.symbol
        assert candle2.close == candle.close


class TestFeaturesMessage:
    """Test FeaturesMessage schema validation."""

    def test_valid_features_message(self) -> None:
        """Valid features message is accepted."""
        features = FeaturesMessage(
            timestamp=datetime.now(UTC),
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            vwap=2650.5,
            rsi=55.2,
            ema_9=2649.8,
            ema_20=2648.5,
            ema_50=2647.0,
            dxy_correlation=-0.75,
            structure_label="HH",
            vwap_deviation=0.02,
        )

        assert features.symbol == "GC"
        assert features.rsi == 55.2

    def test_rsi_bounds_validation(self) -> None:
        """RSI must be between 0 and 100."""
        with pytest.raises(ValidationError):
            FeaturesMessage(
                timestamp=datetime.now(UTC),
                symbol="GC",
                timeframe="1m",
                close=2651.0,
                rsi=150.0,  # Invalid
            )

    def test_correlation_bounds_validation(self) -> None:
        """Correlation must be between -1 and 1."""
        with pytest.raises(ValidationError):
            FeaturesMessage(
                timestamp=datetime.now(UTC),
                symbol="GC",
                timeframe="1m",
                close=2651.0,
                dxy_correlation=1.5,  # Invalid
            )

    def test_partial_features_allowed(self) -> None:
        """Features can be None during warmup."""
        features = FeaturesMessage(
            timestamp=datetime.now(UTC),
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            vwap=None,  # Not yet computed
            rsi=None,
        )

        assert features.vwap is None
        assert features.rsi is None


class TestHTFBiasMessage:
    """Test HTFBiasMessage schema validation."""

    def test_valid_htf_bias_message(self) -> None:
        """Valid HTF bias message is accepted."""
        bias = HTFBiasMessage(
            timestamp=datetime.now(UTC),
            bias="bullish",
            score=8.5,
            confidence="A+",
            structure_15m="HH",
            structure_1h="bullish",
            dxy_aligned=True,
            chop_detected=False,
        )

        assert bias.bias == "bullish"
        assert bias.score == 8.5

    def test_invalid_bias_rejected(self) -> None:
        """Invalid bias value is rejected."""
        with pytest.raises(ValidationError):
            HTFBiasMessage(
                timestamp=datetime.now(UTC),
                bias="sideways",  # Invalid
                score=8.5,
                confidence="A+",
                dxy_aligned=True,
                chop_detected=False,
            )

    def test_score_bounds_validation(self) -> None:
        """Score must be between 0 and 10."""
        with pytest.raises(ValidationError):
            HTFBiasMessage(
                timestamp=datetime.now(UTC),
                bias="bullish",
                score=15.0,  # Invalid
                confidence="A+",
                dxy_aligned=True,
                chop_detected=False,
            )


class TestSignalMessage:
    """Test SignalMessage schema validation."""

    def test_valid_signal_message(self) -> None:
        """Valid signal message is accepted."""
        signal = SignalMessage(
            id="550e8400-e29b-41d4-a716-446655440000",
            timestamp=datetime.now(UTC),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=9.0,
            confidence="A+",
            entry_price=2651.0,
            sl_price=2645.0,
            tp_price=2663.0,
            factors={"vwap_reclaim": True, "htf_bullish": True},
        )

        assert signal.direction == "long"
        assert signal.setup_type == "VWAP_RECLAIM"

    def test_invalid_direction_rejected(self) -> None:
        """Invalid direction is rejected."""
        with pytest.raises(ValidationError):
            SignalMessage(
                id="550e8400-e29b-41d4-a716-446655440000",
                timestamp=datetime.now(UTC),
                direction="neutral",  # Invalid
                setup_type="VWAP_RECLAIM",
                score=9.0,
                confidence="A+",
                entry_price=2651.0,
                sl_price=2645.0,
                tp_price=2663.0,
                factors={},
            )


class TestTradeMessage:
    """Test TradeMessage schema validation."""

    def test_valid_trade_message(self) -> None:
        """Valid trade message is accepted."""
        trade = TradeMessage(
            id="660e8400-e29b-41d4-a716-446655440001",
            signal_id="550e8400-e29b-41d4-a716-446655440000",
            direction="long",
            entry_price=2651.0,
            sl_price=2645.0,
            tp_price=2663.0,
            quantity=1,
            opened_at=datetime.now(UTC),
        )

        assert trade.direction == "long"
        assert trade.quantity == 1

    def test_closed_trade(self) -> None:
        """Trade can include close information."""
        trade = TradeMessage(
            id="660e8400-e29b-41d4-a716-446655440001",
            signal_id="550e8400-e29b-41d4-a716-446655440000",
            direction="long",
            entry_price=2651.0,
            sl_price=2645.0,
            tp_price=2663.0,
            quantity=1,
            opened_at=datetime.now(UTC),
            closed_at=datetime.now(UTC),
            exit_price=2663.0,
            pnl_points=12.0,
            exit_reason="TP_HIT",
        )

        assert trade.closed_at is not None
        assert trade.pnl_points == 12.0
        assert trade.exit_reason == "TP_HIT"

