"""Tests for structure quality metrics (chop detection and clarity calculation).

Tests the helper functions that compute structure quality metrics used in
strict structure scoring.
"""

import pandas as pd
import pytest
from rule_engine.htf.calculator import (
    calculate_bars_since_event,
    calculate_structure_clarity,
    detect_structure_chop,
)


class TestDetectStructureChop:
    """Tests for chop detection based on mixed structure labels."""

    def test_all_bullish_labels_no_chop(self):
        """Test that all bullish labels (HH/HL) indicate no chop."""
        # Arrange
        labels = ["HH", "HL", "HH", "HL", "HH"]

        # Act
        chop = detect_structure_chop(labels, lookback=5)

        # Assert
        assert chop is False

    def test_all_bearish_labels_no_chop(self):
        """Test that all bearish labels (LH/LL) indicate no chop."""
        # Arrange
        labels = ["LH", "LL", "LH", "LL", "LH"]

        # Act
        chop = detect_structure_chop(labels, lookback=5)

        # Assert
        assert chop is False

    def test_mixed_labels_detect_chop(self):
        """Test that rapid alternations detect as chop (tolerant version)."""
        # Arrange: Rapid alternations (HH->LL->HH->LL)
        # With tolerant logic, needs 2+ consecutive alternations for chop
        labels = ["HH", "LL", "HH", "LL", "HH"]

        # Act
        chop = detect_structure_chop(labels, lookback=5)

        # Assert: Rapid alternations = chop
        assert chop is True

    def test_lookback_window_respects_recent_labels(self):
        """Test that lookback window only considers recent labels."""
        # Arrange: Old bearish, recent bullish (no chop in lookback)
        labels = ["LH", "LL", "LH", None, "HH", "HL", "HH", "HL"]

        # Act: Only look at last 4 labels
        chop = detect_structure_chop(labels, lookback=4)

        # Assert: Recent labels are all bullish, no chop
        assert chop is False

    def test_none_labels_are_filtered(self):
        """Test that None labels are filtered and alternations detected (tolerant version)."""
        # Arrange: Alternations with None values
        # After filtering: ["HH", "LL", "HH", "LL"] = 3 consecutive alternations
        labels = [None, "HH", "LL", None, "HH", "LL", None]

        # Act
        chop = detect_structure_chop(labels, lookback=10)

        # Assert: Rapid alternations after filtering Nones = chop
        assert chop is True

    def test_insufficient_labels_no_chop(self):
        """Test that < 2 valid labels cannot detect chop."""
        # Arrange: Only one label
        labels = ["HH"]

        # Act
        chop = detect_structure_chop(labels, lookback=10)

        # Assert: Need at least 2 labels
        assert chop is False

    def test_empty_list_no_chop(self):
        """Test that empty label list returns no chop."""
        # Arrange
        labels = []

        # Act
        chop = detect_structure_chop(labels, lookback=10)

        # Assert
        assert chop is False


class TestCalculateStructureClarity:
    """Tests for structure clarity calculation."""

    def test_all_bullish_perfect_clarity(self):
        """Test that all bullish labels give clarity = 1.0."""
        # Arrange
        labels = ["HH", "HL", "HH", "HL", "HH"]

        # Act
        clarity = calculate_structure_clarity(labels, lookback=5)

        # Assert: 100% bullish = clarity 1.0
        assert clarity == pytest.approx(1.0, abs=0.01)

    def test_all_bearish_perfect_clarity(self):
        """Test that all bearish labels give clarity = 1.0."""
        # Arrange
        labels = ["LH", "LL", "LH", "LL", "LH"]

        # Act
        clarity = calculate_structure_clarity(labels, lookback=5)

        # Assert: 100% bearish = clarity 1.0
        assert clarity == pytest.approx(1.0, abs=0.01)

    def test_50_50_mix_zero_clarity(self):
        """Test that 50/50 mix gives clarity = 0.0."""
        # Arrange: 3 bullish, 3 bearish
        labels = ["HH", "HL", "HH", "LH", "LL", "LH"]

        # Act
        clarity = calculate_structure_clarity(labels, lookback=10)

        # Assert: 50/50 = no clarity
        assert clarity == pytest.approx(0.0, abs=0.01)

    def test_60_40_mix_moderate_clarity(self):
        """Test that 60/40 mix gives clarity = 0.2."""
        # Arrange: 3 bullish, 2 bearish
        labels = ["HH", "HL", "HH", "LH", "LL"]

        # Act
        clarity = calculate_structure_clarity(labels, lookback=10)

        # Assert: 60/40 = abs(0.6 - 0.4) = 0.2
        assert clarity == pytest.approx(0.2, abs=0.01)

    def test_80_20_mix_high_clarity(self):
        """Test that 80/20 mix gives clarity = 0.6."""
        # Arrange: 4 bullish, 1 bearish
        labels = ["HH", "HL", "HH", "HL", "LH"]

        # Act
        clarity = calculate_structure_clarity(labels, lookback=10)

        # Assert: 80/20 = abs(0.8 - 0.2) = 0.6
        assert clarity == pytest.approx(0.6, abs=0.01)

    def test_none_labels_filtered_in_calculation(self):
        """Test that None labels don't affect clarity calculation."""
        # Arrange: All bullish with None values
        labels = [None, "HH", None, "HL", None, "HH", None]

        # Act
        clarity = calculate_structure_clarity(labels, lookback=10)

        # Assert: All valid labels are bullish = 1.0
        assert clarity == pytest.approx(1.0, abs=0.01)

    def test_lookback_window_limits_scope(self):
        """Test that lookback window limits which labels are considered."""
        # Arrange: Old bearish, recent bullish
        labels = ["LH", "LL", "LH", "LL", "HH", "HL", "HH", "HL"]

        # Act: Only look at last 4 labels
        clarity = calculate_structure_clarity(labels, lookback=4)

        # Assert: Recent 4 are all bullish = 1.0
        assert clarity == pytest.approx(1.0, abs=0.01)

    def test_empty_list_zero_clarity(self):
        """Test that empty label list returns 0 clarity."""
        # Arrange
        labels = []

        # Act
        clarity = calculate_structure_clarity(labels, lookback=10)

        # Assert
        assert clarity == 0.0


class TestCalculateBarsSinceEvent:
    """Tests for bars since event calculation."""

    def test_event_2_bars_ago(self):
        """Test calculating bars since event 2 bars ago."""
        # Arrange
        events = pd.Series([None, None, "BOS", None, None])
        events.index = pd.date_range("2025-01-01", periods=5, freq="1h")
        current_ts = events.index[-1]

        # Act
        bars_since = calculate_bars_since_event(events, current_ts)

        # Assert
        assert bars_since == 2

    def test_event_at_current_bar(self):
        """Test event at current bar returns 0."""
        # Arrange
        events = pd.Series([None, None, None, None, "BOS"])
        events.index = pd.date_range("2025-01-01", periods=5, freq="1h")
        current_ts = events.index[-1]

        # Act
        bars_since = calculate_bars_since_event(events, current_ts)

        # Assert
        assert bars_since == 0

    def test_no_events_returns_none(self):
        """Test that no events returns None."""
        # Arrange
        events = pd.Series([None, None, None, None, None])
        events.index = pd.date_range("2025-01-01", periods=5, freq="1h")
        current_ts = events.index[-1]

        # Act
        bars_since = calculate_bars_since_event(events, current_ts)

        # Assert
        assert bars_since is None

    def test_empty_series_returns_none(self):
        """Test that empty series returns None."""
        # Arrange
        events = pd.Series(dtype=object)

        # Act
        bars_since = calculate_bars_since_event(events, pd.Timestamp("2025-01-01"))

        # Assert
        assert bars_since is None

    def test_none_series_returns_none(self):
        """Test that None series returns None."""
        # Act
        bars_since = calculate_bars_since_event(None, pd.Timestamp("2025-01-01"))

        # Assert
        assert bars_since is None

    def test_multiple_events_uses_most_recent(self):
        """Test that multiple events use the most recent one."""
        # Arrange
        events = pd.Series(["BOS", None, "BOS", None, None])
        events.index = pd.date_range("2025-01-01", periods=5, freq="1h")
        current_ts = events.index[-1]

        # Act
        bars_since = calculate_bars_since_event(events, current_ts)

        # Assert: Most recent BOS is at index 2, current is index 4
        assert bars_since == 2
