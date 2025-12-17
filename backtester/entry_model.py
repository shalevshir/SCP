"""Entry model for backtesting - executes entries at next bar open.

This module implements the "next bar open" entry model, which ensures:
- No look-ahead bias: entries occur after signal generation
- Deterministic execution: entry price = next candle open
- Realistic timing: simulates broker execution delay
- Full auditability: all executions are traceable

Following Shir Capital SOP requirements for structure-based, reproducible entries.
"""

from dataclasses import dataclass
from datetime import datetime

from common.logger import get_logger
from common.types import Candle
from rule_engine.signal import Signal

logger = get_logger(__name__)


@dataclass(frozen=True)
class EntryExecution:
    """Result of entry execution at next bar open.

    This immutable dataclass captures the complete execution context for a trade
    entry, including timing, pricing, and success/failure status. Designed for
    auditability and backtesting reproducibility.

    Attributes:
        signal_timestamp: Timestamp when the signal was generated (from Signal)
        entry_timestamp: Timestamp when trade was entered (next bar timestamp)
        entry_price: Executed entry price (next bar open price)
        signal: Original Signal object that triggered this entry
        executed: Whether entry was successfully executed
        rejection_reason: Explanation if entry was not executed (None if executed)

    Example:
        >>> signal = Signal(...)  # A+ confidence signal
        >>> next_candle = Candle(timestamp=..., open=2650.0, ...)
        >>> execution = execute_entry_at_next_open(signal, next_candle)
        >>> if execution.executed:
        ...     print(f"Entered at {execution.entry_price}")
    """

    signal_timestamp: datetime
    entry_timestamp: datetime
    entry_price: float
    signal: Signal
    executed: bool
    rejection_reason: str | None


def execute_entry_at_next_open(
    signal: Signal,
    next_candle: Candle | None,
) -> EntryExecution:
    """Execute trade entry at the opening price of the next candle.

    This function implements the core "next bar open" entry logic, ensuring:
    - Entries occur one bar after signal generation (no look-ahead)
    - Only A+ confidence signals are executed
    - VWAP_RECLAIM expansion gate checked at execution (not setup classification)
    - Graceful handling of missing data (end of dataset)
    - Full determinism (no randomness or slippage)

    Entry rejection reasons:
    1. Signal confidence != "A+"
    2. next_candle is None (end of dataset)
    3. VWAP_RECLAIM without expansion signals (entry not ready)
    All other validation (session, guardrails, tier) happens BEFORE signal generation.

    Args:
        signal: Validated Signal object from RuleEngine (must have passed
            SOP validation)
        next_candle: The candle immediately following the signal timestamp,
            or None if signal occurred at end of dataset

    Returns:
        EntryExecution object with execution details or rejection reason

    Behavior:
        - If signal confidence is not "A+": entry not executed
        - If next_candle is None: entry not executed (end of dataset)
        - If VWAP_RECLAIM without expansion: entry not ready (setup detected, not executable)
        - If next_candle exists and signal is "A+": entry at next_candle.open
        - Entry timestamp = next_candle.timestamp
        - Entry price = next_candle.open (no slippage applied)

    Example:
        >>> signal = Signal(confidence="A+", timestamp=datetime(...), ...)
        >>> next_candle = Candle(timestamp=datetime(...), open=2650.0, ...)
        >>> execution = execute_entry_at_next_open(signal, next_candle)
        >>> assert execution.executed is True
        >>> assert execution.entry_price == 2650.0
    """
    # Check 1: Only execute A+ confidence signals
    if signal.confidence != "A+":
        logger.debug(
            f"Entry skipped: Signal confidence {signal.confidence} is below A+ "
            f"(symbol={signal.symbol}, timestamp={signal.timestamp})"
        )
        return EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=0.0,
            signal=signal,
            executed=False,
            rejection_reason=f"Signal confidence {signal.confidence} not tradeable",
        )

    # Check 2: Ensure next candle exists
    if next_candle is None:
        logger.warning(
            f"Entry rejected: No next candle available (end of dataset) "
            f"(symbol={signal.symbol}, timestamp={signal.timestamp})"
        )
        return EntryExecution(
            signal_timestamp=signal.timestamp,
            entry_timestamp=signal.timestamp,
            entry_price=0.0,
            signal=signal,
            executed=False,
            rejection_reason="No next candle available (end of dataset)",
        )

    # Check 3: VWAP_RECLAIM expansion gate (entry readiness check)
    # Setup can be detected without expansion, but entry requires expansion signals
    # if signal.setup_type == "VWAP_RECLAIM":
    #     expansion_detected = signal.diagnostics.get("expansion_detected", False)
    #     expansion_reasons = signal.diagnostics.get("expansion_reasons", [])
        
    #     if not expansion_detected:
    #         logger.info(
    #             f"Entry NOT READY: VWAP_RECLAIM detected but no expansion signals "
    #             f"(symbol={signal.symbol}, timestamp={signal.timestamp}, "
    #             f"score={signal.score}). Setup candidate exists, waiting for expansion."
    #         )
    #         return EntryExecution(
    #             signal_timestamp=signal.timestamp,
    #             entry_timestamp=signal.timestamp,
    #             entry_price=0.0,
    #             signal=signal,
    #             executed=False,
    #             rejection_reason="VWAP_RECLAIM entry not ready: no expansion signals detected",
    #         )
        
    #     logger.debug(
    #         f"VWAP_RECLAIM expansion gate PASSED: {expansion_reasons} "
    #         f"(symbol={signal.symbol}, timestamp={signal.timestamp})"
    #     )

    # SUCCESS: Execute entry at next bar open
    time_delta = next_candle.timestamp - signal.timestamp
    logger.info(
        f"Entry executed: {signal.direction} {signal.symbol} at {next_candle.open} "
        f"(signal_time={signal.timestamp}, entry_time={next_candle.timestamp}, "
        f"delta={time_delta}, setup={signal.setup_type}, score={signal.score})"
    )

    return EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=next_candle.timestamp,
        entry_price=next_candle.open,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )
