"""Unit tests for FeatureRepository."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage

from feature_engine_svc.repository import FeatureRepository


@pytest.fixture
def mock_db_pool() -> MagicMock:
    """Create mock database pool."""
    pool = MagicMock()
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    return pool


class TestFeatureRepositorySaveCandle:
    """Test save_candle method."""

    @pytest.mark.asyncio
    async def test_save_candle_executes_upsert(self, mock_db_pool: MagicMock) -> None:
        """Save candle executes upsert query."""
        repo = FeatureRepository(mock_db_pool)

        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )

        await repo.save_candle(candle)

        mock_db_pool.execute.assert_called_once()
        call_args = mock_db_pool.execute.call_args[0]
        assert "INSERT INTO candles" in call_args[0]
        assert "ON CONFLICT" in call_args[0]

    @pytest.mark.asyncio
    async def test_save_candle_passes_all_fields(self, mock_db_pool: MagicMock) -> None:
        """Save candle passes all OHLCV fields."""
        repo = FeatureRepository(mock_db_pool)

        candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=107.250,
            high=107.300,
            low=107.200,
            close=107.280,
            volume=500.0,
        )

        await repo.save_candle(candle)

        call_args = mock_db_pool.execute.call_args[0]
        # Check all values are passed
        assert call_args[1] == candle.timestamp
        assert call_args[2] == "DXY"
        assert call_args[3] == "1m"
        assert call_args[4] == 107.250  # open
        assert call_args[5] == 107.300  # high
        assert call_args[6] == 107.200  # low
        assert call_args[7] == 107.280  # close
        assert call_args[8] == 500.0  # volume

    @pytest.mark.asyncio
    async def test_save_candle_handles_both_symbols(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Save candle works for both GC and DXY."""
        repo = FeatureRepository(mock_db_pool)

        gc_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2655.0,
            low=2648.0,
            close=2652.0,
            volume=1000.0,
        )

        dxy_candle = CandleMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="DXY",
            timeframe="1m",
            open=107.250,
            high=107.300,
            low=107.200,
            close=107.280,
            volume=500.0,
        )

        await repo.save_candle(gc_candle)
        await repo.save_candle(dxy_candle)

        assert mock_db_pool.execute.call_count == 2


class TestFeatureRepositorySaveFeatures:
    """Test save_features method."""

    @pytest.mark.asyncio
    async def test_save_features_executes_upsert(self, mock_db_pool: MagicMock) -> None:
        """Save features executes upsert query."""
        repo = FeatureRepository(mock_db_pool)

        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            rsi=55.0,
            ema_9=2648.0,
            ema_20=2645.0,
            ema_50=2640.0,
            dxy_correlation=-0.75,
            structure_label="HH",
            vwap_deviation=0.5,
        )

        await repo.save_features(features)

        mock_db_pool.execute.assert_called_once()
        call_args = mock_db_pool.execute.call_args[0]
        assert "INSERT INTO features" in call_args[0]
        assert "ON CONFLICT" in call_args[0]

    @pytest.mark.asyncio
    async def test_save_features_passes_all_fields(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Save features passes all message fields."""
        repo = FeatureRepository(mock_db_pool)

        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2645.0,
            vwap_slope=0.15,  # Added vwap_slope field
            rsi=55.0,
            ema_9=2648.0,
            ema_20=2645.0,
            ema_50=2640.0,
            dxy_correlation=-0.75,
            structure_label="HH",
            vwap_deviation=0.5,
        )

        await repo.save_features(features)

        call_args = mock_db_pool.execute.call_args[0]
        # Check all values are passed (order: timestamp, symbol, timeframe, close, vwap, vwap_slope, rsi, ...)
        assert call_args[1] == features.timestamp
        assert call_args[2] == "GC"
        assert call_args[3] == "1m"
        assert call_args[4] == 2650.0  # close
        assert call_args[5] == 2645.0  # vwap
        assert call_args[6] == 0.15  # vwap_slope (NEW field after migration 007)
        assert call_args[7] == 55.0  # rsi

    @pytest.mark.asyncio
    async def test_save_features_handles_none_values(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Save features handles None values."""
        repo = FeatureRepository(mock_db_pool)

        features = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=None,  # None
            rsi=None,  # None
        )

        await repo.save_features(features)

        call_args = mock_db_pool.execute.call_args[0]
        assert call_args[5] is None  # vwap
        assert call_args[6] is None  # rsi


class TestFeatureRepositoryLoadRecentCandles:
    """Test load_recent_candles method."""

    @pytest.mark.asyncio
    async def test_load_recent_candles_returns_empty_when_no_data(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Load recent candles returns empty list when no data."""
        mock_db_pool.fetch = AsyncMock(return_value=[])

        repo = FeatureRepository(mock_db_pool)
        result = await repo.load_recent_candles(
            symbol="GC",
            timeframe="1m",
            count=60,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_load_recent_candles_pairs_by_timestamp(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Load recent candles pairs GC and DXY by timestamp."""
        ts = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)

        # First call for GC, second for DXY
        mock_db_pool.fetch = AsyncMock(
            side_effect=[
                # GC candles
                [
                    {
                        "timestamp": ts,
                        "open": 2650.0,
                        "high": 2655.0,
                        "low": 2648.0,
                        "close": 2654.0,
                        "volume": 1000.0,
                    },
                ],
                # DXY candles
                [
                    {
                        "timestamp": ts,
                        "open": 103.5,
                        "high": 103.7,
                        "low": 103.4,
                        "close": 103.6,
                        "volume": 500.0,
                    },
                ],
            ]
        )

        repo = FeatureRepository(mock_db_pool)
        result = await repo.load_recent_candles(
            symbol="GC",
            timeframe="1m",
            count=60,
        )

        assert len(result) == 1
        gc_candle, dxy_candle = result[0]

        assert isinstance(gc_candle, CandleMessage)
        assert isinstance(dxy_candle, CandleMessage)
        assert gc_candle.symbol == "GC"
        assert dxy_candle.symbol == "DXY"
        assert gc_candle.close == 2654.0
        assert dxy_candle.close == 103.6

    @pytest.mark.asyncio
    async def test_load_recent_candles_skips_unmatched_timestamps(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Load recent candles skips timestamps that don't match."""
        ts1 = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        ts2 = datetime(2025, 1, 15, 10, 1, tzinfo=timezone.utc)
        ts3 = datetime(2025, 1, 15, 10, 2, tzinfo=timezone.utc)

        mock_db_pool.fetch = AsyncMock(
            side_effect=[
                # GC candles - has ts1 and ts2
                [
                    {
                        "timestamp": ts1,
                        "open": 2650.0,
                        "high": 2655.0,
                        "low": 2648.0,
                        "close": 2654.0,
                        "volume": 1000.0,
                    },
                    {
                        "timestamp": ts2,
                        "open": 2654.0,
                        "high": 2658.0,
                        "low": 2652.0,
                        "close": 2656.0,
                        "volume": 1100.0,
                    },
                ],
                # DXY candles - has ts1 and ts3 (no ts2)
                [
                    {
                        "timestamp": ts1,
                        "open": 103.5,
                        "high": 103.7,
                        "low": 103.4,
                        "close": 103.6,
                        "volume": 500.0,
                    },
                    {
                        "timestamp": ts3,
                        "open": 103.6,
                        "high": 103.8,
                        "low": 103.5,
                        "close": 103.7,
                        "volume": 600.0,
                    },
                ],
            ]
        )

        repo = FeatureRepository(mock_db_pool)
        result = await repo.load_recent_candles(
            symbol="GC",
            timeframe="1m",
            count=60,
        )

        # Only ts1 is common
        assert len(result) == 1
        gc_candle, dxy_candle = result[0]
        assert gc_candle.timestamp == ts1
        assert dxy_candle.timestamp == ts1

    @pytest.mark.asyncio
    async def test_load_recent_candles_converts_types(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Load recent candles converts database types correctly."""
        ts = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)

        mock_db_pool.fetch = AsyncMock(
            side_effect=[
                [
                    {
                        "timestamp": ts,
                        "open": "2650.5",
                        "high": "2655.0",
                        "low": "2648.0",
                        "close": "2654.0",
                        "volume": "1000.0",
                    }
                ],
                [
                    {
                        "timestamp": ts,
                        "open": "103.5",
                        "high": "103.7",
                        "low": "103.4",
                        "close": "103.6",
                        "volume": "500.0",
                    }
                ],
            ]
        )

        repo = FeatureRepository(mock_db_pool)
        result = await repo.load_recent_candles(
            symbol="GC",
            timeframe="1m",
            count=60,
        )

        assert len(result) == 1
        gc_candle, _ = result[0]

        # Values should be floats
        assert isinstance(gc_candle.open, float)
        assert gc_candle.open == 2650.5


class TestFeatureRepositoryMultipleTimeframes:
    """Test repository with different timeframes."""

    @pytest.mark.asyncio
    async def test_load_candles_respects_timeframe(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Load candles uses correct timeframe in query."""
        mock_db_pool.fetch = AsyncMock(return_value=[])

        repo = FeatureRepository(mock_db_pool)
        await repo.load_recent_candles(
            symbol="GC",
            timeframe="15m",
            count=30,
        )

        # Check both calls use the correct timeframe
        assert mock_db_pool.fetch.call_count == 2

        # First call for GC
        gc_call = mock_db_pool.fetch.call_args_list[0]
        assert gc_call[0][1] == "GC"
        assert gc_call[0][2] == "15m"

        # Second call for DXY
        dxy_call = mock_db_pool.fetch.call_args_list[1]
        assert dxy_call[0][1] == "DXY"
        assert dxy_call[0][2] == "15m"
