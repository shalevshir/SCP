"""Feature Engine package for technical indicators and features."""

from feature_engine.aggregator import aggregate_features
from feature_engine.dxy_correlation import calculate_dxy_correlation
from feature_engine.ema import calculate_ema, calculate_ema_multiple
from feature_engine.rsi import calculate_rsi
from feature_engine.vwap import calculate_vwap

__all__ = [
    "aggregate_features",
    "calculate_dxy_correlation",
    "calculate_ema",
    "calculate_ema_multiple",
    "calculate_rsi",
    "calculate_vwap",
]
