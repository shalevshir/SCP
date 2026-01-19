"""Feature Repository - persists and loads features from PostgreSQL."""

from datetime import datetime, timedelta

from scp_shared.database import DatabasePool
from scp_shared.messaging.schemas import FeaturesMessage, CandleMessage


class FeatureRepository:
    """Persists and loads features from PostgreSQL.
    
    Handles feature persistence for warmup recovery and historical analysis.
    """
    
    def __init__(self, db_pool: DatabasePool):
        """Initialize feature repository.
        
        Args:
            db_pool: Database connection pool
        """
        self.db = db_pool
    
    async def save_candle(self, candle: CandleMessage) -> None:
        """Save candle to database.
        
        Args:
            candle: Candle message to persist
        """
        query = """
            INSERT INTO candles (
                timestamp, symbol, timeframe, open, high, low, close, volume
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
        """
        
        await self.db.execute(
            query,
            candle.timestamp,
            candle.symbol,
            candle.timeframe,
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
        )
    
    async def save_features(self, features: FeaturesMessage) -> None:
        """Save features to database.
        
        Args:
            features: Features message to persist
        """
        query = """
            INSERT INTO features (
                timestamp, symbol, timeframe, close, vwap, vwap_slope, rsi,
                ema_9, ema_20, ema_50, dxy_correlation,
                structure_label, vwap_deviation, atr, vwap_deviation_normalized
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE SET
                close = EXCLUDED.close,
                vwap = EXCLUDED.vwap,
                vwap_slope = EXCLUDED.vwap_slope,
                rsi = EXCLUDED.rsi,
                ema_9 = EXCLUDED.ema_9,
                ema_20 = EXCLUDED.ema_20,
                ema_50 = EXCLUDED.ema_50,
                dxy_correlation = EXCLUDED.dxy_correlation,
                structure_label = EXCLUDED.structure_label,
                vwap_deviation = EXCLUDED.vwap_deviation,
                atr = EXCLUDED.atr,
                vwap_deviation_normalized = EXCLUDED.vwap_deviation_normalized
        """
        
        await self.db.execute(
            query,
            features.timestamp,
            features.symbol,
            features.timeframe,
            features.close,
            features.vwap,
            features.vwap_slope if hasattr(features, 'vwap_slope') else None,
            features.rsi,
            features.ema_9,
            features.ema_20,
            features.ema_50,
            features.dxy_correlation,
            features.structure_label,
            features.vwap_deviation,
            features.atr if hasattr(features, 'atr') else None,
            features.vwap_deviation_normalized if hasattr(features, 'vwap_deviation_normalized') else None,
        )
    
    async def load_recent_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int,
    ) -> list[tuple[CandleMessage, CandleMessage]]:
        """Load recent candles for warmup.
        
        Args:
            symbol: Symbol to load (GC)
            timeframe: Timeframe to load
            count: Number of recent candles to load
            
        Returns:
            List of (gc_candle, dxy_candle) tuples
        """
        # Load GC candles
        gc_query = """
            SELECT timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = $1 AND timeframe = $2
            ORDER BY timestamp DESC
            LIMIT $3
        """
        gc_rows = await self.db.fetch(gc_query, "GC", timeframe, count)
        
        # Load DXY candles
        dxy_query = """
            SELECT timestamp, open, high, low, close, volume
            FROM candles
            WHERE symbol = $1 AND timeframe = $2
            ORDER BY timestamp DESC
            LIMIT $3
        """
        dxy_rows = await self.db.fetch(dxy_query, "DXY", timeframe, count)
        
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
                timeframe=timeframe,
                open=float(gc_row["open"]),
                high=float(gc_row["high"]),
                low=float(gc_row["low"]),
                close=float(gc_row["close"]),
                volume=float(gc_row["volume"]),
            )
            dxy_candle = CandleMessage(
                timestamp=dxy_row["timestamp"],
                symbol="DXY",
                timeframe=timeframe,
                open=float(dxy_row["open"]),
                high=float(dxy_row["high"]),
                low=float(dxy_row["low"]),
                close=float(dxy_row["close"]),
                volume=float(dxy_row["volume"]),
            )
            
            pairs.append((gc_candle, dxy_candle))
        
        return pairs

