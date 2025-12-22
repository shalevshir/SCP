"""Pydantic message schemas for inter-service communication."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CandleMessage(BaseModel):
    """OHLCV candle data message.
    
    Published by: Data Adapter
    Consumed by: Feature Engine
    """
    
    timestamp: datetime = Field(description="Candle opening time (UTC)")
    symbol: str = Field(description="Asset symbol (e.g., 'GC', 'DXY')")
    timeframe: str = Field(description="Timeframe (e.g., '1m', '15m', '1h')")
    open: float = Field(description="Opening price", gt=0)
    high: float = Field(description="Highest price", gt=0)
    low: float = Field(description="Lowest price", gt=0)
    close: float = Field(description="Closing price", gt=0)
    volume: float = Field(description="Trading volume", ge=0)

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2025-01-15T10:00:00Z",
                "symbol": "GC",
                "timeframe": "1m",
                "open": 2650.0,
                "high": 2652.0,
                "low": 2649.0,
                "close": 2651.0,
                "volume": 1000.0,
            }
        }


class FeaturesMessage(BaseModel):
    """Computed features message.
    
    Published by: Feature Engine
    Consumed by: Bot Core, HTF Bias
    """
    
    timestamp: datetime = Field(description="Feature computation time (UTC)")
    symbol: str = Field(description="Asset symbol")
    timeframe: str = Field(description="Timeframe")
    close: float = Field(description="Close price")
    vwap: float | None = Field(default=None, description="VWAP value")
    rsi: float | None = Field(default=None, description="RSI value", ge=0, le=100)
    ema_9: float | None = Field(default=None, description="9-period EMA")
    ema_20: float | None = Field(default=None, description="20-period EMA")
    ema_50: float | None = Field(default=None, description="50-period EMA")
    dxy_correlation: float | None = Field(
        default=None, description="DXY correlation", ge=-1, le=1
    )
    structure_label: str | None = Field(default=None, description="Structure label")
    vwap_deviation: float | None = Field(default=None, description="VWAP deviation %")

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2025-01-15T10:00:00Z",
                "symbol": "GC",
                "timeframe": "1m",
                "close": 2651.0,
                "vwap": 2650.5,
                "rsi": 55.2,
                "ema_9": 2649.8,
                "ema_20": 2648.5,
                "ema_50": 2647.0,
                "dxy_correlation": -0.75,
                "structure_label": "HH",
                "vwap_deviation": 0.02,
            }
        }


class HTFBiasMessage(BaseModel):
    """Higher-timeframe bias message.
    
    Published by: HTF Bias Service
    Consumed by: Bot Core
    """
    
    timestamp: datetime = Field(description="Bias computation time (UTC)")
    bias: str = Field(description="Bias direction", pattern="^(bullish|bearish|neutral)$")
    score: float = Field(description="Bias score (0-10)", ge=0, le=10)
    confidence: str = Field(description="Confidence level", pattern="^(A\\+|A|B|C)$")
    structure_15m: str | None = Field(default=None, description="15m structure")
    structure_1h: str | None = Field(default=None, description="1h structure")
    dxy_aligned: bool = Field(description="DXY alignment status")
    chop_detected: bool = Field(description="Chop/conflict detected")

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2025-01-15T10:00:00Z",
                "bias": "bullish",
                "score": 8.5,
                "confidence": "A+",
                "structure_15m": "HH",
                "structure_1h": "bullish",
                "dxy_aligned": True,
                "chop_detected": False,
            }
        }


class SignalMessage(BaseModel):
    """Trading signal message.
    
    Published by: Bot Core
    Consumed by: Execution Service
    """
    
    id: str = Field(description="Unique signal ID")
    timestamp: datetime = Field(description="Signal generation time (UTC)")
    direction: str = Field(description="Trade direction", pattern="^(long|short)$")
    setup_type: str = Field(description="Setup type (e.g., 'VWAP_RECLAIM')")
    score: float = Field(description="Signal score (0-10)", ge=0, le=10)
    confidence: str = Field(description="Confidence level", pattern="^(A\\+|A|B|C)$")
    entry_price: float = Field(description="Suggested entry price", gt=0)
    sl_price: float = Field(description="Stop loss price", gt=0)
    tp_price: float = Field(description="Take profit price", gt=0)
    factors: dict[str, Any] = Field(description="Contributing factors")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "timestamp": "2025-01-15T10:00:00Z",
                "direction": "long",
                "setup_type": "VWAP_RECLAIM",
                "score": 9.0,
                "confidence": "A+",
                "entry_price": 2651.0,
                "sl_price": 2645.0,
                "tp_price": 2663.0,
                "factors": {
                    "vwap_reclaim": True,
                    "htf_bullish": True,
                    "dxy_aligned": True,
                },
            }
        }


class TradeMessage(BaseModel):
    """Trade lifecycle message.
    
    Published by: Execution Service
    Consumed by: Monitoring, Analytics
    """
    
    id: str = Field(description="Unique trade ID")
    signal_id: str = Field(description="Source signal ID")
    direction: str = Field(description="Trade direction", pattern="^(long|short)$")
    entry_price: float = Field(description="Actual entry price", gt=0)
    sl_price: float = Field(description="Stop loss price", gt=0)
    tp_price: float = Field(description="Take profit price", gt=0)
    quantity: int = Field(description="Position size", gt=0)
    opened_at: datetime = Field(description="Trade opened time (UTC)")
    closed_at: datetime | None = Field(default=None, description="Trade closed time")
    exit_price: float | None = Field(default=None, description="Exit price")
    pnl_points: float | None = Field(default=None, description="P&L in points")
    exit_reason: str | None = Field(default=None, description="Exit reason")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "signal_id": "550e8400-e29b-41d4-a716-446655440000",
                "direction": "long",
                "entry_price": 2651.0,
                "sl_price": 2645.0,
                "tp_price": 2663.0,
                "quantity": 1,
                "opened_at": "2025-01-15T10:01:00Z",
                "closed_at": "2025-01-15T10:15:00Z",
                "exit_price": 2663.0,
                "pnl_points": 12.0,
                "exit_reason": "TP_HIT",
            }
        }

