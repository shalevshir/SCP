"""Dashboard module for Shir Capital Live Trading Simulation.

This module provides a Plotly Dash dashboard for live trading simulation
with the following architecture:

- **dashboard.core**: Pure Python business logic (no Dash dependencies)
  - DataStream: Historical data iterator
  - SimulationEngine: Core orchestrator with warmup and auto-pause
  - DashboardState: Immutable state container

- **dashboard.components**: Dash UI components
  - Controls: Play/Pause/Step buttons, speed, progress
  - Indicators: 15M indicators with SOP validation
  - HTF Panel: Higher timeframe bias display
  - Signal Panel: Current trade signal display
  - Chart: Price chart with VWAP and DXY overlay

- **dashboard.app**: Main LiveDashboard class

Usage:
    from dashboard.app import LiveDashboard
    from dashboard.core import DataStream, SimulationEngine

    # Set up data stream
    stream = DataStream("./data/gc_dx_ohlcv/")
    stream.load(start_date, end_date)
    stream.seek_to_timestamp(display_start)

    # Create engine
    engine = SimulationEngine(stream, validation_engine, session_validator)
    engine.warmup()

    # Launch dashboard
    dashboard = LiveDashboard(engine)
    dashboard.run()
"""

from dashboard.app import LiveDashboard
from dashboard.core import DataStream, DashboardState, PriceBar, SimulationEngine

__all__ = [
    "LiveDashboard",
    "DataStream",
    "DashboardState",
    "PriceBar",
    "SimulationEngine",
]

