"""Minimal types for streaming execution."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TradeRecord:
    """Minimal trade record for invalidation checking.

    This is a lightweight version of the full Trade dataclass from backtester,
    containing only fields needed for invalidation logic in streaming mode.
    """

    trade_id: str
    signal_id: str  # Source signal ID for correlation
    symbol: str
    direction: str  # "long" | "short"
    setup_type: str  # "VWAP_RECLAIM" | "VWAP_FADE" | "DXY_CONTINUATION"
    entry_price: float
    sl_price: float
    tp_price: float
    risk_amount: float
    reward_amount: float
    entry_timestamp: datetime
    exit_timestamp: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    pnl: float | None = None

    # State fields for service restart recovery
    entry_bar_idx: int | None = None  # Bar index when trade was entered
    reached_1r: bool = False  # Whether trade achieved +1R protection

    # Risk in price points (CRITICAL for correct R calculations)
    # Must be set at entry: risk_points = abs(entry_price - sl_price)
    risk_points: float | None = None

    # Trade management state (for DXY_CONTINUATION partial profit / de-risk)
    partial_taken: bool = False  # 40% taken at +1R
    breakeven_set: bool = False  # Legacy: SL moved to entry (kept for backward compat)
    current_sl_price: float | None = None  # Adjusted SL (None = use original sl_price)

    # BE tracking with explicit details (Phase 2.0 - separate from partial action)
    be_set: bool = False  # Whether BE was explicitly set (separate event from partial)
    be_price: float | None = None  # BE level with buffer (entry + 0.1R for longs)
    be_set_bar_idx: int | None = None  # Bar when BE was set
    tp1_hit_bar_idx: int | None = None  # Bar when +1R was hit

    # Phase-2: Runner unlock state (conditional runner after TP1)
    runner_unlocked: bool = False  # Whether runner is unlocked for TP2
    runner_unlock_mode: str | None = None  # "micro_bos" (Mode A), "hold_impulse" (Fallback A)
    runner_unlock_bar_idx: int | None = None  # Bar when runner was unlocked
    runner_exited_at_market: bool = False  # True if closed at market (unlock failed)
    tp2_price: float | None = None  # TP2 target (from signal, capped at 4R)

    # Phase-2: Enhanced runner logging (Section 9 of spec)
    runner_invalidation_reason: str | None = None  # "chop", "htf_conflict", "dxy_misaligned"
    bars_to_unlock: int | None = None  # Bars from TP1 to unlock (for metrics)
