"""Tests for stream-based warmup error handling."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage


def _build_candle(timestamp: datetime, symbol: str) -> CandleMessage:
    return CandleMessage(
        timestamp=timestamp,
        symbol=symbol,
        timeframe="1m",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
    )


class TestWarmupFromStream:
    """Test warmup_from_stream exception handling."""

    @pytest.mark.asyncio
    async def test_warmup_from_stream_handles_persistence_error(self) -> None:
        """Stream warmup returns False when batch persistence fails."""
        base_ts = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
        gc_candles = [_build_candle(base_ts, "GC")]
        dxy_candles = [_build_candle(base_ts, "DXY")]

        async def fake_consume(
            _redis_client: object, stream_name: str, timeout_seconds: int
        ) -> list[CandleMessage]:
            return gc_candles if stream_name.endswith(".gc") else dxy_candles

        def build_features(gc_candle: CandleMessage, _dxy_candle: CandleMessage) -> FeaturesMessage:
            return FeaturesMessage(
                timestamp=gc_candle.timestamp,
                symbol="GC",
                timeframe="1m",
                close=gc_candle.close,
            )

        processor = MagicMock()
        processor.process = MagicMock(side_effect=build_features)
        processor.bar_count = 0
        processor.is_warmed_up = MagicMock(return_value=True)

        repository = MagicMock()
        repository.save_candles_batch = AsyncMock(side_effect=Exception("db error"))
        repository.save_features_batch = AsyncMock()

        with patch(
            "scp_shared.messaging.warmup_consumer.check_warmup_available",
            new=AsyncMock(return_value={"available": True}),
        ), patch(
            "scp_shared.messaging.warmup_consumer.consume_warmup_stream",
            new=AsyncMock(side_effect=fake_consume),
        ), patch("feature_engine_svc.main.config") as mock_config:
            mock_config.warmup_candles = 1
            mock_config.warmup_stream_timeout_seconds = 1

            from feature_engine_svc.main import warmup_from_stream

            success = await warmup_from_stream(
                MagicMock(), processor, repository, timeframe="1m"
            )

        assert success is False
