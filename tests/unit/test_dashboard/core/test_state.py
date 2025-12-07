"""Unit tests for DashboardState.

Tests the immutable state container and its update methods.
"""

from datetime import datetime, timezone

import pandas as pd
import pytest

from dashboard.core.state import DashboardState, PriceBar


class TestPriceBar:
    """Tests for PriceBar dataclass."""

    def test_create_price_bar(self):
        """Test creating a PriceBar."""
        timestamp = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        bar = PriceBar(
            timestamp=timestamp,
            open=2650.0,
            high=2655.0,
            low=2645.0,
            close=2652.0,
            volume=1000.0,
        )

        assert bar.timestamp == timestamp
        assert bar.open == 2650.0
        assert bar.high == 2655.0
        assert bar.low == 2645.0
        assert bar.close == 2652.0
        assert bar.volume == 1000.0

    def test_price_bar_is_immutable(self):
        """Test that PriceBar is immutable (frozen)."""
        bar = PriceBar(
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
            open=100.0,
            high=110.0,
            low=90.0,
            close=105.0,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            bar.close = 200.0


class TestDashboardState:
    """Tests for DashboardState dataclass."""

    def test_create_empty_state(self):
        """Test creating empty state."""
        state = DashboardState.create_empty()

        assert state.timestamp is None
        assert state.features.empty
        assert state.htf_bias is None
        assert state.current_signal is None
        assert state.is_simulation_running is False
        assert state.is_paused is False
        assert state.simulation_progress == 0.0
        assert len(state.price_history_gc) == 0
        assert len(state.price_history_dxy) == 0

    def test_update_returns_new_state(self):
        """Test that update() returns a new state without modifying original."""
        original = DashboardState.create_empty()
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        updated = original.update(
            timestamp=timestamp,
            is_simulation_running=True,
            simulation_progress=0.5,
        )

        # Original unchanged
        assert original.timestamp is None
        assert original.is_simulation_running is False
        assert original.simulation_progress == 0.0

        # Updated has new values
        assert updated.timestamp == timestamp
        assert updated.is_simulation_running is True
        assert updated.simulation_progress == 0.5

    def test_with_price_bars(self):
        """Test adding price bars to history."""
        state = DashboardState.create_empty()

        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        gc_bar = PriceBar(
            timestamp=timestamp,
            open=2650.0,
            high=2655.0,
            low=2645.0,
            close=2652.0,
            volume=1000.0,
        )
        dxy_bar = PriceBar(
            timestamp=timestamp,
            open=104.0,
            high=104.5,
            low=103.5,
            close=104.2,
        )

        new_state = state.with_price_bars(gc_bar, dxy_bar)

        # Original unchanged
        assert len(state.price_history_gc) == 0
        assert len(state.price_history_dxy) == 0

        # New state has bars
        assert len(new_state.price_history_gc) == 1
        assert len(new_state.price_history_dxy) == 1
        assert new_state.price_history_gc[0] == gc_bar
        assert new_state.price_history_dxy[0] == dxy_bar

    def test_price_history_limit(self):
        """Test that price history respects max_history_size."""
        state = DashboardState.create_empty()
        # Override max_history_size for test
        state = state.update(max_history_size=5)

        # Add more bars than max
        for i in range(10):
            timestamp = datetime(2025, 1, 1, 10, i, tzinfo=timezone.utc)
            gc_bar = PriceBar(
                timestamp=timestamp,
                open=2650.0 + i,
                high=2655.0 + i,
                low=2645.0 + i,
                close=2652.0 + i,
            )
            dxy_bar = PriceBar(
                timestamp=timestamp,
                open=104.0,
                high=104.5,
                low=103.5,
                close=104.2,
            )
            state = state.with_price_bars(gc_bar, dxy_bar)

        # Should only have last 5 bars
        assert len(state.price_history_gc) == 5
        assert len(state.price_history_dxy) == 5

        # First bar should be from index 5 (minute 5)
        assert state.price_history_gc[0].timestamp.minute == 5

    def test_get_price_history_df(self):
        """Test converting price history to DataFrame."""
        state = DashboardState.create_empty()

        # Add some bars
        for i in range(3):
            timestamp = datetime(2025, 1, 1, 10, i, tzinfo=timezone.utc)
            gc_bar = PriceBar(
                timestamp=timestamp,
                open=2650.0 + i,
                high=2655.0 + i,
                low=2645.0 + i,
                close=2652.0 + i,
                volume=float(1000 + i),
            )
            dxy_bar = PriceBar(
                timestamp=timestamp,
                open=104.0 + i * 0.1,
                high=104.5,
                low=103.5,
                close=104.2,
            )
            state = state.with_price_bars(gc_bar, dxy_bar)

        gc_df = state.get_price_history_gc_df()
        dxy_df = state.get_price_history_dxy_df()

        assert len(gc_df) == 3
        assert len(dxy_df) == 3
        assert "open" in gc_df.columns
        assert "close" in gc_df.columns
        assert "volume" in gc_df.columns
        assert "timestamp" in gc_df.columns

    def test_to_dict(self):
        """Test serializing state to dict."""
        state = DashboardState.create_empty()
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        state = state.update(
            timestamp=timestamp,
            is_simulation_running=True,
            is_paused=True,
            pause_reason="Test pause",
            simulation_speed=5.0,
            simulation_progress=0.25,
        )

        d = state.to_dict()

        assert d["timestamp"] == timestamp.isoformat()
        assert d["is_simulation_running"] is True
        assert d["is_paused"] is True
        assert d["pause_reason"] == "Test pause"
        assert d["simulation_speed"] == 5.0
        assert d["simulation_progress"] == 0.25

    def test_state_is_hashable(self):
        """Test that state is hashable (can be used in sets/dicts)."""
        state1 = DashboardState.create_empty()
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        state2 = state1.update(timestamp=timestamp)

        # Should be hashable
        hash1 = hash(state1)
        hash2 = hash(state2)

        assert isinstance(hash1, int)
        assert isinstance(hash2, int)
        assert hash1 != hash2  # Different timestamps = different hashes

    def test_state_equality_considers_all_fields(self):
        """Test that equality considers all fields, not just timestamp."""
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        # Two states with same timestamp but different features should NOT be equal
        state1 = DashboardState.create_empty().update(
            timestamp=timestamp,
            features=pd.Series({"vwap": 2650.0, "rsi": 50.0}),
        )
        state2 = DashboardState.create_empty().update(
            timestamp=timestamp,
            features=pd.Series({"vwap": 2700.0, "rsi": 70.0}),
        )

        assert state1 != state2
        assert hash(state1) != hash(state2)

        # Two states with timestamp=None but different fields should NOT be equal
        state3 = DashboardState.create_empty().update(is_simulation_running=True)
        state4 = DashboardState.create_empty().update(is_simulation_running=False)

        assert state3 != state4
        assert hash(state3) != hash(state4)

        # Two states with all fields the same SHOULD be equal
        state5 = DashboardState.create_empty().update(
            timestamp=timestamp,
            features=pd.Series({"vwap": 2650.0}),
            is_simulation_running=True,
        )
        state6 = DashboardState.create_empty().update(
            timestamp=timestamp,
            features=pd.Series({"vwap": 2650.0}),
            is_simulation_running=True,
        )

        assert state5 == state6
        assert hash(state5) == hash(state6)

    def test_state_equality_with_none_values(self):
        """Test equality handling of None values in optional fields."""
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        # States with None HTFBias should be equal if all other fields match
        state1 = DashboardState.create_empty().update(
            timestamp=timestamp,
            htf_bias=None,
        )
        state2 = DashboardState.create_empty().update(
            timestamp=timestamp,
            htf_bias=None,
        )
        assert state1 == state2
        assert hash(state1) == hash(state2)

        # States with None vs non-None HTFBias should not be equal
        from rule_engine.htf.types import HTFBias

        state3 = DashboardState.create_empty().update(
            timestamp=timestamp,
            htf_bias=HTFBias(
                bias="bullish",
                direction="long",
                score=8.0,
                confidence="high",
            ),
        )
        assert state1 != state3
        assert hash(state1) != hash(state3)

        # States with None session_constraints should be equal
        state4 = DashboardState.create_empty().update(
            timestamp=timestamp,
            session_constraints=None,
        )
        state5 = DashboardState.create_empty().update(
            timestamp=timestamp,
            session_constraints=None,
        )
        assert state4 == state5
        assert hash(state4) == hash(state5)

    def test_state_equality_with_empty_series(self):
        """Test equality handling of empty pandas Series."""
        timestamp = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        # Empty series should be equal
        state1 = DashboardState.create_empty().update(
            timestamp=timestamp,
            features=pd.Series(dtype=float),
        )
        state2 = DashboardState.create_empty().update(
            timestamp=timestamp,
            features=pd.Series(dtype=float),
        )
        assert state1 == state2
        assert hash(state1) == hash(state2)

        # Empty vs non-empty should not be equal
        state3 = DashboardState.create_empty().update(
            timestamp=timestamp,
            features=pd.Series({"vwap": 2650.0}),
        )
        assert state1 != state3
        assert hash(state1) != hash(state3)

