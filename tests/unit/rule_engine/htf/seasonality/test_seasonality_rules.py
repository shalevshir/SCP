"""Tests for seasonality rules and period detection.

Tests the month-based HTF scoring modifiers from SOP.

Task: Add seasonality module
Epic: Full HTF Bias Engine Upgrade
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from rule_engine.htf.seasonality.rules import (
    SeasonalityPeriod,
    get_seasonality_config,
    get_seasonality_period,
)


class TestGetSeasonalityPeriod:
    """Tests for seasonality period detection from timestamps."""

    def test_september_returns_september_period(self) -> None:
        """September (month 9) should return 'september' period."""
        timestamp = datetime(2024, 9, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "september"

    def test_october_returns_october_period(self) -> None:
        """October (month 10) should return 'october' period."""
        timestamp = datetime(2024, 10, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "october"

    def test_november_returns_november_december_period(self) -> None:
        """November (month 11) should return 'november_december' period."""
        timestamp = datetime(2024, 11, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "november_december"

    def test_december_returns_november_december_period(self) -> None:
        """December (month 12) should return 'november_december' period."""
        timestamp = datetime(2024, 12, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "november_december"

    def test_january_returns_other_period(self) -> None:
        """January (month 1) should return 'other' period."""
        timestamp = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_february_returns_other_period(self) -> None:
        """February (month 2) should return 'other' period."""
        timestamp = datetime(2024, 2, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_march_returns_other_period(self) -> None:
        """March (month 3) should return 'other' period."""
        timestamp = datetime(2024, 3, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_april_returns_other_period(self) -> None:
        """April (month 4) should return 'other' period."""
        timestamp = datetime(2024, 4, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_may_returns_other_period(self) -> None:
        """May (month 5) should return 'other' period."""
        timestamp = datetime(2024, 5, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_june_returns_other_period(self) -> None:
        """June (month 6) should return 'other' period."""
        timestamp = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_july_returns_other_period(self) -> None:
        """July (month 7) should return 'other' period."""
        timestamp = datetime(2024, 7, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_august_returns_other_period(self) -> None:
        """August (month 8) should return 'other' period."""
        timestamp = datetime(2024, 8, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_first_day_of_september(self) -> None:
        """First day of September should return 'september' period."""
        timestamp = datetime(2024, 9, 1, 0, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "september"

    def test_last_day_of_september(self) -> None:
        """Last day of September should return 'september' period."""
        timestamp = datetime(2024, 9, 30, 23, 59, 59, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "september"

    def test_first_day_of_november(self) -> None:
        """First day of November should return 'november_december' period."""
        timestamp = datetime(2024, 11, 1, 0, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "november_december"

    def test_last_day_of_december(self) -> None:
        """Last day of December should return 'november_december' period."""
        timestamp = datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "november_december"

    def test_year_transition_december_to_january(self) -> None:
        """Test year boundary: December should be trend, January should be other."""
        dec_timestamp = datetime(2024, 12, 31, 23, 59, tzinfo=UTC)
        jan_timestamp = datetime(2025, 1, 1, 0, 1, tzinfo=UTC)

        assert get_seasonality_period(dec_timestamp) == "november_december"
        assert get_seasonality_period(jan_timestamp) == "other"

    def test_leap_year_february(self) -> None:
        """Test leap year February still returns 'other' period."""
        timestamp = datetime(2024, 2, 29, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == "other"

    def test_different_timezones_same_month(self) -> None:
        """Different timezones should resolve to same period if same month."""
        # Both timestamps are in September regardless of timezone
        utc_timestamp = datetime(2024, 9, 15, 12, 0, tzinfo=UTC)
        naive_timestamp = datetime(2024, 9, 15, 12, 0)  # No timezone

        assert get_seasonality_period(utc_timestamp) == "september"
        assert get_seasonality_period(naive_timestamp) == "september"

    def test_works_with_future_dates(self) -> None:
        """Should work correctly with future dates."""
        future_timestamp = datetime(2030, 11, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(future_timestamp)
        assert result == "november_december"

    def test_works_with_past_dates(self) -> None:
        """Should work correctly with past dates."""
        past_timestamp = datetime(2020, 9, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(past_timestamp)
        assert result == "september"


class TestGetSeasonalityConfig:
    """Tests for seasonality-specific configuration retrieval."""

    def test_september_config_returns_strict_thresholds(self) -> None:
        """September should return strictest thresholds (defensive mode)."""
        config = get_seasonality_config("september")

        assert config["min_score_threshold"] == 8.5
        assert config["dxy_corr_threshold"] == -0.65
        assert config["max_losses"] == 1
        assert "september" in config["description"].lower()

    def test_october_config_returns_baseline_thresholds(self) -> None:
        """October should return neutral baseline thresholds."""
        config = get_seasonality_config("october")

        assert config["min_score_threshold"] == 8.0
        assert config["dxy_corr_threshold"] == -0.6
        assert config["max_losses"] == 2
        assert "october" in config["description"].lower()

    def test_november_december_config_returns_relaxed_thresholds(self) -> None:
        """November-December should return relaxed thresholds (trend season)."""
        config = get_seasonality_config("november_december")

        assert config["min_score_threshold"] == 8.0
        assert config["dxy_corr_threshold"] == -0.55  # Most relaxed
        assert config["max_losses"] == 2
        assert (
            "trend" in config["description"].lower()
            or "november" in config["description"].lower()
        )

    def test_other_config_returns_standard_thresholds(self) -> None:
        """Other months should return standard baseline thresholds."""
        config = get_seasonality_config("other")

        assert config["min_score_threshold"] == 8.0
        assert config["dxy_corr_threshold"] == -0.6
        assert config["max_losses"] == 2
        assert (
            "standard" in config["description"].lower()
            or "other" in config["description"].lower()
        )

    def test_all_configs_have_required_keys(self) -> None:
        """All configs should contain required keys."""
        required_keys = {
            "min_score_threshold",
            "dxy_corr_threshold",
            "max_losses",
            "description",
        }

        for period in ["september", "october", "november_december", "other"]:
            config = get_seasonality_config(period)
            assert set(config.keys()) == required_keys

    def test_september_strictest_min_score(self) -> None:
        """September should have the highest minimum score threshold."""
        sep_config = get_seasonality_config("september")
        oct_config = get_seasonality_config("october")
        nov_config = get_seasonality_config("november_december")
        other_config = get_seasonality_config("other")

        sep_score = sep_config["min_score_threshold"]
        assert sep_score > oct_config["min_score_threshold"]
        assert sep_score > nov_config["min_score_threshold"]
        assert sep_score > other_config["min_score_threshold"]

    def test_september_strictest_max_losses(self) -> None:
        """September should have the lowest max losses (most conservative)."""
        sep_config = get_seasonality_config("september")
        oct_config = get_seasonality_config("october")
        nov_config = get_seasonality_config("november_december")
        other_config = get_seasonality_config("other")

        sep_losses = sep_config["max_losses"]
        assert sep_losses < oct_config["max_losses"]
        assert sep_losses < nov_config["max_losses"]
        assert sep_losses < other_config["max_losses"]

    def test_november_december_most_relaxed_dxy_correlation(self) -> None:
        """November-December should have the most relaxed (highest) DXY correlation threshold."""
        sep_config = get_seasonality_config("september")
        oct_config = get_seasonality_config("october")
        nov_config = get_seasonality_config("november_december")
        other_config = get_seasonality_config("other")

        nov_corr = nov_config["dxy_corr_threshold"]
        assert nov_corr > sep_config["dxy_corr_threshold"]
        assert nov_corr > oct_config["dxy_corr_threshold"]
        assert nov_corr > other_config["dxy_corr_threshold"]

    def test_october_and_other_have_same_thresholds(self) -> None:
        """October baseline and 'other' should have identical thresholds."""
        oct_config = get_seasonality_config("october")
        other_config = get_seasonality_config("other")

        assert oct_config["min_score_threshold"] == other_config["min_score_threshold"]
        assert oct_config["dxy_corr_threshold"] == other_config["dxy_corr_threshold"]
        assert oct_config["max_losses"] == other_config["max_losses"]


class TestSeasonalityIntegration:
    """Integration tests for full seasonality workflow."""

    def test_full_workflow_september(self) -> None:
        """Test full workflow: timestamp -> period -> config for September."""
        timestamp = datetime(2024, 9, 15, 12, 0, tzinfo=UTC)

        period = get_seasonality_period(timestamp)
        assert period == "september"

        config = get_seasonality_config(period)
        assert config["min_score_threshold"] == 8.5
        assert config["max_losses"] == 1

    def test_full_workflow_trend_season(self) -> None:
        """Test full workflow: timestamp -> period -> config for trend season."""
        timestamp = datetime(2024, 11, 15, 12, 0, tzinfo=UTC)

        period = get_seasonality_period(timestamp)
        assert period == "november_december"

        config = get_seasonality_config(period)
        assert config["dxy_corr_threshold"] == -0.55  # Most relaxed

    def test_full_workflow_standard_month(self) -> None:
        """Test full workflow: timestamp -> period -> config for standard month."""
        timestamp = datetime(2024, 3, 15, 12, 0, tzinfo=UTC)

        period = get_seasonality_period(timestamp)
        assert period == "other"

        config = get_seasonality_config(period)
        assert config["min_score_threshold"] == 8.0
        assert config["max_losses"] == 2

    @pytest.mark.parametrize(
        "month,expected_period",
        [
            (1, "other"),
            (2, "other"),
            (3, "other"),
            (4, "other"),
            (5, "other"),
            (6, "other"),
            (7, "other"),
            (8, "other"),
            (9, "september"),
            (10, "october"),
            (11, "november_december"),
            (12, "november_december"),
        ],
    )
    def test_all_months_parameterized(
        self, month: int, expected_period: SeasonalityPeriod
    ) -> None:
        """Parameterized test covering all 12 months."""
        timestamp = datetime(2024, month, 15, 12, 0, tzinfo=UTC)
        result = get_seasonality_period(timestamp)
        assert result == expected_period
