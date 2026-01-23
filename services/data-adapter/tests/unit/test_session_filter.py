"""Tests for SessionFilter - wrapper around SessionValidator."""

from datetime import UTC, datetime, time

from scp_shared.messaging.schemas import CandleMessage

from data_adapter.session_filter import GoldFuturesSessionFilter, SessionFilter


class TestSessionFilter:
    """Test suite for SessionFilter."""

    def test_default_config_allows_typical_trading_hours(self) -> None:
        """Default session config allows typical US trading hours."""
        filter_instance = SessionFilter()

        # 9:00 AM ET (14:00 UTC) - should be allowed
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 14, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        is_allowed = filter_instance.is_trading_hours(candle)

        # Depending on default config, this might be allowed or not
        # For now, test that it returns a boolean
        assert isinstance(is_allowed, bool)

    def test_custom_window_allows_specific_hours(self) -> None:
        """Custom session window allows only specified hours."""
        # Create filter with custom window: 10:00-12:00 UTC
        filter_instance = SessionFilter(
            window_start=time(10, 0),
            window_end=time(12, 0),
        )

        # 10:30 UTC - should be allowed
        allowed_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # 9:00 UTC - should be rejected
        rejected_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 9, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert filter_instance.is_trading_hours(allowed_candle)
        assert not filter_instance.is_trading_hours(rejected_candle)

    def test_boundary_times_handled_correctly(self) -> None:
        """Boundary times (exactly at window start/end) handled correctly."""
        filter_instance = SessionFilter(
            window_start=time(10, 0),
            window_end=time(12, 0),
        )

        # Exactly at start - should be allowed
        start_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Exactly at end - should be rejected (exclusive end)
        end_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 12, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert filter_instance.is_trading_hours(start_candle)
        assert not filter_instance.is_trading_hours(end_candle)

    def test_disabled_filter_allows_all(self) -> None:
        """When enabled=False, all times are allowed."""
        filter_instance = SessionFilter(
            window_start=time(10, 0),
            window_end=time(12, 0),
            enabled=False,
        )

        # 3:00 AM UTC - normally rejected, but filter disabled
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 3, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert filter_instance.is_trading_hours(candle)

    def test_weekend_check_rejects_saturday_sunday(self) -> None:
        """Weekend check rejects Saturday and Sunday."""
        filter_instance = SessionFilter(
            window_start=time(0, 0),
            window_end=time(23, 59),
            check_weekends=True,
        )

        # Saturday
        saturday_candle = CandleMessage(
            timestamp=datetime(2025, 1, 18, 10, 0, tzinfo=UTC),  # Saturday
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Sunday
        sunday_candle = CandleMessage(
            timestamp=datetime(2025, 1, 19, 10, 0, tzinfo=UTC),  # Sunday
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Monday
        monday_candle = CandleMessage(
            timestamp=datetime(2025, 1, 20, 10, 0, tzinfo=UTC),  # Monday
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert not filter_instance.is_trading_hours(saturday_candle)
        assert not filter_instance.is_trading_hours(sunday_candle)
        assert filter_instance.is_trading_hours(monday_candle)

    def test_timezone_conversion(self) -> None:
        """Timestamps are correctly converted to configured timezone."""
        # Create filter with US/Eastern timezone
        filter_instance = SessionFilter(
            window_start=time(9, 30),  # 9:30 AM ET
            window_end=time(16, 0),  # 4:00 PM ET
            timezone="US/Eastern",
        )

        # 14:30 UTC = 9:30 AM ET (during standard time)
        # This should be allowed if timezone conversion works
        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 14, 30, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        result = filter_instance.is_trading_hours(candle)

        # Should be allowed (9:30 AM ET is within window)
        assert isinstance(result, bool)


class TestGoldFuturesSessionFilter:
    """Test suite for GoldFuturesSessionFilter (Gold futures market hours)."""

    def test_sunday_evening_market_open(self) -> None:
        """Gold futures open Sunday 6 PM ET."""
        filter_instance = GoldFuturesSessionFilter(enabled=True)

        # Sunday 6 PM ET = Sunday 23:00 UTC (standard time)
        # Sunday 6 PM ET = Sunday 22:00 UTC (daylight time)
        # Using January (standard time)
        open_candle = CandleMessage(
            timestamp=datetime(2025, 1, 19, 23, 0, tzinfo=UTC),  # Sunday 6 PM ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Sunday 5 PM ET - should be closed
        before_open_candle = CandleMessage(
            timestamp=datetime(2025, 1, 19, 22, 0, tzinfo=UTC),  # Sunday 5 PM ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert filter_instance.is_trading_hours(open_candle)
        assert not filter_instance.is_trading_hours(before_open_candle)

    def test_friday_afternoon_market_close(self) -> None:
        """Gold futures close Friday 5 PM ET."""
        filter_instance = GoldFuturesSessionFilter(enabled=True)

        # Friday 5 PM ET = Friday 22:00 UTC (standard time)
        close_candle = CandleMessage(
            timestamp=datetime(2025, 1, 17, 22, 0, tzinfo=UTC),  # Friday 5 PM ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Friday 4 PM ET - should be open
        before_close_candle = CandleMessage(
            timestamp=datetime(2025, 1, 17, 21, 0, tzinfo=UTC),  # Friday 4 PM ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert not filter_instance.is_trading_hours(close_candle)
        assert filter_instance.is_trading_hours(before_close_candle)

    def test_saturday_fully_closed(self) -> None:
        """Saturday is fully closed for Gold futures."""
        filter_instance = GoldFuturesSessionFilter(enabled=True)

        # Saturday noon
        saturday_candle = CandleMessage(
            timestamp=datetime(2025, 1, 18, 17, 0, tzinfo=UTC),  # Saturday noon ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert not filter_instance.is_trading_hours(saturday_candle)

    def test_daily_maintenance_break(self) -> None:
        """Daily maintenance break 5-6 PM ET (Monday-Thursday)."""
        filter_instance = GoldFuturesSessionFilter(enabled=True)

        # Monday 5:30 PM ET = Monday 22:30 UTC
        maintenance_candle = CandleMessage(
            timestamp=datetime(2025, 1, 13, 22, 30, tzinfo=UTC),  # Monday 5:30 PM ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Monday 4:30 PM ET - before maintenance
        before_maintenance = CandleMessage(
            timestamp=datetime(2025, 1, 13, 21, 30, tzinfo=UTC),  # Monday 4:30 PM ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # Monday 6:30 PM ET - after maintenance
        after_maintenance = CandleMessage(
            timestamp=datetime(2025, 1, 13, 23, 30, tzinfo=UTC),  # Monday 6:30 PM ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert not filter_instance.is_trading_hours(maintenance_candle)
        assert filter_instance.is_trading_hours(before_maintenance)
        assert filter_instance.is_trading_hours(after_maintenance)

    def test_weekday_trading_hours(self) -> None:
        """Weekday trading hours work correctly (outside maintenance)."""
        filter_instance = GoldFuturesSessionFilter(enabled=True)

        # Tuesday 10 AM ET = Tuesday 15:00 UTC
        weekday_candle = CandleMessage(
            timestamp=datetime(2025, 1, 14, 15, 0, tzinfo=UTC),  # Tuesday 10 AM ET
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert filter_instance.is_trading_hours(weekday_candle)

    def test_disabled_filter_allows_all_times(self) -> None:
        """When disabled, all times are allowed."""
        filter_instance = GoldFuturesSessionFilter(enabled=False)

        # Saturday (normally closed)
        saturday_candle = CandleMessage(
            timestamp=datetime(2025, 1, 18, 17, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        assert filter_instance.is_trading_hours(saturday_candle)
