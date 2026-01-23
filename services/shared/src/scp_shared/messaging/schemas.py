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

    # OHLC data (needed for invalidation candle checks)
    open: float | None = Field(default=None, description="Open price", gt=0)
    high: float | None = Field(default=None, description="High price", gt=0)
    low: float | None = Field(default=None, description="Low price", gt=0)
    volume: float | None = Field(default=None, description="Volume", ge=0)

    # VWAP indicators
    vwap: float | None = Field(default=None, description="VWAP value")
    vwap_slope: float | None = Field(
        default=None, description="VWAP slope (for FADE invalidation)"
    )
    vwap_deviation: float | None = Field(default=None, description="VWAP deviation %")
    atr: float | None = Field(
        default=None, description="Average True Range (14-period)"
    )
    vwap_deviation_normalized: float | None = Field(
        default=None,
        description="Normalized VWAP deviation: (Price - VWAP) / ATR - dimensionless, volatility-adjusted metric",
    )

    # Trend indicators
    rsi: float | None = Field(default=None, description="RSI value", ge=0, le=100)
    ema_9: float | None = Field(default=None, description="9-period EMA")
    ema_20: float | None = Field(default=None, description="20-period EMA")
    ema_50: float | None = Field(default=None, description="50-period EMA")

    # DXY correlation fields
    dxy_correlation: float | None = Field(
        default=None, description="DXY correlation (legacy field)", ge=-1, le=1
    )
    dxy_corr: float | None = Field(
        default=None, description="DXY correlation (raw)", ge=-1, le=1
    )
    dxy_5m_corr: float | None = Field(
        default=None, description="DXY 5m correlation", ge=-1, le=1
    )
    dxy_structure: str | None = Field(default=None, description="DXY structure label")

    # Structure labels
    structure_label: str | None = Field(default=None, description="Structure label")
    htf_structure_label: str | None = Field(
        default=None, description="HTF structure label (15m/1h)"
    )

    # BOS/CHoCH fields for VWAP_RECLAIM validation
    bos_direction: str | None = Field(
        default=None, description="Break of structure direction"
    )
    bos_recent: bool | None = Field(
        default=None, description="Whether BOS was detected recently"
    )
    bos_age: int | None = Field(
        default=None, description="Age of most recent BOS in bars"
    )
    choch_detected: bool | None = Field(
        default=None, description="Whether CHoCH was detected"
    )
    choch_direction: str | None = Field(default=None, description="CHoCH direction")
    structure_clarity: float | None = Field(
        default=None, description="Structure clarity score"
    )
    trend_confidence: float | None = Field(
        default=None, description="Trend confidence score (0-1)"
    )
    liquidity_sweep: bool | None = Field(
        default=None, description="Whether liquidity sweep detected"
    )
    sweep_age: int | None = Field(
        default=None, description="Age of most recent sweep in bars"
    )

    # SL Priority System fields (SOP Section 3.2-3.3)
    swing_hl_low: float | None = Field(
        default=None, description="Low of most recent HL swing (for long SL Priority A)"
    )
    swing_lh_high: float | None = Field(
        default=None,
        description="High of most recent LH swing (for short SL Priority A)",
    )
    reclaim_candle_low: float | None = Field(
        default=None, description="Low of reclaim candle (for long SL Priority B)"
    )
    reclaim_candle_high: float | None = Field(
        default=None, description="High of reclaim candle (for short SL Priority B)"
    )
    reclaim_candle_idx: int | None = Field(
        default=None, description="Bar index of reclaim candle"
    )

    # TP Structural Target fields (SOP Section 4.3)
    # 1m timeframe structural levels (computed by Feature Engine)
    immediate_resistance: float | None = Field(
        default=None,
        description="Immediate 1m resistance level within 1R (blocks long TPs)",
    )
    immediate_support: float | None = Field(
        default=None,
        description="Immediate 1m support level within 1R (blocks short TPs)",
    )
    prior_session_high: float | None = Field(
        default=None, description="Previous session high"
    )
    prior_session_low: float | None = Field(
        default=None, description="Previous session low"
    )
    nearest_liquidity_long: float | None = Field(
        default=None, description="Nearest 1m swing high above (fallback for long TP)"
    )
    nearest_liquidity_short: float | None = Field(
        default=None, description="Nearest 1m swing low below (fallback for short TP)"
    )

    # NOTE: HTF structural targets (htf_range, untouched_liquidity, FVGs) are in HTFBiasMessage

    # Expansion gate fields
    expansion_detected: bool = Field(
        default=False, description="VWAP_RECLAIM expansion detected"
    )
    expansion_reasons: list[str] = Field(
        default_factory=list, description="Expansion detection reasons"
    )

    # Confirmation tracking fields
    second_confirmation_long: bool = Field(
        default=False, description="Second confirmation for long satisfied"
    )
    second_confirmation_short: bool = Field(
        default=False, description="Second confirmation for short satisfied"
    )

    # VWAP acceptance fields (SOP alignment)
    bars_near_vwap: int | None = Field(
        default=None,
        description="Consecutive bars within VWAP proximity band (±0.2 ATR); None when ATR unavailable",
    )
    bars_since_last_vwap_touch: int | None = Field(
        default=None, description="Bars since last VWAP touch/interaction"
    )

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
    bias: str = Field(
        description="Bias direction", pattern="^(bullish|bearish|neutral)$"
    )
    score: float = Field(description="Bias score (0-10)", ge=0, le=10)
    confidence: str = Field(description="Confidence level", pattern="^(A\\+|A|B|C)$")
    structure_15m: str | None = Field(default=None, description="15m structure")
    structure_1h: str | None = Field(default=None, description="1h structure")
    dxy_aligned: bool = Field(description="DXY alignment status")
    chop_detected: bool = Field(description="Chop/conflict detected")

    # Additional fields for scoring bonuses (added for parity with backtester)
    seasonality_adjustment: float = Field(
        default=0.0, description="Seasonality score adjustment"
    )
    seasonality_period: str | None = Field(
        default=None, description="Current seasonality period"
    )
    vwap_trend_confirmed: bool = Field(
        default=False, description="VWAP trend confirmation"
    )

    # Structure quality fields required for calculate_structure_alignment scoring
    bos_detected: bool = Field(default=False, description="Break of Structure detected")
    bars_since_bos: int | None = Field(
        default=None, description="Bars since last BOS event"
    )
    structure_clarity: float = Field(
        default=0.0, description="Structure clarity score (0-1)"
    )
    liquidity_sweep_detected: bool = Field(
        default=False, description="Liquidity sweep detected"
    )

    # Conflict/chop fields required for htf_valid validation (reject signals during conflicts)
    conflict_detected: bool = Field(
        default=False, description="HTF conflict detected (mixed signals)"
    )
    conflict_reason: str | None = Field(
        default=None, description="Reason for conflict detection"
    )
    dxy_chop_detected: bool = Field(
        default=False, description="DXY chop detected on 1H"
    )

    # DXY correlation and structure fields required for DXY_CONTINUATION detection
    dxy_corr_1m: float | None = Field(
        default=None, description="DXY 1M micro correlation (5-bar window)"
    )
    dxy_corr_5m: float | None = Field(
        default=None, description="DXY 5M micro correlation (5-bar window)"
    )
    dxy_corr_15m: float | None = Field(default=None, description="DXY 15M correlation")
    dxy_corr_1h: float | None = Field(default=None, description="DXY 1H correlation")
    dxy_structure: str | None = Field(
        default=None, description="DXY structure label (HH/HL/LH/LL)"
    )
    dxy_chop_5m: bool = Field(default=False, description="DXY chop detected on 5M")

    # TP Structural Targets from HTF analysis (SOP Section 4.3)
    # Priority hierarchy for long TPs: htf_range_high > untouched_liquidity_high > nearest_fvg_high
    htf_range_high: float | None = Field(
        default=None,
        description="HTF range high (highest point in current 15m/1h consolidation/range)",
    )
    htf_range_low: float | None = Field(
        default=None,
        description="HTF range low (lowest point in current 15m/1h consolidation/range)",
    )
    untouched_liquidity_high: float | None = Field(
        default=None,
        description="Untouched HTF buy-side liquidity (clean HH on 15m/1h not yet violated)",
    )
    untouched_liquidity_low: float | None = Field(
        default=None,
        description="Untouched HTF sell-side liquidity (clean LL on 15m/1h not yet violated)",
    )
    nearest_fvg_high: float | None = Field(
        default=None, description="Nearest HTF FVG completion level above (for long TP)"
    )
    nearest_fvg_low: float | None = Field(
        default=None,
        description="Nearest HTF FVG completion level below (for short TP)",
    )
    opposing_fvg_high: float | None = Field(
        default=None,
        description="HTF bearish FVG upper boundary (blocks long TPs inside it)",
    )
    opposing_fvg_low: float | None = Field(
        default=None, description="HTF bearish FVG lower boundary"
    )
    opposing_fvg_bullish_high: float | None = Field(
        default=None,
        description="HTF bullish FVG upper boundary (blocks short TPs inside it)",
    )
    opposing_fvg_bullish_low: float | None = Field(
        default=None, description="HTF bullish FVG lower boundary"
    )

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
                "seasonality_adjustment": 0.8,
                "seasonality_period": "november_december",
                "vwap_trend_confirmed": True,
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
    diagnostics: dict[str, Any] | None = Field(
        default=None,
        description="Signal diagnostics for debugging (includes rejection_analysis, structure state, etc.)",
    )

    # TP Plan fields (SOP continuation mode)
    tp_mode: str = Field(
        default="static", description="TP mode: 'static' or 'continuation'"
    )
    tp2_price: float | None = Field(
        default=None, description="Secondary TP for continuation mode"
    )
    rr_tp1: float | None = Field(default=None, description="R:R at TP1")
    rr_potential: float | None = Field(
        default=None, description="Total R:R potential (continuation)"
    )
    be_after_tp1: bool = Field(default=False, description="Move SL to BE after TP1 hit")
    tp_target_source: str | None = Field(
        default=None, description="Source of TP target (e.g., 'htf_range_high')"
    )

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
