"""HTF Bias types and data structures.

Defines the HTFBias dataclass and related types used throughout the HTF engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rule_engine.htf.seasonality.rules import SeasonalityPeriod

if TYPE_CHECKING:
    from common.types import Candle


@dataclass
class HTFBias:
    """Higher Timeframe Bias result.

    Consolidates all HTF components into a single structured output for use
    by the RuleEngine scoring system.

    Attributes:
        bias: Overall directional bias ("bullish", "bearish", "neutral")
        direction: Trading direction ("long", "short", "neutral")
        score: Confidence score 0-10 indicating bias strength
        confidence: High-level confidence rating

        # Structure summary
        structure_1h: 1H structure label (HH, HL, LH, LL, or None)
        structure_15m: 15M structure label
        bos_detected: Whether Break of Structure occurred
        choch_detected: Whether Change of Character occurred

        # Liquidity summary
        liquidity_sweep_detected: Whether liquidity sweep occurred
        liquidity_sweep_type: Type of sweep ("bullish", "bearish", None)

        # Structure event candles
        bos_candle: Candle where BOS occurred (for SL calculation)
        choch_candle: Candle where CHoCH occurred
        sweep_candle: Candle where liquidity sweep occurred
        confirmation_candle: Confirmation candle for current setup

        # VWAP summary
        vwap_1h: 1H VWAP value
        vwap_distance_1h: Price distance from 1H VWAP
        vwap_slope_1h: 1H VWAP slope
        vwap_trend_confirmed: Whether VWAP trend is confirmed
        fvg_alignment_score: FVG interaction score adjustment

        # Seasonality flags
        seasonality_period: Current seasonality period (Sep, Oct, Nov-Dec)
        seasonality_adjustment: Score adjustment based on seasonality

        # DXY flags
        dxy_corr_1h: 1H DXY correlation (scaled window)
        dxy_corr_15m: 15M DXY correlation (scaled window)
        dxy_corr_1m: 1M micro correlation (5-bar window)
        dxy_corr_5m: 5M micro correlation (5-bar window)
        dxy_structure: DXY structure label (HH/HL/LH/LL)
        dxy_chop_detected: Whether DXY is in chop on 1H (legacy)
        dxy_chop_5m: Whether DXY is in chop on 5M (for alignment)
        dxy_alignment: Whether DXY is aligned with bias (behavior-based)
        dxy_alignment_score: HTF correlation bonus (0-0.5) when aligned

        # Structure quality metrics (for strict scoring)
        structure_clarity: 0-1 score measuring swing sequence purity
        bars_since_bos: Bars since last BOS event (staleness)
        bars_since_choch: Bars since last CHoCH event
        chop_detected: True if recent labels are mixed (HH+LL within window)
    """

    # Core bias
    bias: Literal["bullish", "bearish", "neutral"]
    direction: Literal["long", "short", "neutral"]
    score: float
    confidence: Literal["high", "medium", "low"]

    # Structure
    structure_1h: str | None = None
    structure_15m: str | None = None
    bos_detected: bool = False
    choch_detected: bool = False

    # Liquidity
    liquidity_sweep_detected: bool = False
    liquidity_sweep_type: Literal["bullish", "bearish"] | None = None

    # Structure event candles
    bos_candle: Candle | None = None
    choch_candle: Candle | None = None
    sweep_candle: Candle | None = None
    confirmation_candle: Candle | None = None

    # VWAP
    vwap_1h: float | None = None
    vwap_distance_1h: float | None = None
    vwap_slope_1h: float | None = None
    vwap_trend_confirmed: bool = False
    fvg_alignment_score: float = 0.0

    # Seasonality
    seasonality_period: SeasonalityPeriod | None = None
    seasonality_adjustment: float = 0.0

    # DXY
    dxy_corr_1h: float | None = None
    dxy_corr_15m: float | None = None
    dxy_corr_1m: float | None = None  # Micro correlation (1M)
    dxy_corr_5m: float | None = None  # Micro correlation (5M)
    dxy_structure: str | None = None  # DXY structure label (HH/HL/LH/LL)
    dxy_chop_detected: bool = False  # 1H chop (legacy)
    dxy_chop_5m: bool = False  # 5M chop (for alignment)
    dxy_alignment: bool = False
    dxy_alignment_score: float = 0.0  # HTF correlation bonus (0-0.5) when aligned

    # Structure quality metrics for strict scoring
    structure_clarity: float = 0.0  # 0-1 score measuring swing sequence purity
    bars_since_bos: int | None = None  # Bars since last BOS (staleness metric)
    bars_since_choch: int | None = None  # Bars since last CHoCH
    chop_detected: bool = False  # True if recent labels are mixed (HH+LL within window)
    atr_15m: float | None = None  # 15M ATR for noise filtering in structure detection

    # Conflict detection
    conflict_detected: bool = False
    conflict_reason: str | None = None

    def to_dict(self) -> dict:
        """Convert HTFBias to dictionary for logging/serialization."""
        return {
            "bias": self.bias,
            "direction": self.direction,
            "score": self.score,
            "confidence": self.confidence,
            "structure_1h": self.structure_1h,
            "structure_15m": self.structure_15m,
            "bos_detected": self.bos_detected,
            "choch_detected": self.choch_detected,
            "liquidity_sweep_detected": self.liquidity_sweep_detected,
            "liquidity_sweep_type": self.liquidity_sweep_type,
            "bos_candle_timestamp": (
                self.bos_candle.timestamp if self.bos_candle else None
            ),
            "choch_candle_timestamp": (
                self.choch_candle.timestamp if self.choch_candle else None
            ),
            "sweep_candle_timestamp": (
                self.sweep_candle.timestamp if self.sweep_candle else None
            ),
            "confirmation_candle_timestamp": (
                self.confirmation_candle.timestamp if self.confirmation_candle else None
            ),
            "vwap_1h": self.vwap_1h,
            "vwap_distance_1h": self.vwap_distance_1h,
            "vwap_slope_1h": self.vwap_slope_1h,
            "vwap_trend_confirmed": self.vwap_trend_confirmed,
            "fvg_alignment_score": self.fvg_alignment_score,
            "seasonality_period": self.seasonality_period,
            "seasonality_adjustment": self.seasonality_adjustment,
            "dxy_corr_1h": self.dxy_corr_1h,
            "dxy_corr_15m": self.dxy_corr_15m,
            "dxy_corr_1m": self.dxy_corr_1m,
            "dxy_corr_5m": self.dxy_corr_5m,
            "dxy_structure": self.dxy_structure,
            "dxy_chop_detected": self.dxy_chop_detected,
            "dxy_chop_5m": self.dxy_chop_5m,
            "dxy_alignment": self.dxy_alignment,
            "dxy_alignment_score": self.dxy_alignment_score,
            "structure_clarity": self.structure_clarity,
            "bars_since_bos": self.bars_since_bos,
            "bars_since_choch": self.bars_since_choch,
            "chop_detected": self.chop_detected,
            "atr_15m": self.atr_15m,
            "conflict_detected": self.conflict_detected,
            "conflict_reason": self.conflict_reason,
        }
