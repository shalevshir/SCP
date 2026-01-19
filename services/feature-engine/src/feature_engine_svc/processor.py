"""FeatureProcessor wrapper for service use.

This module wraps the existing StreamingFeatureProcessor to convert between
message types (CandleMessage <-> Candle) and handle service-level concerns.
"""

from scp_shared.indicators.streaming import StreamingFeatureProcessor
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage
from scp_shared.common import Candle


class FeatureProcessor:
    """Wrapper around StreamingFeatureProcessor for service use.
    
    Handles conversion between:
    - Input: CandleMessage (from Redis streams)
    - Internal: Candle (for StreamingFeatureProcessor)
    - Output: FeaturesMessage (for Redis streams)
    """
    
    def __init__(
        self,
        timeframe: str = "1m",
        rsi_period: int = 14,
        ema_periods: list[int] | None = None,
        dxy_window: int = 50,
        swing_window: int | None = None,
        session_reset: bool = True,
    ):
        """Initialize feature processor.
        
        Args:
            timeframe: Target timeframe (e.g., "1m", "15m", "1h")
            rsi_period: RSI calculation period (default: 14)
            ema_periods: List of EMA periods (default: [9, 20, 50])
            dxy_window: DXY correlation window (default: 50)
            swing_window: Structure label swing window (None = auto-detect by timeframe)
            session_reset: Whether to reset VWAP at session boundaries (default: True)
        """
        self.processor = StreamingFeatureProcessor(
            timeframe=timeframe,
            rsi_period=rsi_period,
            ema_periods=ema_periods,
            dxy_window=dxy_window,
            swing_window=swing_window,
            session_reset=session_reset,
        )
        self.timeframe = timeframe
    
    def process(
        self,
        gc_message: CandleMessage,
        dxy_message: CandleMessage,
    ) -> FeaturesMessage:
        """Process candle pair and return features message.
        
        Args:
            gc_message: Gold candle message
            dxy_message: DXY candle message
            
        Returns:
            FeaturesMessage with computed indicators
        """
        # Convert CandleMessage to internal Candle type
        gc_candle = Candle(
            timestamp=gc_message.timestamp,
            open=gc_message.open,
            high=gc_message.high,
            low=gc_message.low,
            close=gc_message.close,
            volume=gc_message.volume,
            symbol=gc_message.symbol,
            timeframe=gc_message.timeframe,
            source="STREAM",
        )
        dxy_candle = Candle(
            timestamp=dxy_message.timestamp,
            open=dxy_message.open,
            high=dxy_message.high,
            low=dxy_message.low,
            close=dxy_message.close,
            volume=dxy_message.volume,
            symbol=dxy_message.symbol,
            timeframe=dxy_message.timeframe,
            source="STREAM",
        )
        
        # Process through existing StreamingFeatureProcessor
        features_series = self.processor.update(gc_candle, dxy_candle)
        
        # Convert to FeaturesMessage format
        dxy_corr = self._safe_float(features_series.get("dxy_corr"))
        # Clamp correlation to [-1, 1] range due to floating point precision
        if dxy_corr is not None:
            dxy_corr = max(-1.0, min(1.0, dxy_corr))
        
        # Prepare DXY fields with clamping
        dxy_5m_corr = self._safe_float(features_series.get("dxy_5m_corr"))
        if dxy_5m_corr is not None:
            dxy_5m_corr = max(-1.0, min(1.0, dxy_5m_corr))
        
        return FeaturesMessage(
            timestamp=gc_message.timestamp,
            symbol="GC",
            timeframe=self.timeframe,
            close=float(features_series.get("close", gc_message.close)),
            # OHLC data
            open=float(gc_message.open),
            high=float(gc_message.high),
            low=float(gc_message.low),
            volume=float(gc_message.volume),
            # VWAP indicators
            vwap=self._safe_float(features_series.get("vwap")),
            vwap_slope=self._safe_float(features_series.get("vwap_slope")),
            vwap_deviation=self._safe_float(features_series.get("vwap_deviation")),
            atr=self._safe_float(features_series.get("atr")),
            vwap_deviation_normalized=self._safe_float(features_series.get("vwap_deviation_normalized")),
            # Trend indicators
            rsi=self._safe_float(features_series.get("rsi")),
            ema_9=self._safe_float(features_series.get("ema_9")),
            ema_20=self._safe_float(features_series.get("ema_20")),
            ema_50=self._safe_float(features_series.get("ema_50")),
            # DXY correlation fields
            dxy_correlation=dxy_corr,  # Legacy field
            dxy_corr=dxy_corr,  # Raw correlation
            dxy_5m_corr=dxy_5m_corr,
            dxy_structure=features_series.get("dxy_structure_label") or features_series.get("dxy_structure"),
            # Structure labels
            structure_label=features_series.get("structure_label"),
            htf_structure_label=features_series.get("htf_structure_label") or features_series.get("structure_15m"),
            # BOS/CHoCH fields for VWAP_RECLAIM validation
            bos_direction=features_series.get("bos_direction"),
            bos_recent=features_series.get("bos_recent"),
            bos_age=self._safe_int(features_series.get("bos_age")),
            choch_detected=features_series.get("choch_detected"),
            choch_direction=features_series.get("choch_direction"),
            structure_clarity=self._safe_float(features_series.get("structure_clarity")),
            trend_confidence=self._safe_float(features_series.get("trend_confidence")),
            liquidity_sweep=features_series.get("liquidity_sweep"),
            sweep_age=self._safe_int(features_series.get("sweep_age")),
            # SL Priority System fields (SOP Section 3.2-3.3)
            swing_hl_low=self._safe_float(features_series.get("swing_hl_low")),
            swing_lh_high=self._safe_float(features_series.get("swing_lh_high")),
            reclaim_candle_low=self._safe_float(features_series.get("reclaim_candle_low")),
            reclaim_candle_high=self._safe_float(features_series.get("reclaim_candle_high")),
            reclaim_candle_idx=self._safe_int(features_series.get("reclaim_candle_idx")),
            # TP Structural Target fields (SOP Section 4.3)
            nearest_liquidity_long=self._safe_float(features_series.get("nearest_swing_high_above")),
            nearest_liquidity_short=self._safe_float(features_series.get("nearest_swing_low_below")),
            prior_session_high=self._safe_float(features_series.get("prior_session_high")),
            prior_session_low=self._safe_float(features_series.get("prior_session_low")),
            # Expansion gate fields
            expansion_detected=bool(features_series.get("expansion_detected", False)),
            expansion_reasons=features_series.get("expansion_reasons", []) or [],
            # Confirmation tracking
            second_confirmation_long=bool(features_series.get("second_confirmation_long", False)),
            second_confirmation_short=bool(features_series.get("second_confirmation_short", False)),
        )
    
    def is_warmed_up(self) -> bool:
        """Check if processor has enough data to produce reliable features.
        
        Returns:
            True if warmup period complete
        """
        return self.processor.is_warmed_up()
    
    def reset(self) -> None:
        """Reset all state to initial conditions."""
        self.processor.reset()
    
    @property
    def bar_count(self) -> int:
        """Get current bar count."""
        return self.processor.bar_count
    
    @staticmethod
    def _safe_float(value) -> float | None:
        """Convert value to float or None if invalid.
        
        Args:
            value: Value to convert (can be None, NaN, inf, or numeric)
            
        Returns:
            Float value or None
        """
        if value is None:
            return None
        
        # Handle pandas NA/NaN
        try:
            import pandas as pd
            if pd.isna(value):
                return None
        except (ImportError, TypeError):
            pass
        
        # Handle numpy NaN and infinity
        try:
            import math
            float_val = float(value)
            if math.isnan(float_val) or math.isinf(float_val):
                return None
        except (ValueError, TypeError):
            return None
        
        return float(value)

    @staticmethod
    def _safe_int(value) -> int | None:
        """Convert value to int or None if invalid.
        
        Args:
            value: Value to convert (can be None, NaN, or numeric)
            
        Returns:
            Int value or None
        """
        if value is None:
            return None
        
        # Handle pandas NA/NaN
        try:
            import pandas as pd
            if pd.isna(value):
                return None
        except (ImportError, TypeError):
            pass
        
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

