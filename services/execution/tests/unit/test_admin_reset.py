"""Unit tests for /admin/reset test-isolation behavior.

The /admin/reset endpoint is intended to clear ALL in-memory state so tests can
run independently. In particular, it must reset the global kill switch flag
(`_is_killed`) so subsequent tests are not affected.
"""

import pytest


class _DummyDailyTracker:
    def __init__(self) -> None:
        self.reset_called = False

    def reset_state(self) -> None:
        self.reset_called = True


class _DummyInvalidationChecker:
    def __init__(self) -> None:
        self.reset_called = False

    def reset_daily_state(self) -> None:
        self.reset_called = True


class _DummyTradeManager:
    def __init__(self) -> None:
        self._active_trades: dict = {"t1": object()}
        self._pending_signals: list = [{"id": "s1"}]
        self._trade_entry_bars: dict = {"s1": 123}
        self._last_processed_candle_ts = object()
        self._closed_trade_ranges: set = {(1, 2)}
        self._daily_tracker = _DummyDailyTracker()
        self._invalidation_checker = _DummyInvalidationChecker()


class _DummyStateMachineManager:
    def __init__(self) -> None:
        self._state_machines: dict = {"sm1": object()}
        self._bar_counter = 42


class _DummyBroker:
    def __init__(self) -> None:
        self.reset_called = False

    def reset_state(self) -> None:
        self.reset_called = True


class _DummySynchronizer:
    def __init__(self) -> None:
        self.cleared = False

    def clear(self) -> None:
        self.cleared = True


@pytest.mark.asyncio
async def test_admin_reset_clears_kill_switch_flag() -> None:
    """After kill switch activation, /admin/reset must clear `_is_killed`."""
    import execution_svc.main as main

    old_trade_manager = main._trade_manager
    old_broker = main._broker
    old_sm_manager = main._sm_manager
    old_synchronizer = main._synchronizer
    old_is_killed = main._is_killed

    try:
        main._trade_manager = _DummyTradeManager()  # type: ignore[assignment]
        main._broker = _DummyBroker()  # type: ignore[assignment]
        main._sm_manager = _DummyStateMachineManager()  # type: ignore[assignment]
        main._synchronizer = _DummySynchronizer()  # type: ignore[assignment]

        # Simulate a previous test activating the kill switch.
        main._is_killed = True

        resp = await main.reset_state()
        assert resp["status"] == "ok"

        # Regression assertion: reset must disable kill mode.
        assert main._is_killed is False
    finally:
        main._trade_manager = old_trade_manager
        main._broker = old_broker
        main._sm_manager = old_sm_manager
        main._synchronizer = old_synchronizer
        main._is_killed = old_is_killed
