"""Trade invalidation checker - detects early exit conditions.

This module implements invalidation detection for trades, following SOP rules:
- Trade must reach +1R within time limits (20 bars continuation, 10 bars fade)
- Other invalidations (DXY flip, VWAP, structure, HTF) can be added later

Key Features:
- Tracks +1R achievement per trade
- Setup-specific time limits
- Stateful tracking across candles
- Clean invalidation reasons
"""

from common.logger import get_logger
from common.types import Candle

from backtester.trade import Trade

logger = get_logger(__name__)

# SOP time limits for +1R achievement
R1_TIME_LIMITS = {
    "VWAP_RECLAIM": 20,
    "DXY_CONTINUATION": 20,
    "VWAP_FADE": 10,
}


class InvalidationChecker:
    """Checks for trade invalidation conditions.

    Tracks trade state to detect when trades should be exited early due to:
    - Not reaching +1R within time limits
    - (Future) DXY flip, VWAP invalidation, structure break, HTF flip, session end

    Example:
        >>> checker = InvalidationChecker()
        >>> for candle in candles:
        ...     checker.update_state(trade, candle)  # Track progress
        ...     is_invalid, reason = checker.check_all(trade, candle, bars_elapsed)
        ...     if is_invalid:
        ...         break
    """

    def __init__(self):
        """Initialize invalidation checker with empty state."""
        self._trade_states: dict[str, dict] = {}

    def _get_trade_state(self, trade_id: str) -> dict:
        """Get or create trade state.

        Args:
            trade_id: Unique trade identifier

        Returns:
            Dictionary with trade state (reached_1r, etc.)
        """
        if trade_id not in self._trade_states:
            self._trade_states[trade_id] = {
                "reached_1r": False,
            }
        return self._trade_states[trade_id]

    def update_state(self, trade: Trade, candle: Candle) -> None:
        """Update trade state based on current candle.

        Tracks whether +1R has been reached.

        Args:
            trade: Open trade to track
            candle: Current candle to check
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

    def check_no_1r_reached(
        self, trade: Trade, bars_elapsed: int
    ) -> tuple[bool, str | None]:
        """Check if +1R not reached within time limits.

        Args:
            trade: Open trade to check
            bars_elapsed: Number of bars since entry

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - Continuation: Must reach +1R within 20 bars
            - Fade: Must reach +1R within 10 bars
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
                f"+1R not reached within {time_limit} bars "
                f"({trade.setup_type})"
            )
            logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
            return True, reason

        return False, None

    def check_all(
        self,
        trade: Trade,
        candle: Candle,
        bars_elapsed: int,
        features: dict | None = None,
    ) -> tuple[bool, str | None]:
        """Check all invalidation conditions.

        Args:
            trade: Open trade to check
            candle: Current candle
            bars_elapsed: Number of bars since entry
            features: Optional feature dictionary (for future DXY/VWAP/HTF checks)

        Returns:
            Tuple of (is_invalid, reason)

        Checks (in priority order):
            1. +1R not reached within time limits
            2. (Future) DXY flip
            3. (Future) VWAP invalidation
            4. (Future) Structure break
            5. (Future) HTF bias flip
            6. (Future) Session end
        """
        # First update state with current candle
        self.update_state(trade, candle)

        # Check +1R time limit
        is_invalid, reason = self.check_no_1r_reached(trade, bars_elapsed)
        if is_invalid:
            return is_invalid, reason

        # Future: Add other invalidation checks here
        # - check_dxy_flip(features)
        # - check_vwap_invalidation(features)
        # - check_structure_break(features)
        # - check_htf_flip(features)
        # - check_session_end(candle.timestamp)

        return False, None

    def reset_trade(self, trade_id: str) -> None:
        """Reset state for a specific trade.

        Args:
            trade_id: Trade ID to reset
        """
        if trade_id in self._trade_states:
            del self._trade_states[trade_id]

    def clear_all(self) -> None:
        """Clear all trade states."""
        self._trade_states.clear()

