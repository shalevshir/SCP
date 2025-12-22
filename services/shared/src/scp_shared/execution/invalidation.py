"""Trade invalidation checker for streaming execution.

Simplified version adapted from backtester/invalidations.py for real-time use.
Focuses on essential invalidation rules for production trading.
"""

import math
from typing import Any

from scp_shared.common.logger import get_logger
from scp_shared.common.types import Candle
from scp_shared.execution.types import TradeRecord

logger = get_logger(__name__)

# SOP time limits for +1R achievement
R1_TIME_LIMITS = {
    "VWAP_RECLAIM": 60,
    "DXY_CONTINUATION": 20,
    "VWAP_FADE": 10,
}


def _sanitize_float(value: object | None) -> float | None:
    """Convert value to a finite float if possible; otherwise return None."""
    if value is None:
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(numeric_value) or math.isinf(numeric_value):
        return None

    return numeric_value


class InvalidationChecker:
    """Checks for trade invalidation conditions in streaming mode.

    Tracks trade state to detect when trades should be exited early due to:
    - Not reaching +1R within time limits
    - VWAP invalidation
    - Stop-loss or take-profit hit

    Example:
        >>> checker = InvalidationChecker()
        >>> for candle in candles:
        ...     checker.update_state(trade, candle, features)
        ...     is_invalid, reason = checker.check_all(trade, candle, bars_elapsed, features)
        ...     if is_invalid:
        ...         break
    """

    def __init__(self) -> None:
        """Initialize invalidation checker with empty state."""
        self._trade_states: dict[str, dict[str, Any]] = {}
        # Track consecutive invalidation bars for FADE setups (2-bar confirmation)
        self._fade_invalidation_count: dict[str, int] = {}

    def _get_trade_state(self, trade_id: str) -> dict[str, Any]:
        """Get or create trade state.

        Args:
            trade_id: Unique trade identifier

        Returns:
            Dictionary with trade state (reached_1r, vwap_reclaimed, etc.)
        """
        if trade_id not in self._trade_states:
            self._trade_states[trade_id] = {
                "reached_1r": False,
                "vwap_reclaimed": False,
            }
        return self._trade_states[trade_id]

    def update_state(
        self, trade: TradeRecord, candle: Candle, features: dict[str, Any] | None = None
    ) -> None:
        """Update trade state based on current candle.

        Tracks whether +1R has been reached and VWAP reclaim status.

        Args:
            trade: Open trade to track
            candle: Current candle to check
            features: Optional feature dictionary for VWAP tracking
        """
        state = self._get_trade_state(trade.trade_id)

        # Check if +1R reached
        if not state["reached_1r"]:
            r1_price = trade.entry_price + trade.risk_amount  # +1R for long
            if trade.direction == "short":
                r1_price = trade.entry_price - trade.risk_amount  # +1R for short

            # Check if candle reached +1R
            if trade.direction == "long":
                if candle.high >= r1_price:
                    state["reached_1r"] = True
                    logger.debug(
                        f"Trade {trade.trade_id} reached +1R at {candle.timestamp}"
                    )
            else:  # short
                if candle.low <= r1_price:
                    state["reached_1r"] = True
                    logger.debug(
                        f"Trade {trade.trade_id} reached +1R at {candle.timestamp}"
                    )

        # Track VWAP reclaim for fade setups
        if trade.setup_type == "VWAP_FADE" and not state["vwap_reclaimed"]:
            if features is not None:
                vwap = _sanitize_float(features.get("vwap"))
                if vwap is not None:
                    # VWAP reclaimed if price closes above (long) or below (short)
                    if trade.direction == "long":
                        if candle.close > vwap:
                            state["vwap_reclaimed"] = True
                            logger.debug(
                                f"Trade {trade.trade_id} VWAP reclaimed at {candle.timestamp}"
                            )
                    else:  # short
                        if candle.close < vwap:
                            state["vwap_reclaimed"] = True
                            logger.debug(
                                f"Trade {trade.trade_id} VWAP reclaimed at {candle.timestamp}"
                            )

    def check_sl_tp(
        self, trade: TradeRecord, candle: Candle
    ) -> tuple[bool, str | None]:
        """Check if stop-loss or take-profit was hit.

        Args:
            trade: Open trade to check
            candle: Current candle

        Returns:
            Tuple of (is_exited, exit_reason)
        """
        # Check stop-loss
        if trade.direction == "long":
            if candle.low <= trade.sl_price:
                reason = f"SL_HIT: low {candle.low:.2f} <= SL {trade.sl_price:.2f}"
                logger.info(f"Trade {trade.trade_id} stopped out: {reason}")
                return True, reason
        else:  # short
            if candle.high >= trade.sl_price:
                reason = f"SL_HIT: high {candle.high:.2f} >= SL {trade.sl_price:.2f}"
                logger.info(f"Trade {trade.trade_id} stopped out: {reason}")
                return True, reason

        # Check take-profit
        if trade.direction == "long":
            if candle.high >= trade.tp_price:
                reason = f"TP_HIT: high {candle.high:.2f} >= TP {trade.tp_price:.2f}"
                logger.info(f"Trade {trade.trade_id} take profit hit: {reason}")
                return True, reason
        else:  # short
            if candle.low <= trade.tp_price:
                reason = f"TP_HIT: low {candle.low:.2f} <= TP {trade.tp_price:.2f}"
                logger.info(f"Trade {trade.trade_id} take profit hit: {reason}")
                return True, reason

        return False, None

    def check_no_1r_reached(
        self, trade: TradeRecord, bars_elapsed: int
    ) -> tuple[bool, str | None]:
        """Check if +1R not reached within time limits.

        Args:
            trade: Open trade to check
            bars_elapsed: Number of bars since entry

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - VWAP_RECLAIM: Must reach +1R within 60 bars
            - DXY_CONTINUATION: Must reach +1R within 20 bars
            - VWAP_FADE: Must reach +1R within 10 bars
        """
        # Get time limit for this setup type
        time_limit = R1_TIME_LIMITS.get(trade.setup_type, 20)

        # Only check at the time limit
        if bars_elapsed < time_limit:
            return False, None

        # Check if +1R was reached
        state = self._get_trade_state(trade.trade_id)
        if not state["reached_1r"]:
            reason = (
                f"+1R not reached within {time_limit} bars " f"({trade.setup_type})"
            )
            logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
            return True, reason

        return False, None

    def check_vwap_invalidation(
        self, trade: TradeRecord, candle: Candle, features: dict[str, Any] | None = None
    ) -> tuple[bool, str | None]:
        """Check if VWAP structure is lost.

        Args:
            trade: Open trade to check
            candle: Current candle
            features: Optional feature dictionary containing VWAP value

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - VWAP_RECLAIM: Invalid if price falls below/above VWAP
            - VWAP_FADE: Invalid if price reclaims VWAP (2-bar confirmation)
        """
        # Only applies to VWAP-based setups
        if trade.setup_type not in ("VWAP_RECLAIM", "VWAP_FADE"):
            return False, None

        # Need VWAP from features
        if features is None:
            return False, None

        vwap = _sanitize_float(features.get("vwap"))
        if vwap is None:
            return False, None

        # Check VWAP invalidation - different logic for RECLAIM vs FADE
        if trade.setup_type == "VWAP_RECLAIM":
            # Continuation setups: invalid if price moves against continuation
            if trade.direction == "long":
                if candle.close < vwap:
                    reason = (
                        f"VWAP invalidation: close {candle.close:.2f} < VWAP {vwap:.2f}"
                    )
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    return True, reason
            else:  # short
                if candle.close > vwap:
                    reason = (
                        f"VWAP invalidation: close {candle.close:.2f} > VWAP {vwap:.2f}"
                    )
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    return True, reason
        else:  # VWAP_FADE
            # FADE setups require 2 CONSECUTIVE bars meeting invalidation criteria
            trade_id = trade.trade_id

            # Check if invalidation condition is met on THIS bar
            condition_met = False

            if trade.direction == "long":
                # Long fade: invalid if price RECLAIMS ABOVE VWAP
                if candle.close > vwap:
                    condition_met = True
            else:  # short
                # Short fade: invalid if price BREAKS BELOW VWAP
                if candle.close < vwap:
                    condition_met = True

            # Track consecutive bars meeting condition
            if condition_met:
                # Increment counter
                current_count = self._fade_invalidation_count.get(trade_id, 0)
                self._fade_invalidation_count[trade_id] = current_count + 1

                # Require 2 consecutive bars
                if self._fade_invalidation_count[trade_id] >= 2:
                    reason = (
                        f"VWAP invalidation (2-bar confirmed): "
                        f"close {candle.close:.2f} {'>' if trade.direction == 'long' else '<'} "
                        f"VWAP {vwap:.2f}"
                    )
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    # Clear counter after invalidation
                    self._fade_invalidation_count[trade_id] = 0
                    return True, reason
            else:
                # Condition NOT met - reset counter
                if trade_id in self._fade_invalidation_count:
                    self._fade_invalidation_count[trade_id] = 0

        return False, None

    def check_all(
        self,
        trade: TradeRecord,
        candle: Candle,
        bars_elapsed: int,
        features: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        """Check all invalidation and exit conditions.

        Args:
            trade: Open trade to check
            candle: Current candle
            bars_elapsed: Number of bars since entry
            features: Optional feature dictionary

        Returns:
            Tuple of (should_exit, reason)

        Checks (in priority order):
            1. SL/TP hit (immediate exit)
            2. +1R not reached within time limits
            3. VWAP invalidation
        """
        # First update state with current candle
        self.update_state(trade, candle, features)

        # Priority 1: SL/TP (immediate exit, no waiting)
        should_exit, reason = self.check_sl_tp(trade, candle)
        if should_exit:
            return should_exit, reason

        # Priority 2: +1R time limit
        is_invalid, reason = self.check_no_1r_reached(trade, bars_elapsed)
        if is_invalid:
            return is_invalid, reason

        # Priority 3: VWAP invalidation
        is_invalid, reason = self.check_vwap_invalidation(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        return False, None

    def reset_trade(self, trade_id: str) -> None:
        """Reset state for a specific trade.

        Args:
            trade_id: Trade ID to reset
        """
        if trade_id in self._trade_states:
            del self._trade_states[trade_id]
        if trade_id in self._fade_invalidation_count:
            del self._fade_invalidation_count[trade_id]

    def clear_all(self) -> None:
        """Clear all trade states."""
        self._trade_states.clear()
        self._fade_invalidation_count.clear()


