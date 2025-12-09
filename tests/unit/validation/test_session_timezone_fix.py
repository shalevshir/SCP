"""Test session timezone alignment between entry and exit validation.

This test verifies that the session validator uses the correct timezone (ILT)
to prevent the timezone mismatch bug where trades enter after 13:00 ILT
(because entry validation uses London time) only to immediately exit with
session_close (because exit validation uses ILT).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from validation.config_loader import load_session_config
from validation.session_validator import SessionValidator


class TestSessionTimezoneAlignment:
    """Test that session validation uses ILT (Israel Local Time) per SOP."""

    def setup_method(self) -> None:
        """Initialize session validator for each test."""
        config = load_session_config()
        self.validator = SessionValidator(config)

    def test_session_blocks_after_13_00_ilt_winter(self) -> None:
        """Test that trading is blocked after 13:00 ILT in winter.

        This is the bug case: In winter (November), when DST is not active:
        - 13:05 ILT = 11:05 UTC (ILT is UTC+2 in winter)
        - 13:05 ILT = 13:05 London (same timezone in winter)

        Old behavior (Europe/London):
        - Entry validation allows at 13:05 London (within 10:00-13:00)
        - Exit validation blocks at 13:05 ILT
        - Result: Trade enters then immediately exits

        New behavior (Asia/Jerusalem):
        - Entry validation blocks at 13:05 ILT (outside 10:00-13:00)
        - Exit validation blocks at 13:05 ILT
        - Result: No trade entered
        """
        # November 7, 2025, 13:05 ILT (winter, no DST)
        # This is 11:05 UTC
        timestamp_utc = datetime(2025, 11, 7, 11, 5, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: outside 10:00-13:00 ILT window
        assert not result.session_ok, (
            "Trading should be blocked after 13:00 ILT. "
            "If this fails, the validator is still using London time instead of ILT."
        )
        assert result.reason == "outside_window"

    def test_session_allows_before_13_00_ilt_winter(self) -> None:
        """Test that trading is allowed before 13:00 ILT in winter."""
        # November 7, 2025, 12:55 ILT (winter, no DST)
        # This is 10:55 UTC
        timestamp_utc = datetime(2025, 11, 7, 10, 55, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: within 10:00-13:00 ILT window
        assert result.session_ok, "Trading should be allowed at 12:55 ILT"
        assert result.reason is None

    def test_session_blocks_before_10_00_ilt_winter(self) -> None:
        """Test that trading is blocked before 10:00 ILT in winter."""
        # November 7, 2025, 09:55 ILT (winter, no DST)
        # This is 07:55 UTC
        timestamp_utc = datetime(2025, 11, 7, 7, 55, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: before 10:00 ILT window
        assert not result.session_ok, "Trading should be blocked before 10:00 ILT"
        assert result.reason == "outside_window"

    def test_session_allows_at_10_00_ilt_winter(self) -> None:
        """Test that trading is allowed exactly at 10:00 ILT in winter."""
        # November 7, 2025, 10:00 ILT (winter, no DST)
        # This is 08:00 UTC
        timestamp_utc = datetime(2025, 11, 7, 8, 0, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: exactly at 10:00 ILT (start of window)
        assert result.session_ok, "Trading should be allowed at 10:00 ILT (window start)"
        assert result.reason is None

    def test_session_blocks_at_13_00_ilt_winter(self) -> None:
        """Test that trading is blocked exactly at 13:00 ILT in winter."""
        # November 7, 2025, 13:00 ILT (winter, no DST)
        # This is 11:00 UTC
        timestamp_utc = datetime(2025, 11, 7, 11, 0, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: at 13:00 ILT (end of window, exclusive)
        assert not result.session_ok, "Trading should be blocked at 13:00 ILT (window end)"
        assert result.reason == "outside_window"

    def test_session_allows_at_12_59_ilt_winter(self) -> None:
        """Test that trading is allowed at 12:59 ILT in winter."""
        # November 7, 2025, 12:59 ILT (winter, no DST)
        # This is 10:59 UTC
        timestamp_utc = datetime(2025, 11, 7, 10, 59, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: just before 13:00 ILT window end
        assert result.session_ok, "Trading should be allowed at 12:59 ILT"
        assert result.reason is None

    def test_real_trade_case_nov_7_11_12_utc(self) -> None:
        """Test the actual failing trade case from Nov 7.

        Trade d84c61fb entered at 2025-11-07T11:12:00+00:00 (UTC):
        - In London time: 11:12 (within 10:00-13:00) - entry allowed
        - In Israel time: 13:12 (past 13:00) - immediate session_close

        This test verifies the fix: entry should be blocked.
        """
        # The actual entry timestamp from the failing trade
        timestamp_utc = datetime(2025, 11, 7, 11, 12, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: 13:12 ILT is outside 10:00-13:00 window
        assert not result.session_ok, (
            "Trade at 11:12 UTC (13:12 ILT) should be blocked. "
            "This was the actual failing case from Nov 7 backtest."
        )
        assert result.reason == "outside_window"

    def test_session_dst_summer_alignment(self) -> None:
        """Test session validation during summer (DST active in Israel).

        In summer (June), Israel is UTC+3 (DST active):
        - 13:05 ILT = 10:05 UTC
        """
        # June 15, 2025, 13:05 ILT (summer, DST active)
        # This is 10:05 UTC
        timestamp_utc = datetime(2025, 6, 15, 10, 5, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: outside 10:00-13:00 ILT window
        assert not result.session_ok, "Trading should be blocked after 13:00 ILT in summer"
        assert result.reason == "outside_window"

    def test_session_dst_summer_within_window(self) -> None:
        """Test session validation within window during summer."""
        # June 15, 2025, 12:30 ILT (summer, DST active)
        # This is 09:30 UTC
        timestamp_utc = datetime(2025, 6, 15, 9, 30, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: within 10:00-13:00 ILT window
        assert result.session_ok, "Trading should be allowed at 12:30 ILT in summer"
        assert result.reason is None

