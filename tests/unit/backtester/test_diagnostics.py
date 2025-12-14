"""Unit tests for diagnostics helpers.

Tests:
- add_diag() function
- add_nested_diag() function
- Trade diagnostics field serialization/deserialization
- JSON roundtrip with diagnostics
"""

from datetime import datetime

import pytest

from backtester.diagnostics import add_diag, add_nested_diag
from backtester.entry_model import EntryExecution
from backtester.trade import Trade, from_dict, to_dict
from common.types import Candle
from rule_engine.signal import Signal


@pytest.fixture
def sample_trade():
    """Create a sample trade for testing."""
    # Create minimal signal
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 0),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={"vwap": 10.0, "structure": 10.0},
        rationale="Strong reclaim with HTF alignment",
        validation_flags={"session_valid": True},
        enforcer_tier="EarlyMild",
    )

    # Create entry execution
    entry = EntryExecution(
        signal_timestamp=datetime(2025, 11, 1, 10, 0),
        entry_timestamp=datetime(2025, 11, 1, 10, 1),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    # Create trade
    trade = Trade(
        trade_id="test-123",
        symbol="GC",
        timeframe="1m",
        entry_execution=entry,
        entry_timestamp=datetime(2025, 11, 1, 10, 1),
        entry_price=2650.0,
        direction="long",
        setup_type="VWAP_RECLAIM",
        stop_loss=2645.0,
        take_profit=2665.0,
        sl_rationale="Below confirmation candle",
        tp_rationale="3R continuation",
        risk_amount=5.0,
        reward_amount=15.0,
        r_multiple=3.0,
        contracts=1,
        exit_timestamp=None,
        exit_price=None,
        exit_reason=None,
        pnl=None,
        pnl_percent=None,
        r_realized=None,
        pnl_dollars=None,
        pnl_net=None,
        slippage_cost=None,
        commission_cost=None,
        status="OPEN",
        duration_bars=None,
        invalidation_triggered=False,
        ignore_first_retest_bar=True,
        diagnostics={},
    )

    return trade


def test_add_diag_works_with_empty_diagnostics(sample_trade):
    """Test that add_diag works with empty diagnostics dict."""
    # Verify diagnostics starts empty (default_factory)
    assert sample_trade.diagnostics == {}

    # Add diagnostic
    add_diag(sample_trade, "test_key", "test_value")

    # Verify diagnostic was added
    assert sample_trade.diagnostics["test_key"] == "test_value"


def test_add_diag_adds_top_level_key(sample_trade):
    """Test that add_diag adds top-level key-value pair."""
    add_diag(sample_trade, "entry_method", "next_bar_open")
    add_diag(sample_trade, "slippage_ticks", 2.5)

    assert sample_trade.diagnostics["entry_method"] == "next_bar_open"
    assert sample_trade.diagnostics["slippage_ticks"] == 2.5


def test_add_nested_diag_creates_section(sample_trade):
    """Test that add_nested_diag creates section if it doesn't exist."""
    add_nested_diag(sample_trade, "entry_context", "vwap", 2650.5)

    assert "entry_context" in sample_trade.diagnostics
    assert sample_trade.diagnostics["entry_context"]["vwap"] == 2650.5


def test_add_nested_diag_adds_to_existing_section(sample_trade):
    """Test that add_nested_diag adds to existing section."""
    add_nested_diag(sample_trade, "entry_context", "vwap", 2650.5)
    add_nested_diag(sample_trade, "entry_context", "rsi", 55.2)
    add_nested_diag(sample_trade, "entry_context", "atr_5", 3.5)

    assert len(sample_trade.diagnostics["entry_context"]) == 3
    assert sample_trade.diagnostics["entry_context"]["vwap"] == 2650.5
    assert sample_trade.diagnostics["entry_context"]["rsi"] == 55.2
    assert sample_trade.diagnostics["entry_context"]["atr_5"] == 3.5


def test_add_nested_diag_multiple_sections(sample_trade):
    """Test that add_nested_diag can create multiple sections."""
    add_nested_diag(sample_trade, "entry_context", "vwap", 2650.5)
    add_nested_diag(sample_trade, "sl_hit_context", "sl_level", 2645.0)
    add_nested_diag(sample_trade, "tp_hit_context", "tp_level", 2665.0)

    assert "entry_context" in sample_trade.diagnostics
    assert "sl_hit_context" in sample_trade.diagnostics
    assert "tp_hit_context" in sample_trade.diagnostics


def test_trade_diagnostics_serialization(sample_trade):
    """Test that diagnostics are serialized in to_dict()."""
    # Add diagnostics
    add_nested_diag(sample_trade, "entry_context", "vwap", 2650.5)
    add_nested_diag(sample_trade, "entry_context", "rsi", 55.2)
    add_nested_diag(sample_trade, "sl_hit_context", "bars_elapsed", 7)

    # Serialize
    trade_dict = to_dict(sample_trade)

    # Verify diagnostics are present
    assert "diagnostics" in trade_dict
    assert "entry_context" in trade_dict["diagnostics"]
    assert trade_dict["diagnostics"]["entry_context"]["vwap"] == 2650.5
    assert trade_dict["diagnostics"]["entry_context"]["rsi"] == 55.2
    assert trade_dict["diagnostics"]["sl_hit_context"]["bars_elapsed"] == 7


def test_trade_diagnostics_deserialization(sample_trade):
    """Test that diagnostics are deserialized in from_dict()."""
    # Add diagnostics
    add_nested_diag(sample_trade, "entry_context", "vwap", 2650.5)
    add_nested_diag(sample_trade, "invalidation_context", "type", "vwap")

    # Serialize and deserialize
    trade_dict = to_dict(sample_trade)
    reconstructed = from_dict(trade_dict)

    # Verify diagnostics survived roundtrip
    assert reconstructed.diagnostics is not None
    assert "entry_context" in reconstructed.diagnostics
    assert reconstructed.diagnostics["entry_context"]["vwap"] == 2650.5
    assert reconstructed.diagnostics["invalidation_context"]["type"] == "vwap"


def test_trade_diagnostics_roundtrip_empty(sample_trade):
    """Test that empty diagnostics roundtrip correctly."""
    # Don't add any diagnostics (should default to empty dict)

    # Serialize and deserialize
    trade_dict = to_dict(sample_trade)
    reconstructed = from_dict(trade_dict)

    # Verify empty diagnostics
    assert reconstructed.diagnostics == {}


def test_trade_diagnostics_roundtrip_backward_compat():
    """Test that trades without diagnostics field (old format) load correctly."""
    # Create minimal trade dict without diagnostics
    trade_dict = {
        "trade_id": "test-123",
        "symbol": "GC",
        "timeframe": "1m",
        "entry_execution": {
            "signal_timestamp": "2025-11-01T10:00:00",
            "entry_timestamp": "2025-11-01T10:01:00",
            "entry_price": 2650.0,
            "executed": True,
            "rejection_reason": None,
            "signal": {
                "timestamp": "2025-11-01T10:00:00",
                "symbol": "GC",
                "timeframe": "1m",
                "direction": "long",
                "setup_type": "VWAP_RECLAIM",
                "htf_bias": "bullish",
                "score": 8.5,
                "confidence": "A+",
                "factors": {},
                "rationale": "Test",
                "validation_flags": {},
                "enforcer_tier": "EarlyMild",
            },
        },
        "entry_timestamp": "2025-11-01T10:01:00",
        "entry_price": 2650.0,
        "direction": "long",
        "setup_type": "VWAP_RECLAIM",
        "stop_loss": 2645.0,
        "take_profit": 2665.0,
        "sl_rationale": "Below confirmation",
        "tp_rationale": "3R",
        "risk_amount": 5.0,
        "reward_amount": 15.0,
        "r_multiple": 3.0,
        "contracts": 1,
        "exit_timestamp": None,
        "exit_price": None,
        "exit_reason": None,
        "pnl": None,
        "pnl_percent": None,
        "r_realized": None,
        "pnl_dollars": None,
        "pnl_net": None,
        "slippage_cost": None,
        "commission_cost": None,
        "status": "OPEN",
        "duration_bars": None,
        "invalidation_triggered": False,
        "ignore_first_retest_bar": False,
        # NOTE: No "diagnostics" field - old format
    }

    # Deserialize (should default to empty dict)
    reconstructed = from_dict(trade_dict)

    # Verify empty diagnostics
    assert reconstructed.diagnostics == {}


def test_complex_diagnostics_structure(sample_trade):
    """Test complex nested diagnostics structure."""
    # Add entry context
    add_nested_diag(sample_trade, "entry_context", "structure_label", "HH")
    add_nested_diag(sample_trade, "entry_context", "vwap", 2650.5)
    add_nested_diag(
        sample_trade,
        "entry_context",
        "rejection_candle_raw",
        {"wick_penetration": 0.8, "close_vs_vwap_diff": 2.5},
    )

    # Add per-bar tracking
    for i in range(1, 4):
        add_nested_diag(
            sample_trade,
            "rejection_during_trade",
            f"bar_{i}",
            {"wick_penetration": 0.5 + i * 0.1, "close_vs_vwap_diff": 1.0 + i},
        )

    # Add invalidation context
    add_nested_diag(sample_trade, "invalidation_context", "type", "vwap")
    add_nested_diag(sample_trade, "invalidation_context", "reason", "Close below VWAP")

    # Serialize and verify structure
    trade_dict = to_dict(sample_trade)

    assert len(trade_dict["diagnostics"]) == 3
    assert "entry_context" in trade_dict["diagnostics"]
    assert "rejection_during_trade" in trade_dict["diagnostics"]
    assert "invalidation_context" in trade_dict["diagnostics"]

    # Verify nested structures
    assert isinstance(
        trade_dict["diagnostics"]["entry_context"]["rejection_candle_raw"], dict
    )
    assert len(trade_dict["diagnostics"]["rejection_during_trade"]) == 3

    # Verify roundtrip
    reconstructed = from_dict(trade_dict)
    assert reconstructed.diagnostics["entry_context"]["structure_label"] == "HH"
    assert (
        reconstructed.diagnostics["rejection_during_trade"]["bar_1"]["wick_penetration"]
        == 0.6
    )


def test_add_diag_handles_none_diagnostics(sample_trade):
    """Test that add_diag handles None diagnostics (frozen dataclass edge case)."""
    # Simulate edge case where diagnostics is None (shouldn't happen in practice,
    # but could occur with malformed data or manual object manipulation)
    object.__setattr__(sample_trade, "diagnostics", None)

    # Should not raise FrozenInstanceError
    add_diag(sample_trade, "test_key", "test_value")

    # Verify diagnostic was added
    assert sample_trade.diagnostics is not None
    assert sample_trade.diagnostics["test_key"] == "test_value"


def test_add_nested_diag_handles_none_diagnostics(sample_trade):
    """Test that add_nested_diag handles None diagnostics (frozen dataclass edge case)."""
    # Simulate edge case where diagnostics is None
    object.__setattr__(sample_trade, "diagnostics", None)

    # Should not raise FrozenInstanceError
    add_nested_diag(sample_trade, "entry_context", "vwap", 2650.5)

    # Verify diagnostic was added
    assert sample_trade.diagnostics is not None
    assert sample_trade.diagnostics["entry_context"]["vwap"] == 2650.5
