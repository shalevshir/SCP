"""Unit tests for validation config_loader module."""

from datetime import date, time
from pathlib import Path
from unittest.mock import mock_open, patch
import tempfile
import os

import pytest
import yaml

from scp_shared.validation.config_loader import (
    load_session_config,
    load_dxy_handling_config,
    load_ceo_directive_config,
    _parse_time,
    _parse_date,
    _parse_season_rule,
)
from scp_shared.validation.session_validator import SeasonRule


class TestParseTime:
    """Tests for _parse_time function."""

    def test_parses_valid_time(self) -> None:
        """Parses valid HH:MM format."""
        result = _parse_time("10:30")
        assert result == time(10, 30)

    def test_parses_midnight(self) -> None:
        """Parses midnight correctly."""
        result = _parse_time("00:00")
        assert result == time(0, 0)

    def test_parses_end_of_day(self) -> None:
        """Parses end of day correctly."""
        result = _parse_time("23:59")
        assert result == time(23, 59)

    def test_raises_on_invalid_format(self) -> None:
        """Raises ValueError on invalid format."""
        with pytest.raises(ValueError, match="Invalid time format"):
            _parse_time("invalid")

    def test_raises_on_missing_colon(self) -> None:
        """Raises ValueError when colon is missing."""
        with pytest.raises(ValueError, match="Invalid time format"):
            _parse_time("1030")

    def test_raises_on_invalid_hour(self) -> None:
        """Raises ValueError on invalid hour."""
        with pytest.raises(ValueError, match="Invalid time format"):
            _parse_time("25:00")


class TestParseDate:
    """Tests for _parse_date function."""

    def test_parses_valid_date(self) -> None:
        """Parses valid YYYY-MM-DD format."""
        result = _parse_date("2024-12-25")
        assert result == date(2024, 12, 25)

    def test_parses_leap_year(self) -> None:
        """Parses leap year date correctly."""
        result = _parse_date("2024-02-29")
        assert result == date(2024, 2, 29)

    def test_raises_on_invalid_format(self) -> None:
        """Raises ValueError on invalid format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            _parse_date("invalid")

    def test_raises_on_invalid_date(self) -> None:
        """Raises ValueError on invalid date values."""
        with pytest.raises(ValueError, match="Invalid date format"):
            _parse_date("2024-13-01")  # Invalid month


class TestParseSeasonRule:
    """Tests for _parse_season_rule function."""

    def test_parses_complete_rule(self) -> None:
        """Parses a complete season rule."""
        rule_data = {
            "name": "Summer",
            "months": [6, 7, 8],
            "window_start": "09:00",
            "window_end": "14:00",
            "allowed_tiers": ["A", "B"],
            "allowed_setups": ["VWAP_RECLAIM"],
            "min_score": 7.5,
            "max_losses": 3,
            "dxy_correlation_max": -0.5,
        }
        
        result = _parse_season_rule(rule_data)
        
        assert result.name == "Summer"
        assert result.months == frozenset([6, 7, 8])
        assert result.window_start == time(9, 0)
        assert result.window_end == time(14, 0)
        assert result.allowed_tiers == frozenset(["A", "B"])
        assert result.allowed_setups == frozenset(["VWAP_RECLAIM"])
        assert result.min_score == 7.5
        assert result.max_losses == 3
        assert result.dxy_correlation_max == -0.5

    def test_uses_defaults_for_missing_fields(self) -> None:
        """Uses default values for missing fields."""
        rule_data = {}
        
        result = _parse_season_rule(rule_data)
        
        assert result.name == "Unnamed"
        assert result.months == frozenset()
        assert result.window_start == time(10, 0)
        assert result.window_end == time(13, 0)
        assert result.min_score == 8.0
        assert result.max_losses == 2
        assert result.dxy_correlation_max == -0.6

    def test_overrides_name(self) -> None:
        """Overrides name with parameter."""
        rule_data = {"name": "Original"}
        
        result = _parse_season_rule(rule_data, name="Override")
        
        assert result.name == "Override"

    def test_overrides_months(self) -> None:
        """Overrides months with parameter."""
        rule_data = {"months": [1, 2]}
        
        result = _parse_season_rule(rule_data, months=[3, 4, 5])
        
        assert result.months == frozenset([3, 4, 5])


class TestLoadSessionConfig:
    """Tests for load_session_config function."""

    def test_loads_config_from_file(self, tmp_path: Path) -> None:
        """Loads config from YAML file."""
        config_data = {
            "timezone": "America/New_York",
            "default_session": {
                "window_start": "09:30",
                "window_end": "16:00",
                "min_score": 7.0,
            },
            "seasons": [
                {
                    "name": "Winter",
                    "months": [12, 1, 2],
                    "window_start": "10:00",
                    "window_end": "15:00",
                }
            ],
            "holidays": ["2024-12-25", "2024-01-01"],
        }
        
        config_file = tmp_path / "validation.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        result = load_session_config(str(config_file))
        
        assert result.timezone == "America/New_York"
        assert result.default_rule.window_start == time(9, 30)
        assert len(result.seasons) == 1
        assert result.seasons[0].name == "Winter"
        assert len(result.holidays) == 2

    def test_raises_file_not_found(self) -> None:
        """Raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="Validation config not found"):
            load_session_config("/nonexistent/path.yaml")

    def test_uses_default_values(self, tmp_path: Path) -> None:
        """Uses default values when fields are missing."""
        config_data = {}
        
        config_file = tmp_path / "validation.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        result = load_session_config(str(config_file))
        
        assert result.timezone == "Europe/London"
        assert result.default_rule.months == frozenset(range(1, 13))
        assert len(result.seasons) == 0
        assert len(result.holidays) == 0


class TestLoadDxyHandlingConfig:
    """Tests for load_dxy_handling_config function."""

    def test_loads_dxy_handling(self, tmp_path: Path) -> None:
        """Loads DXY handling configuration."""
        config_data = {
            "dxy_handling": {
                "on_missing": {
                    "VWAP_RECLAIM": "skip",
                    "DXY_CONTINUATION": "block",
                }
            }
        }
        
        config_file = tmp_path / "validation.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        result = load_dxy_handling_config(str(config_file))
        
        assert result == {
            "VWAP_RECLAIM": "skip",
            "DXY_CONTINUATION": "block",
        }

    def test_returns_empty_dict_when_missing(self, tmp_path: Path) -> None:
        """Returns empty dict when dxy_handling is missing."""
        config_data = {}
        
        config_file = tmp_path / "validation.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        result = load_dxy_handling_config(str(config_file))
        
        assert result == {}


class TestLoadCeoDirectiveConfig:
    """Tests for load_ceo_directive_config function."""

    def test_loads_ceo_directive(self, tmp_path: Path) -> None:
        """Loads CEO directive configuration."""
        config_data = {
            "ceo_directive": {
                "override_file": "./config/custom.json",
                "early_mild_enabled": True,
                "daily_reset": False,
            }
        }
        
        config_file = tmp_path / "validation.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        result = load_ceo_directive_config(str(config_file))
        
        assert result == {
            "override_file": "./config/custom.json",
            "early_mild_enabled": True,
            "daily_reset": False,
        }

    def test_returns_defaults_when_missing(self, tmp_path: Path) -> None:
        """Returns default values when ceo_directive is missing."""
        config_data = {}
        
        config_file = tmp_path / "validation.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        result = load_ceo_directive_config(str(config_file))
        
        assert result == {
            "override_file": "./config/dev.local.json",
            "early_mild_enabled": False,
            "daily_reset": True,
        }
