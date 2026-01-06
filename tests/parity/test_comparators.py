"""Unit tests for parity comparison functions."""

from datetime import UTC, datetime

import pandas as pd
import pytest
from scripts.parity.comparators import (
    FeatureComparison,
    SignalComparison,
    _is_close,
    compare_features,
    compare_signals,
)


class TestIsClose:
    """Test the _is_close helper function."""

    def test_both_none(self):
        """Both None values should match."""
        assert _is_close(None, None, 0.01)

    def test_one_none(self):
        """One None, one not None should not match."""
        assert not _is_close(None, 5.0, 0.01)
        assert not _is_close(5.0, None, 0.01)

    def test_both_nan(self):
        """Both NaN values should match."""
        assert _is_close(float("nan"), float("nan"), 0.01)

    def test_one_nan(self):
        """One NaN, one not NaN should not match."""
        assert not _is_close(float("nan"), 5.0, 0.01)
        assert not _is_close(5.0, float("nan"), 0.01)

    def test_numeric_within_tolerance(self):
        """Numeric values within tolerance should match."""
        assert _is_close(5.0, 5.005, 0.01)
        assert _is_close(5.0, 4.995, 0.01)

    def test_numeric_outside_tolerance(self):
        """Numeric values outside tolerance should not match."""
        assert not _is_close(5.0, 5.02, 0.01)
        assert not _is_close(5.0, 4.98, 0.01)

    def test_string_equality(self):
        """String values should use exact equality."""
        assert _is_close("HH", "HH", 0.01)
        assert not _is_close("HH", "HL", 0.01)


class TestCompareFeatures:
    """Test feature comparison function."""

    @pytest.fixture
    def sample_bt_features(self) -> pd.Series:
        """Create sample backtester features."""
        return pd.Series(
            {
                "timestamp": datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
                "close": 2650.0,
                "vwap": 2648.5,
                "rsi": 58.234,
                "ema_9": 2649.5,
                "ema_20": 2647.0,
                "ema_50": 2645.0,
                "dxy_corr": -0.65,
                "structure_label": "HL",
            }
        )

    @pytest.fixture
    def sample_ms_features(self) -> pd.Series:
        """Create sample microservices features (identical)."""
        return pd.Series(
            {
                "timestamp": datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
                "close": 2650.0,
                "vwap": 2648.5,
                "rsi": 58.234,
                "ema_9": 2649.5,
                "ema_20": 2647.0,
                "ema_50": 2645.0,
                "dxy_corr": -0.65,
                "structure_label": "HL",
            }
        )

    def test_identical_features_match(self, sample_bt_features, sample_ms_features):
        """Identical features should match."""
        result = compare_features(sample_bt_features, sample_ms_features)

        assert result.matches
        assert len(result.differences) == 0
        assert result.matching_fields == result.all_fields_compared

    def test_small_numeric_difference_within_tolerance(
        self, sample_bt_features, sample_ms_features
    ):
        """Small numeric difference within tolerance should match."""
        sample_ms_features["rsi"] = 58.240  # 0.006 difference, within 0.5 tolerance

        result = compare_features(sample_bt_features, sample_ms_features)

        assert result.matches
        assert len(result.differences) == 0

    def test_numeric_difference_outside_tolerance(
        self, sample_bt_features, sample_ms_features
    ):
        """Numeric difference outside tolerance should not match."""
        sample_ms_features["rsi"] = 57.5  # 0.734 difference, outside 0.5 tolerance

        result = compare_features(sample_bt_features, sample_ms_features)

        assert not result.matches
        assert "rsi" in result.differences
        assert result.differences["rsi"] == (58.234, 57.5)

    def test_categorical_field_mismatch(self, sample_bt_features, sample_ms_features):
        """Categorical field mismatch should be detected."""
        sample_ms_features["structure_label"] = "HH"

        result = compare_features(sample_bt_features, sample_ms_features)

        assert not result.matches
        assert "structure_label" in result.differences
        assert result.differences["structure_label"] == ("HL", "HH")

    def test_missing_field_in_one_series(self, sample_bt_features, sample_ms_features):
        """Missing field should be detected as difference."""
        sample_ms_features.pop("rsi")

        result = compare_features(sample_bt_features, sample_ms_features)

        assert not result.matches
        assert "rsi" in result.differences
        assert result.differences["rsi"] == (58.234, None)

    def test_custom_tolerances(self, sample_bt_features, sample_ms_features):
        """Custom tolerances should be applied."""
        sample_ms_features["rsi"] = 57.5  # Would fail with default tolerance

        # Use very loose tolerance
        custom_tolerances = {"rsi": 1.0}
        result = compare_features(
            sample_bt_features, sample_ms_features, tolerances=custom_tolerances
        )

        assert result.matches

    def test_excludes_metadata_fields(self, sample_bt_features, sample_ms_features):
        """Metadata fields should not be compared."""
        sample_ms_features["symbol"] = "DIFFERENT"  # Should be ignored

        result = compare_features(sample_bt_features, sample_ms_features)

        assert result.matches  # Still matches because symbol is excluded


class TestCompareSignals:
    """Test signal comparison function."""

    @pytest.fixture
    def mock_signal_bt(self):
        """Create mock backtester signal."""
        from rule_engine.signal import Signal

        return Signal(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.2,
            confidence="A+",
            rationale="Test signal",
            factors={},
            validation_flags={},
            diagnostics={},
            htf_bias="bullish",
            symbol="GC",
            timeframe="1m",
            enforcer_tier="EarlyMild",
        )

    @pytest.fixture
    def mock_signal_ms(self):
        """Create mock microservices signal."""
        from scp_shared.rule_engine.signal import Signal

        return Signal(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.2,
            confidence="A+",
            rationale="Test signal",
            factors={},
            validation_flags={},
            diagnostics={},
            htf_bias="bullish",
            symbol="GC",
            timeframe="1m",
            enforcer_tier="EarlyMild",
        )

    def test_both_none_signals_match(self):
        """Both None signals should match."""
        result = compare_signals(None, None)

        assert result.matches
        assert result.bt_signal is None
        assert result.ms_signal is None

    def test_one_signal_none_does_not_match(self, mock_signal_bt):
        """One None signal should not match."""
        result = compare_signals(mock_signal_bt, None)

        assert not result.matches
        assert result.bt_signal is not None
        assert result.ms_signal is None
        assert "signal_generated" in result.field_diffs

    def test_identical_signals_match(self, mock_signal_bt, mock_signal_ms):
        """Identical signals should match."""
        result = compare_signals(mock_signal_bt, mock_signal_ms)

        assert result.matches
        assert len(result.field_diffs) == 0

    def test_different_confidence_does_not_match(self, mock_signal_bt):
        """Different confidence should not match."""
        from scp_shared.rule_engine.signal import Signal

        mock_signal_ms = Signal(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.2,
            confidence="A",  # Different confidence
            rationale="Test signal",
            factors={},
            validation_flags={},
            diagnostics={},
            htf_bias="bullish",
            symbol="GC",
            timeframe="1m",
            enforcer_tier="EarlyMild",
        )

        result = compare_signals(mock_signal_bt, mock_signal_ms)

        assert not result.matches
        assert "confidence" in result.field_diffs
        assert result.field_diffs["confidence"] == ("A+", "A")

    def test_score_within_tolerance_matches(self, mock_signal_bt):
        """Score within tolerance should match."""
        from scp_shared.rule_engine.signal import Signal

        mock_signal_ms = Signal(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.25,  # 0.05 difference, within 0.1 tolerance
            confidence="A+",
            rationale="Test signal",
            factors={},
            validation_flags={},
            diagnostics={},
            htf_bias="bullish",
            symbol="GC",
            timeframe="1m",
            enforcer_tier="EarlyMild",
        )

        result = compare_signals(mock_signal_bt, mock_signal_ms)

        assert result.matches

    def test_score_outside_tolerance_does_not_match(self, mock_signal_bt):
        """Score outside tolerance should not match."""
        from scp_shared.rule_engine.signal import Signal

        mock_signal_ms = Signal(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=7.9,  # 0.3 difference, outside 0.1 tolerance
            confidence="A+",
            rationale="Test signal",
            factors={},
            validation_flags={},
            diagnostics={},
            htf_bias="bullish",
            symbol="GC",
            timeframe="1m",
            enforcer_tier="EarlyMild",
        )

        result = compare_signals(mock_signal_bt, mock_signal_ms)

        assert not result.matches
        assert "score" in result.field_diffs
        assert result.field_diffs["score"] == (8.2, 7.9)

    def test_different_setup_type_does_not_match(self, mock_signal_bt):
        """Different setup type should not match."""
        from scp_shared.rule_engine.signal import Signal

        mock_signal_ms = Signal(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            direction="long",
            setup_type="VWAP_FADE",  # Different setup type
            score=8.2,
            confidence="A+",
            rationale="Test signal",
            factors={},
            validation_flags={},
            diagnostics={},
            htf_bias="bullish",
            symbol="GC",
            timeframe="1m",
            enforcer_tier="EarlyMild",
        )

        result = compare_signals(mock_signal_bt, mock_signal_ms)

        assert not result.matches
        assert "setup_type" in result.field_diffs


class TestFeatureComparison:
    """Test FeatureComparison dataclass."""

    def test_summary_for_matching_features(self):
        """Summary should show success for matching features."""
        comparison = FeatureComparison(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            matches=True,
            all_fields_compared=10,
            matching_fields=10,
        )

        summary = comparison.summary()

        assert "✓" in summary
        assert "10 fields match" in summary

    def test_summary_for_differing_features(self):
        """Summary should show differences."""
        comparison = FeatureComparison(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            matches=False,
            differences={"rsi": (58.234, 57.5), "vwap": (2648.5, 2649.0)},
            all_fields_compared=10,
            matching_fields=8,
        )

        summary = comparison.summary()

        assert "✗" in summary
        assert "2/10 fields differ" in summary
        assert "rsi" in summary
        assert "vwap" in summary


class TestSignalComparison:
    """Test SignalComparison dataclass."""

    def test_summary_for_no_signals(self):
        """Summary should show no signals."""
        comparison = SignalComparison(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            matches=True,
        )

        summary = comparison.summary()

        assert "✓" in summary
        assert "no signal" in summary

    def test_summary_for_matching_signals(self):
        """Summary should show matching signals."""
        from rule_engine.signal import Signal

        signal = Signal(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.2,
            confidence="A+",
            rationale="Test",
            factors={},
            validation_flags={},
            diagnostics={},
            htf_bias="bullish",
            symbol="GC",
            timeframe="1m",
            enforcer_tier="EarlyMild",
        )

        comparison = SignalComparison(
            timestamp=datetime(2024, 11, 6, 10, 30, tzinfo=UTC),
            matches=True,
            bt_signal=signal,
            ms_signal=signal,
        )

        summary = comparison.summary()

        assert "✓" in summary
        assert "VWAP_RECLAIM" in summary
        assert "A+" in summary
