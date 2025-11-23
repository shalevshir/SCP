"""Higher Timeframe (HTF) Bias Engine.

This package provides modular components for computing HTF bias according to
Shir Capital's SOP, including:
- Structure analysis (swings, BOS, CHoCH, liquidity sweeps)
- VWAP analysis (calculation, trend validation, FVG interaction)
- DXY analysis (chop detection, correlation)
- Seasonality adjustments
- Final HTFBias object generation

The engine is designed for both vectorized (backtesting) and incremental (live)
processing modes, with parity tests ensuring identical results.
"""

from rule_engine.htf.types import HTFBias

__all__ = ["HTFBias"]

