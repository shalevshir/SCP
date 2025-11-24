"""HTF Bias types and data structures.

Defines the HTFBias dataclass and related types used throughout the HTF engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from rule_engine.htf.seasonality.rules import SeasonalityPeriod


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
        dxy_corr_1h: 1H DXY correlation
        dxy_corr_15m: 15M DXY correlation
        dxy_chop_detected: Whether DXY is in chop/ranging mode
        dxy_alignment: Whether DXY is aligned with bias
    """

    # Core bias
    bias: Literal["bullish", "bearish", "neutral"]
    direction: Literal["long", "short", "neutral"]
    score: float
    confidence: Literal["high", "medium", "low"]

    # Structure
    structure_1h: Optional[str] = None
    structure_15m: Optional[str] = None
    bos_detected: bool = False
    choch_detected: bool = False

    # Liquidity
    liquidity_sweep_detected: bool = False
    liquidity_sweep_type: Optional[Literal["bullish", "bearish"]] = None

    # VWAP
    vwap_1h: Optional[float] = None
    vwap_distance_1h: Optional[float] = None
    vwap_slope_1h: Optional[float] = None
    vwap_trend_confirmed: bool = False
    fvg_alignment_score: float = 0.0

    # Seasonality
    seasonality_period: Optional[SeasonalityPeriod] = None
    seasonality_adjustment: float = 0.0

    # DXY
    dxy_corr_1h: Optional[float] = None
    dxy_corr_15m: Optional[float] = None
    dxy_chop_detected: bool = False
    dxy_alignment: bool = False

    # Conflict detection
    conflict_detected: bool = False
    conflict_reason: Optional[str] = None

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
            "vwap_1h": self.vwap_1h,
            "vwap_distance_1h": self.vwap_distance_1h,
            "vwap_slope_1h": self.vwap_slope_1h,
            "vwap_trend_confirmed": self.vwap_trend_confirmed,
            "fvg_alignment_score": self.fvg_alignment_score,
            "seasonality_period": self.seasonality_period,
            "seasonality_adjustment": self.seasonality_adjustment,
            "dxy_corr_1h": self.dxy_corr_1h,
            "dxy_corr_15m": self.dxy_corr_15m,
            "dxy_chop_detected": self.dxy_chop_detected,
            "dxy_alignment": self.dxy_alignment,
            "conflict_detected": self.conflict_detected,
            "conflict_reason": self.conflict_reason,
        }

