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

    def test_session_blocks_after_14_00_ilt_winter(self) -> None:
        """Test that trading is blocked after 14:00 ILT in winter.

        Window is now 09:00-14:00 ILT per updated config.
        """
        # November 7, 2025, 14:05 ILT (winter, no DST)
        # This is 12:05 UTC
        timestamp_utc = datetime(2025, 11, 7, 12, 5, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: outside 09:00-14:00 ILT window
        assert not result.session_ok, (
            "Trading should be blocked after 14:00 ILT. "
            "If this fails, the validator is still using London time instead of ILT."
        )
        assert result.reason == "outside_window"

    def test_session_allows_before_14_00_ilt_winter(self) -> None:
        """Test that trading is allowed before 14:00 ILT in winter."""
        # November 7, 2025, 13:55 ILT (winter, no DST)
        # This is 11:55 UTC
        timestamp_utc = datetime(2025, 11, 7, 11, 55, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: within 09:00-14:00 ILT window
        assert result.session_ok, "Trading should be allowed at 13:55 ILT"
        assert result.reason is None

    def test_session_blocks_before_09_00_ilt_winter(self) -> None:
        """Test that trading is blocked before 09:00 ILT in winter."""
        # November 7, 2025, 08:55 ILT (winter, no DST)
        # This is 06:55 UTC
        timestamp_utc = datetime(2025, 11, 7, 6, 55, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: before 09:00 ILT window
        assert not result.session_ok, "Trading should be blocked before 09:00 ILT"
        assert result.reason == "outside_window"

    def test_session_allows_at_09_00_ilt_winter(self) -> None:
        """Test that trading is allowed exactly at 09:00 ILT in winter."""
        # November 7, 2025, 09:00 ILT (winter, no DST)
        # This is 07:00 UTC
        timestamp_utc = datetime(2025, 11, 7, 7, 0, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: exactly at 09:00 ILT (start of window)
        assert result.session_ok, "Trading should be allowed at 09:00 ILT (window start)"
        assert result.reason is None

    def test_session_blocks_at_14_00_ilt_winter(self) -> None:
        """Test that trading is blocked exactly at 14:00 ILT in winter."""
        # November 7, 2025, 14:00 ILT (winter, no DST)
        # This is 12:00 UTC
        timestamp_utc = datetime(2025, 11, 7, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: at 14:00 ILT (end of window, exclusive)
        assert not result.session_ok, "Trading should be blocked at 14:00 ILT (window end)"
        assert result.reason == "outside_window"

    def test_session_allows_at_13_59_ilt_winter(self) -> None:
        """Test that trading is allowed at 13:59 ILT in winter."""
        # November 7, 2025, 13:59 ILT (winter, no DST)
        # This is 11:59 UTC
        timestamp_utc = datetime(2025, 11, 7, 11, 59, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: just before 14:00 ILT window end
        assert result.session_ok, "Trading should be allowed at 13:59 ILT"
        assert result.reason is None

    def test_real_trade_case_nov_7_11_12_utc(self) -> None:
        """Test the actual trade case from Nov 7.

        Trade d84c61fb entered at 2025-11-07T11:12:00+00:00 (UTC):
        - In Israel time: 13:12 ILT (within 09:00-14:00 window) - entry allowed

        With updated window (09:00-14:00), this trade should be allowed.
        """
        # The actual entry timestamp from the trade
        timestamp_utc = datetime(2025, 11, 7, 11, 12, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: 13:12 ILT is within 09:00-14:00 window
        assert result.session_ok, (
            "Trade at 11:12 UTC (13:12 ILT) should be allowed within 09:00-14:00 window. "
            "This was the actual case from Nov 7 backtest."
        )
        assert result.reason is None

    def test_session_dst_summer_alignment(self) -> None:
        """Test session validation during summer (DST active in Israel).

        In summer (June), Israel is UTC+3 (DST active):
        - 14:05 ILT = 11:05 UTC
        """
        # June 15, 2025, 14:05 ILT (summer, DST active)
        # This is 11:05 UTC
        timestamp_utc = datetime(2025, 6, 15, 11, 5, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be blocked: outside 09:00-14:00 ILT window
        assert not result.session_ok, "Trading should be blocked after 14:00 ILT in summer"
        assert result.reason == "outside_window"

    def test_session_dst_summer_within_window(self) -> None:
        """Test session validation within window during summer."""
        # June 15, 2025, 12:30 ILT (summer, DST active)
        # This is 09:30 UTC
        timestamp_utc = datetime(2025, 6, 15, 9, 30, 0, tzinfo=ZoneInfo("UTC"))

        result = self.validator.evaluate(timestamp_utc)

        # Should be allowed: within 09:00-14:00 ILT window
        assert result.session_ok, "Trading should be allowed at 12:30 ILT in summer"
        assert result.reason is None

