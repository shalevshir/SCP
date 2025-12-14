"""Unit tests for ValidationContextBuilder.

Tests HTF bias computation, DXY handling, and ValidationContext building.
"""

import pandas as pd
from validation.context_builder import (
    ValidationContextBuilder,
    check_dxy_handling_for_setup,
)
from validation.guardrails import GuardrailResult
from validation.schema import BufferPhase, EnforcerTier, HTFBias
from validation.session_validator import (
    SessionConstraints,
    SessionResult,
)


class TestValidationContextBuilder:
    """Test ValidationContextBuilder functionality."""

    def test_build_context_basic(self) -> None:
        """Test basic context building with minimal inputs."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
                "structure_type": "HH",
            }
        )

        market_state = {
            "buffer_phase": "0-5k",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
        }

        session_result = SessionResult(
            session_ok=True,
            constraints=self._create_test_constraints(),
        )

        context = builder.build_context(features, market_state, session_result)

        assert context.session_ok is True
        assert context.tier_active == EnforcerTier.CONSERVATIVE
        assert context.htf_bias == HTFBias.BULLISH
        assert context.dxy_trending_clean is True
        assert context.buffer_phase == BufferPhase.STARTUP

    def test_compute_htf_bias_bullish(self) -> None:
        """Test HTF bias computation for bullish setup."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "structure_type": "HH",  # Bullish structure
                "ema_9": 2650.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,  # Bullish EMA stack
                "close": 2655.0,
                "vwap": 2645.0,  # Price above VWAP
                "dxy_corr": -0.75,
            }
        )

        bias = builder._compute_htf_bias(features)
        assert bias == HTFBias.BULLISH

    def test_compute_htf_bias_bearish(self) -> None:
        """Test HTF bias computation for bearish setup."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "structure_type": "LL",  # Bearish structure
                "ema_9": 2640.0,
                "ema_20": 2645.0,
                "ema_50": 2650.0,  # Bearish EMA stack
                "close": 2635.0,
                "vwap": 2645.0,  # Price below VWAP
                "dxy_corr": -0.75,
            }
        )

        bias = builder._compute_htf_bias(features)
        assert bias == HTFBias.BEARISH

    def test_compute_htf_bias_neutral(self) -> None:
        """Test HTF bias computation for neutral/mixed signals."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "structure_type": "HL",  # Neutral structure
                "ema_9": 2645.0,
                "ema_20": 2645.0,
                "ema_50": 2645.0,  # Flat EMAs
                "close": 2645.0,
                "vwap": 2645.0,  # Price at VWAP
                "dxy_corr": -0.5,
            }
        )

        bias = builder._compute_htf_bias(features)
        assert bias == HTFBias.NEUTRAL

    def test_dxy_trending_clean_strong_correlation(self) -> None:
        """Test DXY trending status with strong correlation."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "dxy_corr": -0.75,  # Strong inverse correlation
            }
        )

        assert builder._is_dxy_trending_clean(features) is True

    def test_dxy_trending_clean_weak_correlation(self) -> None:
        """Test DXY trending status with weak correlation."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "dxy_corr": -0.4,  # Weak correlation
            }
        )

        assert builder._is_dxy_trending_clean(features) is False

    def test_dxy_trending_clean_missing_data(self) -> None:
        """Test DXY trending status with missing data."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "dxy_corr": None,  # Missing DXY data
            }
        )

        assert builder._is_dxy_trending_clean(features) is False

    def test_check_dxy_availability_present(self) -> None:
        """Test DXY availability check with valid data."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "dxy_corr": -0.75,
            }
        )

        assert builder._check_dxy_availability(features) is True

    def test_check_dxy_availability_none(self) -> None:
        """Test DXY availability check with None."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "dxy_corr": None,
            }
        )

        assert builder._check_dxy_availability(features) is False

    def test_check_dxy_availability_nan(self) -> None:
        """Test DXY availability check with NaN."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "dxy_corr": float("nan"),
            }
        )

        assert builder._check_dxy_availability(features) is False

    def test_parse_buffer_phase_all_phases(self) -> None:
        """Test buffer phase parsing for all phases."""
        builder = ValidationContextBuilder()

        assert builder._parse_buffer_phase("0-5k") == BufferPhase.STARTUP
        assert builder._parse_buffer_phase("5-15k") == BufferPhase.GROWTH
        assert builder._parse_buffer_phase("15-40k") == BufferPhase.SCALING
        assert builder._parse_buffer_phase("40k+") == BufferPhase.INSTITUTIONAL

    def test_parse_enforcer_tier_all_tiers(self) -> None:
        """Test enforcer tier parsing for all tiers."""
        builder = ValidationContextBuilder()

        assert builder._parse_enforcer_tier("Conservative") == EnforcerTier.CONSERVATIVE
        assert builder._parse_enforcer_tier("EarlyMild") == EnforcerTier.EARLY_MILD
        assert builder._parse_enforcer_tier("Early Mild") == EnforcerTier.EARLY_MILD
        assert builder._parse_enforcer_tier("Mild") == EnforcerTier.MILD
        assert builder._parse_enforcer_tier("Offensive") == EnforcerTier.OFFENSIVE

    def test_context_with_guardrail_result(self) -> None:
        """Test context building with guardrail result."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
                "structure_type": "HH",
            }
        )

        market_state = {
            "buffer_phase": "0-5k",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
        }

        session_result = SessionResult(
            session_ok=True,
            constraints=self._create_test_constraints(),
        )

        # Guardrail blocking
        guardrail_result = GuardrailResult(
            allowed=False,
            reasons=["Loss streak limit reached"],
        )

        context = builder.build_context(
            features, market_state, session_result, guardrail_result
        )

        # risk_allowed should be False due to guardrails
        assert context.risk_allowed is False

    def test_context_with_fatigue_flag(self) -> None:
        """Test context building with fatigue flag set."""
        builder = ValidationContextBuilder()

        features = pd.Series(
            {
                "close": 2650.0,
                "vwap": 2645.0,
                "ema_9": 2648.0,
                "ema_20": 2645.0,
                "ema_50": 2640.0,
                "dxy_corr": -0.75,
                "structure_type": "HH",
            }
        )

        market_state = {
            "buffer_phase": "0-5k",
            "tier_active": "Conservative",
            "ceo_directive_active": False,
            "news_ok": True,
            "fatigue_flag": True,
        }

        session_result = SessionResult(
            session_ok=True,
            constraints=self._create_test_constraints(),
        )

        context = builder.build_context(features, market_state, session_result)

        assert context.fatigue_flag is True

    def _create_test_constraints(self) -> SessionConstraints:
        """Create test session constraints."""
        from datetime import time

        return SessionConstraints(
            name="Test Season",
            window_start=time(10, 0),
            window_end=time(13, 0),
            allowed_tiers=frozenset(["Conservative", "EarlyMild"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "DXY_CONTINUATION"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=-0.6,
        )


class TestDXYHandling:
    """Test DXY unavailability handling."""

    def test_dxy_handling_reclaim_unavailable(self) -> None:
        """Test VWAP_RECLAIM rejection when DXY unavailable."""
        allowed, warning = check_dxy_handling_for_setup("VWAP_RECLAIM", False)

        assert allowed is False
        assert "requires DXY data" in warning

    def test_dxy_handling_continuation_unavailable(self) -> None:
        """Test DXY_CONTINUATION rejection when DXY unavailable."""
        allowed, warning = check_dxy_handling_for_setup("DXY_CONTINUATION", False)

        assert allowed is False
        assert "requires DXY data" in warning

    def test_dxy_handling_fade_unavailable(self) -> None:
        """Test VWAP_FADE allowed with warning when DXY unavailable."""
        allowed, warning = check_dxy_handling_for_setup("VWAP_FADE", False)

        assert allowed is True
        assert "allowed with warning" in warning

    def test_dxy_handling_all_setups_available(self) -> None:
        """Test all setups allowed when DXY available."""
        for setup_type in ["VWAP_RECLAIM", "DXY_CONTINUATION", "VWAP_FADE"]:
            allowed, warning = check_dxy_handling_for_setup(setup_type, True)
            assert allowed is True
            assert warning is None

    def test_dxy_handling_unknown_setup(self) -> None:
        """Test unknown setup type rejected when DXY unavailable."""
        allowed, warning = check_dxy_handling_for_setup("UNKNOWN_SETUP", False)

        assert allowed is False
        assert "Unknown setup type" in warning
