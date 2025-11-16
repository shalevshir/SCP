"""Unit tests for Signal dataclass.

Tests the core Signal object structure, validation, and immutability
according to SOP requirements.
"""

from datetime import datetime, timezone

import pytest

from rule_engine.signal import Signal


class TestSignalStructure:
    """Test Signal dataclass structure and types."""

    def test_signal_creation_with_all_fields(self) -> None:
        """Test creating a Signal with all required fields."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={
                "structure_alignment": 2,
                "vwap_relation": 2,
                "rsi_state": 2,
                "ema_stack": 1,
                "dxy_corr": 2,
            },
            rationale="HTF HH/HL intact, VWAP reclaim confirmed",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Early Mild",
        )

        assert signal.timestamp == datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert signal.symbol == "GC"
        assert signal.timeframe == "1m"
        assert signal.direction == "long"
        assert signal.setup_type == "VWAP_RECLAIM"
        assert signal.htf_bias == "bullish"
        assert signal.score == 9.0
        assert signal.confidence == "A+"
        assert len(signal.factors) == 5
        assert signal.rationale == "HTF HH/HL intact, VWAP reclaim confirmed"
        assert len(signal.validation_flags) == 4
        assert signal.enforcer_tier == "Early Mild"

    def test_signal_is_immutable(self) -> None:
        """Test that Signal is frozen and cannot be modified."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="Early Mild",
        )

        with pytest.raises(AttributeError):
            signal.score = 10.0  # type: ignore

    def test_signal_with_short_direction(self) -> None:
        """Test Signal for short setup."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=9.5,
            confidence="A+",
            factors={"vwap_deviation": 3, "rsi_extreme": 3},
            rationale="VWAP fade at resistance",
            validation_flags={"session_ok": True},
            enforcer_tier="Mild",
        )

        assert signal.direction == "short"
        assert signal.setup_type == "VWAP_FADE"
        assert signal.htf_bias == "bearish"

    def test_signal_with_neutral_direction(self) -> None:
        """Test Signal with neutral direction."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="5m",
            direction="neutral",
            setup_type="DXY_CONTINUATION",
            htf_bias="neutral",
            score=5.0,
            confidence="Reject",
            factors={},
            rationale="No clear bias",
            validation_flags={"session_ok": False},
            enforcer_tier="Conservative",
        )

        assert signal.direction == "neutral"
        assert signal.confidence == "Reject"

    def test_signal_factors_dict_structure(self) -> None:
        """Test that factors dict contains proper scoring breakdown."""
        factors = {
            "structure_alignment": 2,
            "vwap_relation": 2,
            "rsi_state": 2,
            "ema_stack": 2,
            "dxy_corr": 2,
            "htf_bonus": 1,
        }

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=sum(factors.values()),
            confidence="A+",
            factors=factors,
            rationale="Perfect setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Offensive",
        )

        assert signal.score == 11  # Sum of all factors
        assert signal.factors["structure_alignment"] == 2
        assert signal.factors["htf_bonus"] == 1

    def test_signal_validation_flags_structure(self) -> None:
        """Test that validation_flags dict contains all required checks."""
        validation_flags = {
            "session_ok": True,
            "tier_ok": True,
            "dxy_alignment_ok": True,
            "htf_bias_ok": True,
        }

        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.0,
            confidence="A+",
            factors={},
            rationale="Valid setup",
            validation_flags=validation_flags,
            enforcer_tier="Early Mild",
        )

        assert signal.validation_flags["session_ok"] is True
        assert signal.validation_flags["tier_ok"] is True
        assert signal.validation_flags["dxy_alignment_ok"] is True
        assert signal.validation_flags["htf_bias_ok"] is True


class TestSignalConfidenceLevels:
    """Test Signal confidence classification."""

    def test_a_plus_confidence_threshold(self) -> None:
        """Test A+ confidence for score >= 8."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.0,
            confidence="A+",
            factors={},
            rationale="Minimum A+ threshold",
            validation_flags={"session_ok": True},
            enforcer_tier="Early Mild",
        )

        assert signal.score >= 8.0
        assert signal.confidence == "A+"

    def test_watch_confidence_threshold(self) -> None:
        """Test Watch confidence for score 6-7."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=7.0,
            confidence="Watch",
            factors={},
            rationale="Watchlist setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Early Mild",
        )

        assert 6.0 <= signal.score < 8.0
        assert signal.confidence == "Watch"

    def test_reject_confidence_threshold(self) -> None:
        """Test Reject confidence for score < 6."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=5.0,
            confidence="Reject",
            factors={},
            rationale="Below threshold",
            validation_flags={"session_ok": False},
            enforcer_tier="Conservative",
        )

        assert signal.score < 6.0
        assert signal.confidence == "Reject"


class TestSignalSetupTypes:
    """Test different setup types."""

    def test_vwap_reclaim_setup(self) -> None:
        """Test VWAP_RECLAIM setup type."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.0,
            confidence="A+",
            factors={},
            rationale="VWAP reclaim",
            validation_flags={"session_ok": True},
            enforcer_tier="Early Mild",
        )

        assert signal.setup_type == "VWAP_RECLAIM"

    def test_vwap_fade_setup(self) -> None:
        """Test VWAP_FADE setup type."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="VWAP fade",
            validation_flags={"session_ok": True},
            enforcer_tier="Mild",
        )

        assert signal.setup_type == "VWAP_FADE"

    def test_dxy_continuation_setup(self) -> None:
        """Test DXY_CONTINUATION setup type."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="5m",
            direction="long",
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            score=8.5,
            confidence="A+",
            factors={},
            rationale="DXY continuation",
            validation_flags={"session_ok": True},
            enforcer_tier="Offensive",
        )

        assert signal.setup_type == "DXY_CONTINUATION"


class TestSignalEnforcerTiers:
    """Test enforcer tier assignments."""

    def test_conservative_tier(self) -> None:
        """Test Conservative enforcer tier."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.0,
            confidence="A+",
            factors={},
            rationale="Conservative setup",
            validation_flags={"session_ok": True},
            enforcer_tier="Conservative",
        )

        assert signal.enforcer_tier == "Conservative"

    def test_all_enforcer_tiers(self) -> None:
        """Test all valid enforcer tiers."""
        valid_tiers = ["Conservative", "Early Mild", "Mild", "Offensive"]

        for tier in valid_tiers:
            signal = Signal(
                timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                direction="long",
                setup_type="VWAP_RECLAIM",
                htf_bias="bullish",
                score=8.0,
                confidence="A+",
                factors={},
                rationale=f"{tier} setup",
                validation_flags={"session_ok": True},
                enforcer_tier=tier,
            )

            assert signal.enforcer_tier == tier

