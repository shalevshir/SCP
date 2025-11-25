"""Backtester package for trade execution simulation.

This package implements backtesting infrastructure for Shir Capital's trading bot,
including entry models, exit logic, PnL calculation, and trade management.
"""

from backtester.entry_model import EntryExecution, execute_entry_at_next_open
from backtester.pipeline import run_backtest_with_entries

__all__ = [
    "EntryExecution",
    "execute_entry_at_next_open",
    "run_backtest_with_entries",
]
