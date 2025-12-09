"""Test that resume() restarts the thread if it has stopped."""

import time
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest
from common.types import Candle
from dashboard.core.data_stream import DataStream
from dashboard.core.engine import SimulationEngine
from validation.engine import ValidationEngine
from validation.session_validator import SessionValidator


@pytest.fixture
def mock_data_stream():
    """Create a mock data stream."""
    stream = MagicMock(spec=DataStream)
    stream.warmup_bars = 0
    stream.stream_start_index = 0
    stream.get_progress.return_value = 0.5

    # Always return True for has_more
    stream.has_more.return_value = True

    gc_candle = Candle(
        symbol="GC",
        timestamp=datetime(2025, 9, 8, 10, 0, tzinfo=UTC),
        open=2500.0,
        high=2510.0,
        low=2495.0,
        close=2505.0,
        volume=1000.0,
        timeframe="1m",
        source="TEST",
    )
    dxy_candle = Candle(
        symbol="DXY",
        timestamp=datetime(2025, 9, 8, 10, 0, tzinfo=UTC),
        open=104.0,
        high=104.1,
        low=103.9,
        close=104.05,
        volume=0.0,
        timeframe="1m",
        source="TEST",
    )
    stream.advance.return_value = (gc_candle, dxy_candle)
    stream.get_candle_at.return_value = (gc_candle, dxy_candle)

    return stream


@pytest.fixture
def mock_validation_engine():
    """Create a mock validation engine."""
    return MagicMock(spec=ValidationEngine)


@pytest.fixture
def mock_session_validator():
    """Create a mock session validator."""
    validator = MagicMock(spec=SessionValidator)
    result = MagicMock()
    result.session_ok = True
    result.constraints = None
    validator.evaluate.return_value = result
    return validator


def test_resume_restarts_thread_when_stopped(
    mock_data_stream, mock_validation_engine, mock_session_validator
):
    """Test that resume() restarts the thread if it has stopped."""
    engine = SimulationEngine(
        data_stream=mock_data_stream,
        validation_engine=mock_validation_engine,
        session_validator=mock_session_validator,
        auto_pause_on_a_plus=True,
        speed_multiplier=100.0,  # Fast speed for testing
    )

    # Setup mocks to avoid errors
    engine.htf_calculator.update = MagicMock(return_value=None)
    engine.htf_calculator.get_current_features_15m = MagicMock(
        return_value=pd.Series(
            {
                "vwap": 2500.0,
                "timestamp": datetime(2025, 9, 8, 10, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "15m",
            }
        )
    )
    engine.htf_calculator.get_current_bias = MagicMock(return_value=None)

    # Start the simulation
    engine.start()
    assert engine._running
    original_thread = engine._thread

    # Pause the simulation
    engine.pause("Test pause")
    assert engine.state.is_paused
    time.sleep(0.2)  # Let it enter the pause loop

    # Simulate the thread stopping (e.g., due to running out of data)
    # Stop the engine which will cause the thread to exit
    engine.stop()
    time.sleep(0.3)  # Wait for thread to fully exit

    # Thread should be dead now
    assert not original_thread.is_alive()

    # Manually set is_paused back to True to simulate the scenario
    # where the thread exited while in paused state
    engine._state = engine._state.update(is_paused=True, pause_reason="Test pause")

    # Now call resume()
    engine.resume()

    # Verify that:
    # 1. Pause flags are cleared
    assert not engine.state.is_paused
    assert engine.state.pause_reason is None

    # 2. A new thread was started
    assert engine._running
    assert engine._thread is not None
    assert engine._thread.is_alive()
    assert engine._thread != original_thread  # New thread object

    # Cleanup
    engine.stop()


def test_resume_does_not_restart_if_thread_alive(
    mock_data_stream, mock_validation_engine, mock_session_validator
):
    """Test that resume() does not restart if thread is still alive."""
    # Mock has_more to always return True so thread doesn't exit
    mock_data_stream.has_more.return_value = True

    engine = SimulationEngine(
        data_stream=mock_data_stream,
        validation_engine=mock_validation_engine,
        session_validator=mock_session_validator,
        auto_pause_on_a_plus=True,
        speed_multiplier=100.0,
    )

    # Setup mocks
    engine.htf_calculator.update = MagicMock(return_value=None)
    engine.htf_calculator.get_current_features_15m = MagicMock(
        return_value=pd.Series(
            {
                "vwap": 2500.0,
                "timestamp": datetime(2025, 9, 8, 10, 0, tzinfo=UTC),
                "symbol": "GC",
                "timeframe": "15m",
            }
        )
    )
    engine.htf_calculator.get_current_bias = MagicMock(return_value=None)

    # Start and pause
    engine.start()
    original_thread = engine._thread
    time.sleep(0.1)
    engine.pause("Test pause")
    assert engine.state.is_paused
    time.sleep(0.1)

    # Thread should still be alive (just paused)
    assert original_thread.is_alive()

    # Resume
    engine.resume()

    # Verify same thread is still running
    assert not engine.state.is_paused
    assert engine._thread == original_thread
    assert engine._thread.is_alive()

    # Cleanup
    engine.stop()
