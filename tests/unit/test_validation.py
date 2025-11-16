"""Unit tests for RuleEngine validation layer.

Tests SOP compliance validation including session checks, tier restrictions,
DXY alignment, and HTF bias validation.
"""

from datetime import datetime, timezone

import pytest

from rule_engine.signal import Signal
from rule_engine.validation import validate_signal


class TestValidateSignal:
    """Test signal validation function."""

    def test_validate_all_checks_pass(self) -> None:
        """Test signal with all validation checks passing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Early Mild",
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
            "htf_direction": "long",
        }

        validated = validate_signal(signal, context)

        assert validated.confidence == "A+"
        assert validated.validation_flags["session_ok"] is True
        assert validated.validation_flags["tier_ok"] is True

    def test_validate_invalid_session_downgrades_to_reject(self) -> None:
        """Test that invalid session downgrades confidence to Reject."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Early Mild",
        )

        context = {
            "session_ok": False,  # Invalid session
            "enforcer_tier": "Early Mild",
            "htf_direction": "long",
        }

        validated = validate_signal(signal, context)

        assert validated.confidence == "Reject"
        assert validated.validation_flags["session_ok"] is False

    def test_validate_htf_bias_mismatch_downgrades_to_reject(self) -> None:
        """Test that HTF bias mismatch downgrades confidence to Reject."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Early Mild",
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
            "htf_direction": "short",  # Mismatch with signal direction
        }

        validated = validate_signal(signal, context)

        assert validated.confidence == "Reject"
        assert validated.validation_flags["htf_bias_ok"] is False

    def test_validate_dxy_alignment_check(self) -> None:
        """Test DXY correlation alignment validation."""
        # Signal with poor DXY correlation
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.0,
            confidence="A+",
            factors={"dxy_corr": 0},  # No DXY correlation info
            rationale="Test",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": False,  # Poor correlation
                "htf_bias_ok": True,
            },
            enforcer_tier="Early Mild",
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
            "htf_direction": "long",
            "dxy_corr": -0.3,  # Weak correlation
        }

        validated = validate_signal(signal, context)

        assert validated.validation_flags["dxy_alignment_ok"] is False

    def test_validate_tier_restriction(self) -> None:
        """Test that tier restrictions are enforced."""
        # VWAP_FADE setup with Conservative tier (not allowed)
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
            rationale="Test",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Conservative",
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Conservative",
            "htf_direction": "short",
        }

        validated = validate_signal(signal, context)

        # Conservative tier doesn't allow VWAP_FADE
        assert validated.validation_flags["tier_ok"] is False
        assert validated.confidence == "Reject"


class TestValidationFlags:
    """Test individual validation flag updates."""

    def test_session_ok_flag_updates(self) -> None:
        """Test session_ok flag is updated correctly."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Early Mild",
        )

        # Test with invalid session
        context_invalid = {
            "session_ok": False,
            "enforcer_tier": "Early Mild",
            "htf_direction": "long",
        }

        validated = validate_signal(signal, context_invalid)
        assert validated.validation_flags["session_ok"] is False

    def test_tier_ok_flag_updates(self) -> None:
        """Test tier_ok flag is updated based on allowed setups."""
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
            rationale="Test",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Conservative",
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Conservative",
            "htf_direction": "short",
        }

        validated = validate_signal(signal, context)
        # Conservative doesn't allow VWAP_FADE
        assert validated.validation_flags["tier_ok"] is False

    def test_htf_bias_ok_flag_updates(self) -> None:
        """Test htf_bias_ok flag is updated on mismatch."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={
                "session_ok": True,
                "tier_ok": True,
                "dxy_alignment_ok": True,
                "htf_bias_ok": True,
            },
            enforcer_tier="Early Mild",
        )

        context = {
            "session_ok": True,
            "enforcer_tier": "Early Mild",
            "htf_direction": "short",  # Mismatch
        }

        validated = validate_signal(signal, context)
        assert validated.validation_flags["htf_bias_ok"] is False


class TestValidationEnforcerTiers:
    """Test validation for different enforcer tiers."""

    def test_conservative_tier_restrictions(self) -> None:
        """Test Conservative tier allows only VWAP_RECLAIM and DXY_CONTINUATION."""
        allowed_setups = ["VWAP_RECLAIM", "DXY_CONTINUATION"]
        forbidden_setups = ["VWAP_FADE"]

        for setup_type in allowed_setups:
            signal = Signal(
                timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                direction="long",
                setup_type=setup_type,
                htf_bias="bullish",
                score=9.0,
                confidence="A+",
                factors={},
                rationale="Test",
                validation_flags={
                    "session_ok": True,
                    "tier_ok": True,
                    "dxy_alignment_ok": True,
                    "htf_bias_ok": True,
                },
                enforcer_tier="Conservative",
            )

            context = {
                "session_ok": True,
                "enforcer_tier": "Conservative",
                "htf_direction": "long",
            }

            validated = validate_signal(signal, context)
            assert validated.validation_flags["tier_ok"] is True

        for setup_type in forbidden_setups:
            signal = Signal(
                timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                direction="short",
                setup_type=setup_type,
                htf_bias="bearish",
                score=9.0,
                confidence="A+",
                factors={},
                rationale="Test",
                validation_flags={
                    "session_ok": True,
                    "tier_ok": True,
                    "dxy_alignment_ok": True,
                    "htf_bias_ok": True,
                },
                enforcer_tier="Conservative",
            )

            context = {
                "session_ok": True,
                "enforcer_tier": "Conservative",
                "htf_direction": "short",
            }

            validated = validate_signal(signal, context)
            assert validated.validation_flags["tier_ok"] is False

    def test_offensive_tier_allows_all_setups(self) -> None:
        """Test Offensive tier allows all setup types."""
        all_setups = ["VWAP_RECLAIM", "VWAP_FADE", "DXY_CONTINUATION"]

        for setup_type in all_setups:
            signal = Signal(
                timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                symbol="GC",
                timeframe="1m",
                direction="long",
                setup_type=setup_type,
                htf_bias="bullish",
                score=9.0,
                confidence="A+",
                factors={},
                rationale="Test",
                validation_flags={
                    "session_ok": True,
                    "tier_ok": True,
                    "dxy_alignment_ok": True,
                    "htf_bias_ok": True,
                },
                enforcer_tier="Offensive",
            )

            context = {
                "session_ok": True,
                "enforcer_tier": "Offensive",
                "htf_direction": "long",
            }

            validated = validate_signal(signal, context)
            assert validated.validation_flags["tier_ok"] is True

