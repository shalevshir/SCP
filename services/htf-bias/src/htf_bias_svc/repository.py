"""HTF Bias Repository - persists and loads bias data from PostgreSQL."""

from datetime import datetime

from scp_shared.database import DatabasePool
from scp_shared.messaging.schemas import HTFBiasMessage, CandleMessage


class BiasRepository:
    """Persists and loads HTF bias history from PostgreSQL.

    Handles bias persistence for warmup recovery and historical analysis.
    """

    def __init__(self, db_pool: DatabasePool):
        """Initialize bias repository.

        Args:
            db_pool: Database connection pool
        """
        self.db = db_pool

    async def save_bias(self, bias: HTFBiasMessage) -> None:
        """Save bias to database.

        Args:
            bias: Bias message to persist
        """
        query = """
            INSERT INTO htf_bias_history (
                timestamp, bias, score, confidence,
                structure_15m, structure_1h, dxy_aligned, chop_detected,
                seasonality_adjustment, seasonality_period, vwap_trend_confirmed
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (timestamp) DO UPDATE SET
                bias = EXCLUDED.bias,
                score = EXCLUDED.score,
                confidence = EXCLUDED.confidence,
                structure_15m = EXCLUDED.structure_15m,
                structure_1h = EXCLUDED.structure_1h,
                dxy_aligned = EXCLUDED.dxy_aligned,
                chop_detected = EXCLUDED.chop_detected,
                seasonality_adjustment = EXCLUDED.seasonality_adjustment,
                seasonality_period = EXCLUDED.seasonality_period,
                vwap_trend_confirmed = EXCLUDED.vwap_trend_confirmed
        """

        await self.db.execute(
            query,
            bias.timestamp,
            bias.bias,
            bias.score,
            bias.confidence,
            bias.structure_15m,
            bias.structure_1h,
            bias.dxy_aligned,
            bias.chop_detected,
            bias.seasonality_adjustment,
            bias.seasonality_period,
            bias.vwap_trend_confirmed,
        )

    async def load_recent_candles(
        self,
        count: int,
        before_timestamp: datetime | None = None,
    ) -> list[tuple[CandleMessage, CandleMessage]]:
        """Load recent candles for warmup.

        Args:
            count: Number of recent candles to load
            before_timestamp: Only load candles before this timestamp (for replay alignment)

        Returns:
            List of (gc_candle, dxy_candle) tuples sorted by timestamp
        """
        from scp_shared.common.logger import get_logger

        logger = get_logger(__name__)

        # Load GC candles (before specified timestamp if provided)
        if before_timestamp:
            gc_query = """
                SELECT timestamp, open, high, low, close, volume
                FROM candles
                WHERE symbol = $1 AND timeframe = $2 AND timestamp < $4
                ORDER BY timestamp DESC
                LIMIT $3
            """
            gc_rows = await self.db.fetch(gc_query, "GC", "1m", count, before_timestamp)
            logger.info(
                f"Warmup: Loading GC candles before {before_timestamp}, found {len(gc_rows)}"
            )
        else:
            gc_query = """
                SELECT timestamp, open, high, low, close, volume
                FROM candles
                WHERE symbol = $1 AND timeframe = $2
                ORDER BY timestamp DESC
                LIMIT $3
            """
            gc_rows = await self.db.fetch(gc_query, "GC", "1m", count)

        # Load DXY candles (before specified timestamp if provided)
        if before_timestamp:
            dxy_query = """
                SELECT timestamp, open, high, low, close, volume
                FROM candles
                WHERE symbol = $1 AND timeframe = $2 AND timestamp < $4
                ORDER BY timestamp DESC
                LIMIT $3
            """
            dxy_rows = await self.db.fetch(
                dxy_query, "DXY", "1m", count, before_timestamp
            )
            logger.info(
                f"Warmup: Loading DXY candles before {before_timestamp}, found {len(dxy_rows)}"
            )
        else:
            dxy_query = """
                SELECT timestamp, open, high, low, close, volume
                FROM candles
                WHERE symbol = $1 AND timeframe = $2
                ORDER BY timestamp DESC
                LIMIT $3
            """
            dxy_rows = await self.db.fetch(dxy_query, "DXY", "1m", count)

        # Pair by timestamp
        gc_dict = {row["timestamp"]: row for row in gc_rows}
        dxy_dict = {row["timestamp"]: row for row in dxy_rows}

        # Get common timestamps
        common_timestamps = sorted(set(gc_dict.keys()) & set(dxy_dict.keys()))

        # Create candle pairs
        pairs = []
        for ts in common_timestamps:
            gc_row = gc_dict[ts]
            dxy_row = dxy_dict[ts]

            gc_candle = CandleMessage(
                timestamp=gc_row["timestamp"],
                symbol="GC",
                timeframe="1m",
                open=float(gc_row["open"]),
                high=float(gc_row["high"]),
                low=float(gc_row["low"]),
                close=float(gc_row["close"]),
                volume=float(gc_row["volume"]),
            )
            dxy_candle = CandleMessage(
                timestamp=dxy_row["timestamp"],
                symbol="DXY",
                timeframe="1m",
                open=float(dxy_row["open"]),
                high=float(dxy_row["high"]),
                low=float(dxy_row["low"]),
                close=float(dxy_row["close"]),
                volume=float(dxy_row["volume"]),
            )

            pairs.append((gc_candle, dxy_candle))

        return pairs
