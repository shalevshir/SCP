"""Unit tests for SimulationEngine.

Tests the core simulation engine including warmup and auto-pause functionality.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from common.types import Candle
from dashboard.core.data_stream import DataStream
from dashboard.core.engine import SimulationEngine
from rule_engine.signal import Signal


@pytest.fixture
def mock_data_stream():
    """Create a mock data stream with sample data."""
    stream = MagicMock(spec=DataStream)
    stream.warmup_bars = 0
    stream.stream_start_index = 0
    stream.current_index = 0

    # Create sample candles
    candles = []
    for i in range(5):
        timestamp = datetime(2025, 1, 1, 10, i, 0, tzinfo=UTC)
        gc = Candle(
            timestamp=timestamp,
            open=2650.0 + i,
            high=2655.0 + i,
            low=2645.0 + i,
            close=2652.0 + i,
            volume=float(1000 + i * 100),
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        dxy = Candle(
            timestamp=timestamp,
            open=104.0,
            high=104.5,
            low=103.5,
            close=104.2,
            volume=0.0,
            symbol="DXY",
            timeframe="1m",
            source="TEST",
        )
        candles.append((gc, dxy))

    # Set up advance() to return candles sequentially
    stream.advance.side_effect = candles + [None]
    stream.has_more.side_effect = [True] * 5 + [False]
    stream.get_progress.return_value = 0.5
    stream.get_warmup_candles.return_value = iter([])

    return stream


@pytest.fixture
def mock_validation_engine():
    """Create a mock validation engine."""
    engine = MagicMock()
    engine.validate.return_value = {"valid": True}
    return engine


@pytest.fixture
def mock_session_validator():
    """Create a mock session validator."""
    validator = MagicMock()
    result = MagicMock()
    result.session_ok = True
    result.constraints = MagicMock()
    result.constraints.name = "Early Mild"
    result.constraints.min_signal_score = 8.0
    validator.evaluate.return_value = result
    return validator


class TestSimulationEngine:
    """Tests for SimulationEngine class."""

    def test_initialization(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test engine initialization."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
            auto_pause_on_a_plus=True,
            speed_multiplier=5.0,
        )

        assert engine.auto_pause_on_a_plus is True
        assert engine.speed_multiplier == 5.0
        assert engine.state.simulation_speed == 5.0
        assert engine.state.is_simulation_running is False
        assert engine.state.is_paused is False

    def test_auto_pause_enabled_by_default(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that auto-pause is enabled by default."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        assert engine.auto_pause_on_a_plus is True

    def test_auto_pause_can_be_disabled(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that auto-pause can be disabled."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
            auto_pause_on_a_plus=False,
        )

        assert engine.auto_pause_on_a_plus is False

    def test_tick_processes_candle(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that tick() processes one candle."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        # Process one tick
        with patch.object(engine.htf_calculator, "update") as mock_update:
            mock_update.return_value = None
            with patch.object(
                engine.htf_calculator, "get_current_features_15m"
            ) as mock_features:
                mock_features.return_value = pd.Series(dtype=object)

                engine.tick()

                # Verify data stream was advanced
                mock_data_stream.advance.assert_called_once()

    def test_tick_updates_state_timestamp(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that tick() updates state timestamp."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        with patch.object(engine.htf_calculator, "update") as mock_update:
            mock_update.return_value = None
            with patch.object(
                engine.htf_calculator, "get_current_features_15m"
            ) as mock_features:
                mock_features.return_value = pd.Series(dtype=object)

                engine.tick()

                # State should have timestamp from first candle
                assert engine.state.timestamp is not None
                assert engine.state.timestamp.minute == 0

    def test_manual_pause(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test manual pause functionality."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        engine.pause("Test pause reason")

        assert engine.state.is_paused is True
        assert engine.state.pause_reason == "Test pause reason"

    def test_resume(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test resume functionality."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        # Pause first
        engine.pause("Test pause")
        assert engine.state.is_paused is True

        # Resume
        engine.resume()
        assert engine.state.is_paused is False
        assert engine.state.pause_reason is None
        assert engine.state.paused_at_signal is None

    def test_set_speed(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test setting simulation speed."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        engine.set_speed(10.0)

        assert engine.speed_multiplier == 10.0
        assert engine.state.simulation_speed == 10.0

    def test_init_speed_validation(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that invalid speed_multiplier in __init__ raises error."""
        with pytest.raises(ValueError, match="Speed multiplier must be positive"):
            SimulationEngine(
                data_stream=mock_data_stream,
                validation_engine=mock_validation_engine,
                session_validator=mock_session_validator,
                speed_multiplier=0,
            )

        with pytest.raises(ValueError, match="Speed multiplier must be positive"):
            SimulationEngine(
                data_stream=mock_data_stream,
                validation_engine=mock_validation_engine,
                session_validator=mock_session_validator,
                speed_multiplier=-1.0,
            )

    def test_set_speed_validation(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that invalid speed raises error."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        with pytest.raises(ValueError, match="Speed multiplier must be positive"):
            engine.set_speed(0)

        with pytest.raises(ValueError, match="Speed multiplier must be positive"):
            engine.set_speed(-1.0)

    def test_state_is_thread_safe(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that state access is thread-safe."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        # Accessing state should work
        state = engine.state
        assert state is not None

        # Multiple accesses should return current state
        state2 = engine.state
        assert state.timestamp == state2.timestamp

    def test_step_works_when_paused(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that step() works even when paused."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        # Pause the engine
        engine.pause("Test")

        with patch.object(engine.htf_calculator, "update") as mock_update:
            mock_update.return_value = None
            with patch.object(
                engine.htf_calculator, "get_current_features_15m"
            ) as mock_features:
                mock_features.return_value = pd.Series(dtype=object)

                # Step should still work
                engine.step()

                # Verify data was advanced
                mock_data_stream.advance.assert_called_once()

    def test_warmup_processes_warmup_candles(
        self, mock_validation_engine, mock_session_validator
    ):
        """Test that warmup processes all warmup candles."""
        # Create a real-ish mock with warmup data
        stream = MagicMock(spec=DataStream)
        stream.warmup_bars = 5
        stream.stream_start_index = 5

        # Create warmup candles
        warmup_candles = []
        for i in range(5):
            timestamp = datetime(2025, 1, 1, 10, i, 0, tzinfo=UTC)
            gc = Candle(
                timestamp=timestamp,
                open=2650.0,
                high=2655.0,
                low=2645.0,
                close=2652.0,
                volume=1000.0,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
            dxy = Candle(
                timestamp=timestamp,
                open=104.0,
                high=104.5,
                low=103.5,
                close=104.2,
                volume=0.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            )
            warmup_candles.append((gc, dxy))

        stream.get_warmup_candles.return_value = iter(warmup_candles)
        stream.get_candle_at.return_value = warmup_candles[-1]

        engine = SimulationEngine(
            data_stream=stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
        )

        with patch.object(engine.htf_calculator, "update") as mock_update:
            mock_update.return_value = None
            with patch.object(engine.htf_calculator, "get_current_bias") as mock_bias:
                mock_bias.return_value = None
                with patch.object(
                    engine.htf_calculator, "get_current_features_15m"
                ) as mock_features:
                    mock_features.return_value = pd.Series(dtype=object)

                    engine.warmup()

                    # Verify HTF calculator was called for each warmup candle
                    assert mock_update.call_count == 5

    def test_auto_pause_triggers_on_a_plus_signal(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that auto-pause triggers when A+ signal is generated."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
            auto_pause_on_a_plus=True,
        )

        # Create an A+ signal
        a_plus_signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure": 2.0},
            rationale="Test signal",
            validation_flags={"session_ok": True},
            enforcer_tier="Early Mild",
        )

        # Mock generate_signal to return A+ signal
        with patch.object(engine, "_generate_signal", return_value=a_plus_signal):
            with patch.object(engine.htf_calculator, "update") as mock_update:
                # Return a valid HTF bias so signal generation is attempted
                mock_htf = MagicMock()
                mock_htf.bias = "bullish"
                mock_update.return_value = mock_htf

                with patch.object(
                    engine.htf_calculator, "get_current_features_15m"
                ) as mock_features:
                    mock_features.return_value = pd.Series({"close": 2650.0})

                    engine.tick()

                    # Should be paused with the signal
                    assert engine.state.is_paused is True
                    assert engine.state.pause_reason == "A+ signal detected"
                    assert engine.state.paused_at_signal is not None
                    assert engine.state.paused_at_signal.confidence == "A+"

    def test_auto_pause_does_not_trigger_on_watch_signal(
        self, mock_data_stream, mock_validation_engine, mock_session_validator
    ):
        """Test that auto-pause does NOT trigger on Watch signals."""
        engine = SimulationEngine(
            data_stream=mock_data_stream,
            validation_engine=mock_validation_engine,
            session_validator=mock_session_validator,
            auto_pause_on_a_plus=True,
        )

        # Create a Watch signal
        watch_signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=7.0,
            confidence="Watch",
            factors={"structure": 1.5},
            rationale="Test signal",
            validation_flags={"session_ok": True},
            enforcer_tier="Early Mild",
        )

        with patch.object(engine, "_generate_signal", return_value=watch_signal):
            with patch.object(engine.htf_calculator, "update") as mock_update:
                mock_htf = MagicMock()
                mock_htf.bias = "bullish"
                mock_update.return_value = mock_htf

                with patch.object(
                    engine.htf_calculator, "get_current_features_15m"
                ) as mock_features:
                    mock_features.return_value = pd.Series({"close": 2650.0})

                    engine.tick()

                    # Should NOT be paused
                    assert engine.state.is_paused is False
                    assert engine.state.pause_reason is None
                    assert engine.state.paused_at_signal is None
