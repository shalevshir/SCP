"""Feature Engine package for technical indicators and features.

Supports both vectorized (batch) and incremental (stateful) calculation modes:
- Vectorized: Fast batch processing for backtesting with correct time slicing
- Incremental: One-candle-at-a-time for live trading and realistic backtesting
"""

from feature_engine.aggregator import aggregate_features
from feature_engine.backtesting import BacktestProcessor
from feature_engine.dxy_correlation import (
    calculate_dxy_correlation,
    calculate_multiwindow_dxy_correlation,
)
from feature_engine.ema import calculate_ema, calculate_ema_multiple
from feature_engine.integration import (
    align_dataframes,
    prepare_for_aggregation,
    process_features,
)
from feature_engine.rsi import calculate_rsi
from feature_engine.state import (
    DXYCorrelationState,
    EMAState,
    FeatureState,
    RSIState,
    StructureState,
    VWAPState,
)
from feature_engine.structure import (
    calculate_structure_labels,
    get_swing_window_for_timeframe,
)
from feature_engine.vwap import calculate_vwap, calculate_vwap_deviation

__all__ = [
    "aggregate_features",
    "align_dataframes",
    "BacktestProcessor",
    "calculate_dxy_correlation",
    "calculate_multiwindow_dxy_correlation",
    "calculate_ema",
    "calculate_ema_multiple",
    "calculate_rsi",
    "calculate_structure_labels",
    "calculate_vwap",
    "calculate_vwap_deviation",
    "get_swing_window_for_timeframe",
    "prepare_for_aggregation",
    "process_features",
    # Incremental state classes
    "FeatureState",
    "VWAPState",
    "RSIState",
    "EMAState",
    "DXYCorrelationState",
    "StructureState",
]
