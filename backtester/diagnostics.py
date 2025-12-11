"""Diagnostics helpers for trade debugging context.

This module provides utility functions to attach diagnostic information to trades
for post-hoc debugging and analysis. Diagnostics are stored in a mutable dict
on the Trade object without affecting trade immutability.

Functions:
    add_diag: Add top-level diagnostic key-value pair
    add_nested_diag: Add diagnostic under a nested section
"""

from typing import Any


def add_diag(trade: Any, key: str, value: Any) -> None:
    """Add top-level diagnostic information to trade.
    
    Args:
        trade: Trade object with diagnostics dict
        key: Diagnostic key (e.g., "entry_price_slippage")
        value: Diagnostic value (any JSON-serializable type)
        
    Example:
        >>> add_diag(trade, "entry_method", "next_bar_open")
        >>> add_diag(trade, "slippage_ticks", 2.5)
    """
    if not hasattr(trade, "diagnostics") or trade.diagnostics is None:
        trade.diagnostics = {}
    trade.diagnostics[key] = value


def add_nested_diag(trade: Any, section: str, key: str, value: Any) -> None:
    """Add diagnostic information under a nested section.
    
    Args:
        trade: Trade object with diagnostics dict
        section: Section name (e.g., "entry_context", "sl_hit_context")
        key: Diagnostic key within section
        value: Diagnostic value (any JSON-serializable type)
        
    Example:
        >>> add_nested_diag(trade, "entry_context", "vwap", 2650.5)
        >>> add_nested_diag(trade, "entry_context", "rsi", 55.2)
        >>> # Results in: trade.diagnostics["entry_context"] = {"vwap": 2650.5, "rsi": 55.2}
    """
    if not hasattr(trade, "diagnostics") or trade.diagnostics is None:
        trade.diagnostics = {}
    
    # Get or create section dict
    section_dict = trade.diagnostics.get(section, {})
    section_dict[key] = value
    trade.diagnostics[section] = section_dict

