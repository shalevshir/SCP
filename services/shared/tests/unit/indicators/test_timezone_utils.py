"""Unit tests for timezone utilities and VWAP session ID calculation."""

from datetime import datetime
from zoneinfo import ZoneInfo

from scp_shared.indicators.timezone_utils import (
    get_session_id_series,
    get_vwap_session_id,
)


class TestVWAPSessionID:
    """Test VWAP session ID calculation with 08:20 ET reset."""

    def test_before_reset_time(self) -> None:
        """Test that bars before 08:20 ET belong to previous day's session."""
        # 08:00 ET on Jan 15 should belong to Jan 14 session
        ts = datetime(2025, 1, 15, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2025, 1, 14).date()
        assert session_id == expected

    def test_at_reset_time(self) -> None:
        """Test that bar exactly at 08:20 ET starts new session."""
        # 08:20 ET on Jan 15 should start Jan 15 session
        ts = datetime(2025, 1, 15, 8, 20, 0, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2025, 1, 15).date()
        assert session_id == expected

    def test_after_reset_time(self) -> None:
        """Test that bars after 08:20 ET belong to current day's session."""
        # 10:00 ET on Jan 15 should belong to Jan 15 session
        ts = datetime(2025, 1, 15, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2025, 1, 15).date()
        assert session_id == expected

    def test_just_before_reset(self) -> None:
        """Test bar at 08:19:59 ET belongs to previous session."""
        # 08:19:59 ET on Jan 15 should belong to Jan 14 session
        ts = datetime(2025, 1, 15, 8, 19, 59, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2025, 1, 14).date()
        assert session_id == expected

    def test_just_after_reset(self) -> None:
        """Test bar at 08:20:01 ET starts new session."""
        # 08:20:01 ET on Jan 15 should start Jan 15 session
        ts = datetime(2025, 1, 15, 8, 20, 1, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2025, 1, 15).date()
        assert session_id == expected

    def test_utc_timestamp_conversion(self) -> None:
        """Test UTC timestamp is correctly converted to ET."""
        # 13:20 UTC = 08:20 ET (during EST)
        ts = datetime(2025, 1, 15, 13, 20, 0, tzinfo=ZoneInfo("UTC"))
        session_id = get_vwap_session_id(ts)

        # Should start Jan 15 session
        expected = datetime(2025, 1, 15).date()
        assert session_id == expected

    def test_utc_before_reset(self) -> None:
        """Test UTC timestamp before 08:20 ET."""
        # 13:00 UTC = 08:00 ET (during EST)
        ts = datetime(2025, 1, 15, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
        session_id = get_vwap_session_id(ts)

        # Should belong to Jan 14 session
        expected = datetime(2025, 1, 14).date()
        assert session_id == expected

    def test_timezone_naive_assumes_utc(self) -> None:
        """Test that timezone-naive timestamps are assumed to be UTC."""
        # 13:20 naive should be treated as UTC → 08:20 ET during EST
        ts = datetime(2025, 1, 15, 13, 20, 0)
        session_id = get_vwap_session_id(ts)

        # Should start Jan 15 session
        expected = datetime(2025, 1, 15).date()
        assert session_id == expected


class TestDSTTransitions:
    """Test VWAP session ID calculation across DST transitions."""

    def test_est_to_edt_spring_forward(self) -> None:
        """Test DST spring forward (EST → EDT).

        In 2025, DST starts on March 9 at 02:00 EST → 03:00 EDT.
        08:20 ET should work correctly on both sides of transition.
        """
        # Day before DST (March 8, 2025) - EST (UTC-5)
        # 13:20 UTC = 08:20 EST
        before_dst = datetime(2025, 3, 8, 13, 20, 0, tzinfo=ZoneInfo("UTC"))
        session_id_before = get_vwap_session_id(before_dst)
        assert session_id_before == datetime(2025, 3, 8).date()

        # Day after DST (March 10, 2025) - EDT (UTC-4)
        # 12:20 UTC = 08:20 EDT
        after_dst = datetime(2025, 3, 10, 12, 20, 0, tzinfo=ZoneInfo("UTC"))
        session_id_after = get_vwap_session_id(after_dst)
        assert session_id_after == datetime(2025, 3, 10).date()

    def test_edt_to_est_fall_back(self) -> None:
        """Test DST fall back (EDT → EST).

        In 2025, DST ends on November 2 at 02:00 EDT → 01:00 EST.
        08:20 ET should work correctly on both sides of transition.
        """
        # Day before DST ends (November 1, 2025) - EDT (UTC-4)
        # 12:20 UTC = 08:20 EDT
        before_dst = datetime(2025, 11, 1, 12, 20, 0, tzinfo=ZoneInfo("UTC"))
        session_id_before = get_vwap_session_id(before_dst)
        assert session_id_before == datetime(2025, 11, 1).date()

        # Day after DST ends (November 3, 2025) - EST (UTC-5)
        # 13:20 UTC = 08:20 EST
        after_dst = datetime(2025, 11, 3, 13, 20, 0, tzinfo=ZoneInfo("UTC"))
        session_id_after = get_vwap_session_id(after_dst)
        assert session_id_after == datetime(2025, 11, 3).date()

    def test_dst_transition_day_itself(self) -> None:
        """Test session ID on the actual DST transition day."""
        # March 9, 2025: DST starts at 02:00 EST → 03:00 EDT
        # 08:20 EDT on this day (12:20 UTC)
        dst_day = datetime(2025, 3, 9, 12, 20, 0, tzinfo=ZoneInfo("UTC"))
        session_id = get_vwap_session_id(dst_day)
        assert session_id == datetime(2025, 3, 9).date()


class TestSessionIDSeries:
    """Test batch session ID calculation for series of timestamps."""

    def test_series_with_single_session(self) -> None:
        """Test series of timestamps within single session."""
        # All after 08:20 ET on same day
        timestamps = [
            datetime(2025, 1, 15, 14, 0, tzinfo=ZoneInfo("UTC")),  # 09:00 ET
            datetime(2025, 1, 15, 15, 0, tzinfo=ZoneInfo("UTC")),  # 10:00 ET
            datetime(2025, 1, 15, 16, 0, tzinfo=ZoneInfo("UTC")),  # 11:00 ET
        ]

        session_ids = get_session_id_series(timestamps)

        # All should belong to Jan 15 session
        expected = datetime(2025, 1, 15).date()
        assert all(sid == expected for sid in session_ids)

    def test_series_crossing_reset_boundary(self) -> None:
        """Test series crossing 08:20 ET reset boundary."""
        timestamps = [
            datetime(
                2025, 1, 15, 13, 0, tzinfo=ZoneInfo("UTC")
            ),  # 08:00 ET - previous session
            datetime(
                2025, 1, 15, 13, 10, tzinfo=ZoneInfo("UTC")
            ),  # 08:10 ET - previous session
            datetime(
                2025, 1, 15, 13, 20, tzinfo=ZoneInfo("UTC")
            ),  # 08:20 ET - NEW session
            datetime(
                2025, 1, 15, 13, 30, tzinfo=ZoneInfo("UTC")
            ),  # 08:30 ET - new session
        ]

        session_ids = get_session_id_series(timestamps)

        # First two should be Jan 14 session
        assert session_ids[0] == datetime(2025, 1, 14).date()
        assert session_ids[1] == datetime(2025, 1, 14).date()

        # Last two should be Jan 15 session
        assert session_ids[2] == datetime(2025, 1, 15).date()
        assert session_ids[3] == datetime(2025, 1, 15).date()

    def test_series_multiple_days(self) -> None:
        """Test series spanning multiple days."""
        timestamps = [
            datetime(2025, 1, 15, 14, 0, tzinfo=ZoneInfo("UTC")),  # Jan 15 session
            datetime(2025, 1, 16, 14, 0, tzinfo=ZoneInfo("UTC")),  # Jan 16 session
            datetime(2025, 1, 17, 14, 0, tzinfo=ZoneInfo("UTC")),  # Jan 17 session
        ]

        session_ids = get_session_id_series(timestamps)

        assert session_ids[0] == datetime(2025, 1, 15).date()
        assert session_ids[1] == datetime(2025, 1, 16).date()
        assert session_ids[2] == datetime(2025, 1, 17).date()


class TestEdgeCases:
    """Test edge cases in session ID calculation."""

    def test_midnight_et(self) -> None:
        """Test midnight ET (between sessions)."""
        # 00:00 ET is before 08:20 ET, so belongs to previous day's session
        ts = datetime(2025, 1, 15, 0, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2025, 1, 14).date()
        assert session_id == expected

    def test_late_night_trading(self) -> None:
        """Test late night (23:00 ET) - still part of current day's session."""
        # 23:00 ET on Jan 15 is after 08:20 ET, so belongs to Jan 15 session
        ts = datetime(2025, 1, 15, 23, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2025, 1, 15).date()
        assert session_id == expected

    def test_early_morning_trading(self) -> None:
        """Test early morning (02:00 ET) - belongs to previous session."""
        # 02:00 ET on Jan 15 is before 08:20 ET, so belongs to Jan 14 session
        ts = datetime(2025, 1, 15, 2, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2025, 1, 14).date()
        assert session_id == expected

    def test_weekend_timestamps(self) -> None:
        """Test session ID calculation on weekend."""
        # Saturday 10:00 ET should still compute session ID correctly
        saturday = datetime(2025, 1, 18, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(saturday)

        # Should belong to Jan 18 session (even though markets are closed)
        expected = datetime(2025, 1, 18).date()
        assert session_id == expected

    def test_leap_year(self) -> None:
        """Test session ID calculation works correctly on Feb 29 (leap year 2024)."""
        # 2024 is a leap year
        ts = datetime(2024, 2, 29, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        session_id = get_vwap_session_id(ts)

        expected = datetime(2024, 2, 29).date()
        assert session_id == expected
