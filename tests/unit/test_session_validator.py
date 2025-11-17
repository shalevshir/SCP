"""Unit tests for the time-based session validator."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from validation.session_validator import (
    SeasonRule,
    SessionConfig,
    SessionResult,
    SessionValidator,
)


@pytest.fixture()
def base_rules() -> tuple[SeasonRule, list[SeasonRule]]:
    """Provide default and seasonal rules matching SOP directives."""

    default_rule = SeasonRule(
        name="Default",
        months=frozenset({1, 2, 3, 4, 5, 6, 7, 8}),
        window_start=time(10, 0),
        window_end=time(13, 0),
        allowed_tiers=frozenset({"Conservative", "Early Mild", "Mild", "Offensive"}),
        allowed_setups=frozenset({"continuation"}),
        min_score=8.0,
        max_losses=2,
        dxy_correlation_max=-0.6,
    )

    september_rule = SeasonRule(
        name="September Defensive",
        months=frozenset({9}),
        window_start=time(11, 0),
        window_end=time(12, 30),
        allowed_tiers=frozenset({"Conservative", "Early Mild"}),
        allowed_setups=frozenset({"continuation"}),
        min_score=8.5,
        max_losses=1,
        dxy_correlation_max=-0.7,
    )

    october_rule = SeasonRule(
        name="October Base",
        months=frozenset({10}),
        window_start=time(10, 0),
        window_end=time(13, 0),
        allowed_tiers=frozenset({"Conservative", "Early Mild", "Mild"}),
        allowed_setups=frozenset({"continuation"}),
        min_score=8.0,
        max_losses=2,
        dxy_correlation_max=-0.6,
    )

    trend_rule = SeasonRule(
        name="Trend Season",
        months=frozenset({11, 12}),
        window_start=time(9, 30),
        window_end=time(14, 0),
        allowed_tiers=frozenset({"Conservative", "Early Mild", "Mild", "Offensive"}),
        allowed_setups=frozenset({"continuation", "fade"}),
        min_score=8.0,
        max_losses=2,
        dxy_correlation_max=-0.55,
    )

    return default_rule, [september_rule, october_rule, trend_rule]


@pytest.fixture()
def session_config(base_rules: tuple[SeasonRule, list[SeasonRule]]) -> SessionConfig:
    default_rule, seasons = base_rules
    return SessionConfig(
        timezone="Asia/Jerusalem",
        default_rule=default_rule,
        seasons=tuple(seasons),
        holidays=frozenset({date(2025, 9, 16)}),
    )


def _utc(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """Helper to create a UTC datetime."""

    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestSessionValidator:
    """Tests covering session validation logic and logging."""

    def test_default_window_allows_time_within_range(
        self, session_config: SessionConfig
    ) -> None:
        validator = SessionValidator(session_config)
        ts = _utc(2025, 8, 15, 7, 30)  # 10:30 ILT

        result = validator.evaluate(ts)

        assert isinstance(result, SessionResult)
        assert result.session_ok is True
        assert result.constraints.window_start == time(10, 0)
        assert result.constraints.window_end == time(13, 0)

    def test_default_window_blocks_time_before_start(
        self, session_config: SessionConfig
    ) -> None:
        validator = SessionValidator(session_config)
        ts = _utc(2025, 8, 15, 6, 59)  # 09:59 ILT

        result = validator.evaluate(ts)

        assert result.session_ok is False
        assert result.reason == "outside_window"

    def test_september_defensive_window(self, session_config: SessionConfig) -> None:
        validator = SessionValidator(session_config)

        allowed = validator.evaluate(_utc(2025, 9, 10, 8, 30))  # 11:30 ILT
        # 10:30 ILT (before window)
        blocked = validator.evaluate(_utc(2025, 9, 10, 7, 30))

        assert allowed.session_ok is True
        assert allowed.constraints.window_start == time(11, 0)
        assert allowed.constraints.allowed_tiers == frozenset(
            {"Conservative", "Early Mild"}
        )

        assert blocked.session_ok is False
        assert blocked.constraints.window_start == time(11, 0)
        assert blocked.reason == "outside_window"

    def test_trend_month_expanded_window(self, session_config: SessionConfig) -> None:
        validator = SessionValidator(session_config)
        ts = _utc(2025, 11, 20, 7, 0)  # 09:00 ILT (before window)
        ts_allowed = _utc(2025, 11, 20, 7, 15)  # 09:15 ILT (still before)
        ts_open = _utc(2025, 11, 20, 7, 30)  # 09:30 ILT (window start)
        ts_close = _utc(2025, 11, 20, 12, 59)  # 14:59 ILT (after window)

        assert validator.evaluate(ts).session_ok is False
        assert validator.evaluate(ts_allowed).session_ok is False

        start_result = validator.evaluate(ts_open)
        assert start_result.session_ok is True
        assert start_result.constraints.window_start == time(9, 30)
        assert start_result.constraints.allowed_setups == frozenset(
            {"continuation", "fade"}
        )

        end_result = validator.evaluate(ts_close)
        assert end_result.session_ok is False
        assert end_result.reason == "outside_window"

    def test_holiday_blocks_session(self, session_config: SessionConfig) -> None:
        validator = SessionValidator(session_config)
        ts = _utc(2025, 9, 16, 9, 0)  # During September window but on holiday

        result = validator.evaluate(ts)

        assert result.session_ok is False
        assert result.reason == "holiday"

    def test_timezone_conversion_from_non_utc(
        self, session_config: SessionConfig
    ) -> None:
        validator = SessionValidator(session_config)
        tz = ZoneInfo("Asia/Jerusalem")
        local_ts = datetime(2025, 12, 10, 12, 0, tzinfo=tz)  # Within trend window

        result = validator.evaluate(local_ts)

        assert result.session_ok is True
        assert result.constraints.name == "Trend Season"

    @patch("validation.session_validator.logger")
    def test_logging_for_allowed_session(
        self, mock_logger, session_config: SessionConfig
    ) -> None:
        validator = SessionValidator(session_config)
        ts = _utc(2025, 8, 15, 7, 30)

        validator.evaluate(ts)

        mock_logger.info.assert_called_once()
        log_msg = str(mock_logger.info.call_args)
        assert "Session status: allowed" in log_msg
        assert "Default" in log_msg

    @patch("validation.session_validator.logger")
    def test_logging_for_blocked_session(
        self, mock_logger, session_config: SessionConfig
    ) -> None:
        validator = SessionValidator(session_config)
        ts = _utc(2025, 8, 15, 6, 30)

        validator.evaluate(ts)

        mock_logger.warning.assert_called_once()
        log_msg = str(mock_logger.warning.call_args)
        assert "Session status: blocked" in log_msg
        assert "reason=outside_window" in log_msg
