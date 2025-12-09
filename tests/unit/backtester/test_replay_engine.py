"""Tests for historical replay engine with SOP validators."""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from backtester.replay_engine import ReplayEngine


class TestReplayEngine:
    """Tests for ReplayEngine incremental validation."""

    @pytest.fixture
    def sample_data(self):
        """Generate sample GC and DXY DataFrames for testing."""
        base_time = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        timestamps = [base_time + timedelta(minutes=i) for i in range(100)]

        gc_df = pd.DataFrame(
            {
                "open": [2000.0 + i * 0.5 for i in range(100)],
                "high": [2002.0 + i * 0.5 for i in range(100)],
                "low": [1998.0 + i * 0.5 for i in range(100)],
                "close": [2001.0 + i * 0.5 for i in range(100)],
                "volume": [1000.0 + i * 10 for i in range(100)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        dxy_df = pd.DataFrame(
            {
                "open": [100.0 - i * 0.02 for i in range(100)],
                "high": [100.5 - i * 0.02 for i in range(100)],
                "low": [99.5 - i * 0.02 for i in range(100)],
                "close": [100.0 - i * 0.02 for i in range(100)],
                "volume": [1000.0 for _ in range(100)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        return gc_df, dxy_df

    def test_replay_yields_features_and_context(self, sample_data):
        """Test that replay yields features and validation context."""
        gc_df, dxy_df = sample_data
        engine = ReplayEngine(timeframe="1m")

        results = list(engine.replay(gc_df, dxy_df))

        assert len(results) > 0
        features, context = results[0]
        assert isinstance(features, pd.Series)
        assert isinstance(context, dict)
        assert "timestamp" in features
        assert "session_ok" in context or "session_result" in context

    def test_replay_produces_validation_flags(self, sample_data):
        """Test that replay produces validation flags per candle."""
        gc_df, dxy_df = sample_data
        engine = ReplayEngine(timeframe="1m")

        results = list(engine.replay(gc_df, dxy_df))

        # Check that validation context contains expected keys
        for _features, context in results:
            # Should have session validation
            assert "session_ok" in context or "session_result" in context
            # Should have guardrail result if validation enabled
            if engine.enable_validation:
                assert "guardrail_result" in context
                assert "behavior_state" in context

    def test_replay_no_lookahead_bias(self, sample_data):
        """Test that replay doesn't use future data (no lookahead)."""
        gc_df, dxy_df = sample_data

        # Modify last candle
        gc_df_modified = gc_df.copy()
        last_idx = -1
        gc_df_modified.iloc[last_idx, gc_df_modified.columns.get_loc("close")] = (
            gc_df_modified.iloc[last_idx]["low"] + 0.5
        )

        engine1 = ReplayEngine(timeframe="1m")
        engine2 = ReplayEngine(timeframe="1m")

        results_original = list(engine1.replay(gc_df, dxy_df))
        results_modified = list(engine2.replay(gc_df_modified, dxy_df))

        # All features except last should be identical
        # (not affected by future change)
        for i in range(len(results_original) - 2):
            features_orig, _ = results_original[i]
            features_mod, _ = results_modified[i]

            # Features should not be affected by future data
            assert features_orig["close"] == features_mod["close"]
            assert features_orig["vwap"] == features_mod["vwap"]

    def test_record_trade_outcome_updates_state(self, sample_data):
        """Test that recording trade outcomes updates behavior state."""
        gc_df, dxy_df = sample_data
        engine = ReplayEngine(timeframe="1m", enable_validation=True)

        # Get initial state
        initial_state = engine.behavior_state
        assert initial_state is not None
        assert initial_state.state.consecutive_losses == 0

        # Record a loss
        engine.record_trade_outcome(won=False)
        assert initial_state.state.consecutive_losses == 1

        # Record another loss
        engine.record_trade_outcome(won=False)
        assert initial_state.state.consecutive_losses == 2

        # Record a win (should reset)
        engine.record_trade_outcome(won=True)
        assert initial_state.state.consecutive_losses == 0

    def test_record_trade_outcome_disabled_when_validation_off(self, sample_data):
        """Test that recording outcomes is skipped when validation disabled."""
        gc_df, dxy_df = sample_data
        engine = ReplayEngine(timeframe="1m", enable_validation=False)

        # Should not raise error
        engine.record_trade_outcome(won=False)
        assert engine.behavior_state is None

    def test_get_validation_context_at_timestamp(self, sample_data):
        """Test getting validation context for specific timestamp."""
        gc_df, dxy_df = sample_data
        engine = ReplayEngine(timeframe="1m")

        target_timestamp = gc_df.index[50]
        context = engine.get_validation_context_at_timestamp(
            gc_df, dxy_df, target_timestamp
        )

        assert context is not None
        assert isinstance(context, dict)

    def test_get_validation_context_nonexistent_timestamp(self, sample_data):
        """Test getting context for nonexistent timestamp returns None."""
        gc_df, dxy_df = sample_data
        engine = ReplayEngine(timeframe="1m")

        nonexistent = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)
        context = engine.get_validation_context_at_timestamp(gc_df, dxy_df, nonexistent)

        assert context is None

    def test_replay_state_evolves_correctly(self, sample_data):
        """Test that state evolves correctly during replay."""
        gc_df, dxy_df = sample_data
        engine = ReplayEngine(timeframe="1m", enable_validation=True)

        # Replay and record outcomes
        list(engine.replay(gc_df, dxy_df))

        # Record some trade outcomes
        engine.record_trade_outcome(won=False)
        engine.record_trade_outcome(won=False)

        # Check state evolved
        state = engine.behavior_state
        assert state is not None
        assert state.state.consecutive_losses == 2

    def test_replay_validation_context_consistent(self, sample_data):
        """Test that validation context is consistent across replay."""
        gc_df, dxy_df = sample_data
        engine1 = ReplayEngine(timeframe="1m")
        engine2 = ReplayEngine(timeframe="1m")

        results1 = list(engine1.replay(gc_df, dxy_df))
        results2 = list(engine2.replay(gc_df, dxy_df))

        # Should produce same number of results
        assert len(results1) == len(results2)

        # Validation contexts should be consistent
        for (f1, c1), (f2, c2) in zip(results1, results2, strict=False):
            assert f1["timestamp"] == f2["timestamp"]
            # Session validation should be consistent
            assert c1.get("session_ok") == c2.get("session_ok")


class TestReplayEngineStateEvolution:
    """Tests for state evolution during replay."""

    @pytest.fixture
    def september_data(self):
        """Generate data for September (1-loss halt)."""
        base_time = datetime(2025, 9, 15, 10, 0, tzinfo=UTC)
        timestamps = [base_time + timedelta(minutes=i) for i in range(50)]

        gc_df = pd.DataFrame(
            {
                "open": [2000.0 + i * 0.5 for i in range(50)],
                "high": [2002.0 + i * 0.5 for i in range(50)],
                "low": [1998.0 + i * 0.5 for i in range(50)],
                "close": [2001.0 + i * 0.5 for i in range(50)],
                "volume": [1000.0 for _ in range(50)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        dxy_df = pd.DataFrame(
            {
                "open": [100.0 for _ in range(50)],
                "high": [100.5 for _ in range(50)],
                "low": [99.5 for _ in range(50)],
                "close": [100.0 for _ in range(50)],
                "volume": [1000.0 for _ in range(50)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        return gc_df, dxy_df

    def test_september_max_losses_is_one(self, september_data):
        """Test that September has max_losses=1 in session constraints."""
        gc_df, dxy_df = september_data
        engine = ReplayEngine(timeframe="1m", enable_validation=True)

        results = list(engine.replay(gc_df, dxy_df))

        # Check that September constraints have max_losses=1
        for features, context in results:
            constraints = context.get("session_constraints")
            if constraints:
                # September should have max_losses=1
                if features["timestamp"].month == 9:
                    assert constraints.max_losses == 1

    @pytest.fixture
    def january_data(self):
        """Generate data for January (2-loss halt)."""
        base_time = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        timestamps = [base_time + timedelta(minutes=i) for i in range(50)]

        gc_df = pd.DataFrame(
            {
                "open": [2000.0 + i * 0.5 for i in range(50)],
                "high": [2002.0 + i * 0.5 for i in range(50)],
                "low": [1998.0 + i * 0.5 for i in range(50)],
                "close": [2001.0 + i * 0.5 for i in range(50)],
                "volume": [1000.0 for _ in range(50)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        dxy_df = pd.DataFrame(
            {
                "open": [100.0 for _ in range(50)],
                "high": [100.5 for _ in range(50)],
                "low": [99.5 for _ in range(50)],
                "close": [100.0 for _ in range(50)],
                "volume": [1000.0 for _ in range(50)],
            },
            index=pd.DatetimeIndex(timestamps, name="timestamp"),
        )

        return gc_df, dxy_df

    def test_other_months_max_losses_is_two(self, january_data):
        """Test that other months have max_losses=2."""
        gc_df, dxy_df = january_data
        engine = ReplayEngine(timeframe="1m", enable_validation=True)

        results = list(engine.replay(gc_df, dxy_df))

        # Check that January (non-September) has max_losses=2
        for features, context in results:
            constraints = context.get("session_constraints")
            if constraints:
                # January should have max_losses=2
                if features["timestamp"].month == 1:
                    assert constraints.max_losses == 2
