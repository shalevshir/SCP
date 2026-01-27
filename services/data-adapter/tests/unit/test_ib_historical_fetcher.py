"""Unit tests for IBHistoricalFetcher."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scp_shared.messaging.schemas import CandleMessage

from data_adapter.ib_historical_fetcher import IBHistoricalFetcher


class MockBarData:
    """Mock IB BarData."""

    def __init__(self, date, open, high, low, close, volume):
        self.date = date
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


@pytest.fixture
def fetcher():
    """Create IBHistoricalFetcher instance."""
    return IBHistoricalFetcher("127.0.0.1", 4002, 11)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_candles_basic(fetcher):
    """Test basic historical data fetch."""
    # Mock IB connection
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    mock_ib.reqHistoricalDataAsync = AsyncMock(
        return_value=[
            MockBarData(
                date=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
                open=2650.0,
                high=2652.0,
                low=2649.0,
                close=2651.0,
                volume=1000.0,
            ),
            MockBarData(
                date=datetime(2025, 1, 15, 10, 1, tzinfo=UTC),
                open=2651.0,
                high=2653.0,
                low=2650.0,
                close=2652.0,
                volume=1100.0,
            ),
        ]
    )
    fetcher._ib = mock_ib

    # Fetch candles
    candles = await fetcher.fetch_candles(
        symbol="GC",
        start=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
        end=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),
        timeframe="1m",
    )

    assert len(candles) == 2
    assert candles[0].symbol == "GC"
    assert candles[0].timeframe == "1m"
    assert candles[0].close == 2651.0
    assert candles[0].timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
    assert isinstance(candles[0], CandleMessage)
    assert candles[1].close == 2652.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_candles_dxy_symbol(fetcher):
    """Test that DXY symbol is correctly mapped to DX for IB."""
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    mock_ib.reqHistoricalDataAsync = AsyncMock(
        return_value=[
            MockBarData(
                date=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
                open=105.0,
                high=105.5,
                low=104.8,
                close=105.2,
                volume=500.0,
            ),
        ]
    )
    fetcher._ib = mock_ib

    # Fetch with DXY (internal symbol)
    candles = await fetcher.fetch_candles(
        symbol="DXY",
        start=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
        end=datetime(2025, 1, 15, 10, 1, tzinfo=UTC),
        timeframe="1m",
    )

    # Should create DX contract but return DXY symbol in candle
    assert len(candles) == 1
    assert candles[0].symbol == "DXY"


@pytest.mark.unit
def test_contract_creation_gc(fetcher):
    """Test GC contract creation."""
    contract = fetcher._create_contract("GC")

    assert contract.symbol == "GC"
    assert contract.secType == "FUT"
    assert contract.exchange == "COMEX"
    assert contract.currency == "USD"
    assert len(contract.lastTradeDateOrContractMonth) == 6  # YYYYMM format


@pytest.mark.unit
def test_contract_creation_dx(fetcher):
    """Test DX contract creation."""
    contract = fetcher._create_contract("DX")

    assert contract.symbol == "DX"
    assert contract.secType == "FUT"
    assert contract.exchange == "NYBOT"
    assert contract.currency == "USD"
    assert len(contract.lastTradeDateOrContractMonth) == 6  # YYYYMM format


@pytest.mark.unit
def test_contract_creation_invalid(fetcher):
    """Test invalid symbol raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported symbol"):
        fetcher._create_contract("INVALID")


@pytest.mark.unit
def test_front_month_calculation_gc(fetcher):
    """Test GC front month calculation (even months)."""
    # GC trades in even months: Feb, Apr, Jun, Aug, Oct, Dec
    with patch("data_adapter.ib_historical_fetcher.datetime") as mock_datetime:
        # Test January - should give next even month (Feb)
        mock_datetime.now.return_value = datetime(2025, 1, 15, tzinfo=UTC)
        front_month = fetcher._get_front_month("GC")
        assert front_month == "202502"

        # Test February - should give next even month (Apr)
        mock_datetime.now.return_value = datetime(2025, 2, 15, tzinfo=UTC)
        front_month = fetcher._get_front_month("GC")
        assert front_month == "202504"

        # Test November - should give next even month (Dec)
        mock_datetime.now.return_value = datetime(2025, 11, 15, tzinfo=UTC)
        front_month = fetcher._get_front_month("GC")
        assert front_month == "202512"

        # Test December - should rollover to next year (Feb)
        mock_datetime.now.return_value = datetime(2025, 12, 15, tzinfo=UTC)
        front_month = fetcher._get_front_month("GC")
        assert front_month == "202602"


@pytest.mark.unit
def test_front_month_calculation_dx(fetcher):
    """Test DX front month calculation (quarterly)."""
    # DX trades in Mar, Jun, Sep, Dec
    with patch("data_adapter.ib_historical_fetcher.datetime") as mock_datetime:
        # Test January - should give Mar
        mock_datetime.now.return_value = datetime(2025, 1, 15, tzinfo=UTC)
        front_month = fetcher._get_front_month("DX")
        assert front_month == "202503"

        # Test April - should give Jun
        mock_datetime.now.return_value = datetime(2025, 4, 15, tzinfo=UTC)
        front_month = fetcher._get_front_month("DX")
        assert front_month == "202506"

        # Test October - should give Dec
        mock_datetime.now.return_value = datetime(2025, 10, 15, tzinfo=UTC)
        front_month = fetcher._get_front_month("DX")
        assert front_month == "202512"

        # Test December - should rollover to next year (Mar)
        mock_datetime.now.return_value = datetime(2025, 12, 15, tzinfo=UTC)
        front_month = fetcher._get_front_month("DX")
        assert front_month == "202603"


@pytest.mark.unit
def test_front_month_invalid_symbol(fetcher):
    """Test invalid symbol in front month calculation."""
    with pytest.raises(ValueError, match="Unsupported symbol"):
        fetcher._get_front_month("INVALID")


@pytest.mark.unit
def test_timeframe_mapping(fetcher):
    """Test timeframe to IB bar size mapping."""
    assert fetcher._map_timeframe_to_bar_size("1m") == "1 min"
    assert fetcher._map_timeframe_to_bar_size("5m") == "5 mins"
    assert fetcher._map_timeframe_to_bar_size("15m") == "15 mins"
    assert fetcher._map_timeframe_to_bar_size("1h") == "1 hour"
    assert fetcher._map_timeframe_to_bar_size("1d") == "1 day"

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        fetcher._map_timeframe_to_bar_size("2m")


@pytest.mark.unit
def test_duration_calculation(fetcher):
    """Test IB duration string calculation."""
    # 4 hours (14400 seconds)
    start = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=UTC)
    assert fetcher._calculate_duration(start, end) == "14400 S"

    # 1 hour (3600 seconds)
    start = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
    end = datetime(2025, 1, 15, 11, 0, tzinfo=UTC)
    assert fetcher._calculate_duration(start, end) == "3600 S"

    # 5 days
    start = datetime(2025, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 15, 0, 0, tzinfo=UTC)
    assert fetcher._calculate_duration(start, end) == "5 D"

    # 2.5 days should round up to 3 days
    start = datetime(2025, 1, 10, 0, 0, tzinfo=UTC)
    end = datetime(2025, 1, 12, 12, 0, tzinfo=UTC)
    assert fetcher._calculate_duration(start, end) == "3 D"

    # Less than 1 hour (1800 seconds = 30 minutes)
    start = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
    end = datetime(2025, 1, 15, 10, 30, tzinfo=UTC)
    assert fetcher._calculate_duration(start, end) == "1800 S"


@pytest.mark.unit
def test_bar_to_candle_conversion(fetcher):
    """Test IB BarData to CandleMessage conversion."""
    bar = MockBarData(
        date=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
        open=2650.5,
        high=2652.0,
        low=2649.0,
        close=2651.5,
        volume=1234.0,
    )

    candle = fetcher._bar_to_candle_message(bar, "GC", "1m")

    assert isinstance(candle, CandleMessage)
    assert candle.timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
    assert candle.symbol == "GC"
    assert candle.timeframe == "1m"
    assert candle.open == 2650.5
    assert candle.high == 2652.0
    assert candle.low == 2649.0
    assert candle.close == 2651.5
    assert candle.volume == 1234.0


@pytest.mark.unit
def test_bar_to_candle_timezone_handling(fetcher):
    """Test timezone normalization in bar conversion."""
    # Test naive datetime (should add UTC)
    bar_naive = MockBarData(
        date=datetime(2025, 1, 15, 10, 0),  # No timezone
        open=2650.0,
        high=2652.0,
        low=2649.0,
        close=2651.0,
        volume=1000.0,
    )
    candle = fetcher._bar_to_candle_message(bar_naive, "GC", "1m")
    assert candle.timestamp.tzinfo == UTC

    # Test timezone-aware datetime (should convert to UTC)
    bar_aware = MockBarData(
        date=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
        open=2650.0,
        high=2652.0,
        low=2649.0,
        close=2651.0,
        volume=1000.0,
    )
    candle = fetcher._bar_to_candle_message(bar_aware, "GC", "1m")
    assert candle.timestamp.tzinfo == UTC


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limiting(fetcher):
    """Test rate limit checking."""
    # Simulate 60 requests in the last 10 minutes
    now = datetime.now(UTC)
    for i in range(60):
        fetcher._request_timestamps.append(now - timedelta(seconds=i))

    # This should trigger a wait
    with patch("data_adapter.ib_historical_fetcher.asyncio.sleep") as mock_sleep:
        await fetcher._check_rate_limit()
        # Should have called sleep with some positive value
        assert mock_sleep.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limiting_no_wait(fetcher):
    """Test rate limit allows requests when under limit."""
    # Simulate 59 requests (under limit)
    now = datetime.now(UTC)
    for i in range(59):
        fetcher._request_timestamps.append(now - timedelta(seconds=i))

    # This should NOT trigger a wait
    with patch("data_adapter.ib_historical_fetcher.asyncio.sleep") as mock_sleep:
        await fetcher._check_rate_limit()
        # Should not have called sleep
        assert not mock_sleep.called


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limiting_old_requests_expire(fetcher):
    """Test that old requests expire from rate limit tracking."""
    # Add a request from 11 minutes ago (should be expired)
    fetcher._request_timestamps.append(datetime.now(UTC) - timedelta(minutes=11))

    # This should NOT trigger a wait (old request expired)
    with patch("data_adapter.ib_historical_fetcher.asyncio.sleep") as mock_sleep:
        await fetcher._check_rate_limit()
        assert not mock_sleep.called

    # Should have removed the old request
    assert len(fetcher._request_timestamps) == 1  # Only the new one added


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_retry(fetcher):
    """Test connection retry with exponential backoff."""
    mock_ib_instance = MagicMock()

    # Simulate connection failure on first 2 attempts, success on 3rd
    call_count = 0

    async def mock_connect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Connection failed")

    mock_ib_instance.connectAsync = mock_connect
    mock_ib_instance.reqMarketDataType = MagicMock()
    mock_ib_instance.isConnected.return_value = False

    with patch("data_adapter.ib_historical_fetcher.IB", return_value=mock_ib_instance):
        with patch("data_adapter.ib_historical_fetcher.asyncio.sleep") as mock_sleep:
            await fetcher._ensure_connected()

            # Should have retried 2 times (3 total attempts)
            assert call_count == 3
            # Should have slept twice with exponential backoff (1s, 2s)
            assert mock_sleep.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_retry_disconnects_on_market_data_error(fetcher):
    """Test that a connected IB instance is disconnected on setup failure."""
    first_ib = MagicMock()
    first_ib.connectAsync = AsyncMock()
    first_ib.reqMarketDataType = MagicMock(
        side_effect=Exception("Market data type failed")
    )
    first_ib.isConnected.return_value = True

    second_ib = MagicMock()
    second_ib.connectAsync = AsyncMock()
    second_ib.reqMarketDataType = MagicMock()
    second_ib.isConnected.return_value = True

    with patch(
        "data_adapter.ib_historical_fetcher.IB",
        side_effect=[first_ib, second_ib],
    ):
        with patch("data_adapter.ib_historical_fetcher.asyncio.sleep") as mock_sleep:
            await fetcher._ensure_connected()

    first_ib.disconnect.assert_called_once()
    assert mock_sleep.call_count == 1
    assert fetcher._ib is second_ib


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_failure_max_retries(fetcher):
    """Test connection failure after max retries."""
    mock_ib_instance = MagicMock()
    mock_ib_instance.connectAsync = AsyncMock(
        side_effect=Exception("Connection failed")
    )
    mock_ib_instance.isConnected.return_value = False

    with patch("data_adapter.ib_historical_fetcher.IB", return_value=mock_ib_instance):
        with patch("data_adapter.ib_historical_fetcher.asyncio.sleep"):
            with pytest.raises(ConnectionError, match="Failed to connect"):
                await fetcher._ensure_connected()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_empty_result(fetcher):
    """Test handling when IB returns no data."""
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    mock_ib.reqHistoricalDataAsync = AsyncMock(return_value=[])  # Empty list
    fetcher._ib = mock_ib

    candles = await fetcher.fetch_candles(
        symbol="GC",
        start=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
        end=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),
        timeframe="1m",
    )

    assert candles == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_error_handling(fetcher):
    """Test error handling returns empty list."""
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    mock_ib.reqHistoricalDataAsync = AsyncMock(
        side_effect=Exception("IB API error")
    )
    fetcher._ib = mock_ib

    # Should return empty list, not raise exception
    candles = await fetcher.fetch_candles(
        symbol="GC",
        start=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
        end=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),
        timeframe="1m",
    )

    assert candles == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_invalid_symbol_raises(fetcher):
    """Test that invalid symbol raises ValueError."""
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    fetcher._ib = mock_ib

    with pytest.raises(ValueError, match="Unsupported symbol"):
        await fetcher.fetch_candles(
            symbol="INVALID",
            start=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            end=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),
            timeframe="1m",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_invalid_timeframe_raises(fetcher):
    """Test that invalid timeframe raises ValueError."""
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    fetcher._ib = mock_ib

    with pytest.raises(ValueError, match="Unsupported timeframe"):
        await fetcher.fetch_candles(
            symbol="GC",
            start=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
            end=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),
            timeframe="3m",  # Invalid
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_connection(fetcher):
    """Test closing IB connection."""
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    fetcher._ib = mock_ib

    await fetcher.close()

    mock_ib.disconnect.assert_called_once()
    assert fetcher._ib is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_close_when_not_connected(fetcher):
    """Test closing when not connected does nothing."""
    fetcher._ib = None
    await fetcher.close()  # Should not raise


@pytest.mark.unit
@pytest.mark.asyncio
async def test_filter_candles_to_exact_range(fetcher):
    """Test that candles are filtered to exact start/end range."""
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True
    mock_ib.reqHistoricalDataAsync = AsyncMock(
        return_value=[
            # IB may return extra bars outside requested range
            MockBarData(
                date=datetime(2025, 1, 15, 9, 59, tzinfo=UTC),  # Before start
                open=2650.0,
                high=2652.0,
                low=2649.0,
                close=2651.0,
                volume=1000.0,
            ),
            MockBarData(
                date=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),  # In range
                open=2651.0,
                high=2653.0,
                low=2650.0,
                close=2652.0,
                volume=1100.0,
            ),
            MockBarData(
                date=datetime(2025, 1, 15, 10, 1, tzinfo=UTC),  # In range
                open=2652.0,
                high=2654.0,
                low=2651.0,
                close=2653.0,
                volume=1200.0,
            ),
            MockBarData(
                date=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),  # At end (excluded)
                open=2653.0,
                high=2655.0,
                low=2652.0,
                close=2654.0,
                volume=1300.0,
            ),
        ]
    )
    fetcher._ib = mock_ib

    candles = await fetcher.fetch_candles(
        symbol="GC",
        start=datetime(2025, 1, 15, 10, 0, tzinfo=UTC),
        end=datetime(2025, 1, 15, 10, 2, tzinfo=UTC),  # Exclusive
        timeframe="1m",
    )

    # Should only include 10:00 and 10:01 (not 9:59 or 10:02)
    assert len(candles) == 2
    assert candles[0].timestamp == datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
    assert candles[1].timestamp == datetime(2025, 1, 15, 10, 1, tzinfo=UTC)


# Integration test (manual, requires IB Gateway running)
@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("IB_GATEWAY_RUNNING"), reason="IB Gateway not running"
)
@pytest.mark.asyncio
async def test_fetch_historical_live():
    """Integration test with real IB Gateway (requires IB connection)."""
    fetcher = IBHistoricalFetcher("127.0.0.1", 4002, 11)

    try:
        candles = await fetcher.fetch_candles(
            symbol="GC",
            start=datetime.now(UTC) - timedelta(hours=4),
            end=datetime.now(UTC),
            timeframe="1m",
        )

        # Should get approximately 240 candles (4 hours * 60 minutes)
        # May be less due to market hours
        assert len(candles) > 0
        assert all(isinstance(c, CandleMessage) for c in candles)
        assert all(c.symbol == "GC" for c in candles)
        assert all(c.timeframe == "1m" for c in candles)

    finally:
        await fetcher.close()
