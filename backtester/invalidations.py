"""Trade invalidation checker - detects early exit conditions.

This module implements invalidation detection for trades, following SOP rules:
- Trade must reach +1R within time limits (20 bars continuation, 10 bars fade)
- VWAP invalidation (for VWAP_RECLAIM and VWAP_FADE setups)
- Session end (13:00 ILT default)
- Other invalidations (DXY flip, HTF structure) can be added later

Key Features:
- Tracks +1R achievement per trade
- Setup-specific time limits
- Stateful tracking across candles
- Clean invalidation reasons
"""

import math
from datetime import time
from zoneinfo import ZoneInfo

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
    - VWAP invalidation, HTF structure break, DXY flip, session end
    - Setup window expiration, daily risk stop

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
        self._daily_state: dict = {
            "consecutive_losses": 0,
            "daily_pnl": 0.0,
            "last_session_date": None,
        }

    def _get_trade_state(self, trade_id: str) -> dict:
        """Get or create trade state.

        Args:
            trade_id: Unique trade identifier

        Returns:
            Dictionary with trade state (reached_1r, vwap_reclaimed, etc.)
        """
        if trade_id not in self._trade_states:
            self._trade_states[trade_id] = {
                "reached_1r": False,
                "vwap_reclaimed": False,  # For fade setups: track if VWAP was reclaimed
                "window_active": True,  # Track if setup window is still active
            }
        return self._trade_states[trade_id]

    def update_state(
        self, trade: Trade, candle: Candle, features: dict | None = None
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
                vwap = features.get("vwap")
                if vwap is not None and not (math.isnan(vwap) or math.isinf(vwap)):
                    # VWAP reclaimed if price closes above VWAP (for long fade) or below (for short fade)
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

    def check_vwap_invalidation(
        self, trade: Trade, candle: Candle, features: dict | None = None
    ) -> tuple[bool, str | None]:
        """Check if VWAP structure is lost (invalidation for continuation/fade setups).

        Args:
            trade: Open trade to check
            candle: Current candle
            features: Optional feature dictionary containing VWAP value

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - Applies to VWAP_RECLAIM and VWAP_FADE setups only
            - Long: Invalid if close < VWAP
            - Short: Invalid if close > VWAP
        """
        # Only applies to VWAP-based setups
        if trade.setup_type not in ("VWAP_RECLAIM", "VWAP_FADE"):
            return False, None

        # Need VWAP from features
        if features is None:
            return False, None

        vwap = features.get("vwap")
        if vwap is None or (isinstance(vwap, float) and (math.isnan(vwap) or math.isinf(vwap))):
            return False, None

        # Check VWAP invalidation
        if trade.direction == "long":
            if candle.close < vwap:
                reason = f"VWAP invalidation: close {candle.close:.2f} < VWAP {vwap:.2f}"
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason
        else:  # short
            if candle.close > vwap:
                reason = f"VWAP invalidation: close {candle.close:.2f} > VWAP {vwap:.2f}"
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason

        return False, None

    def check_session_end(
        self, trade: Trade, candle: Candle, session_end_time: time | None = None
    ) -> tuple[bool, str | None]:
        """Check if session has ended (force exit at session close).

        Args:
            trade: Open trade to check
            candle: Current candle
            session_end_time: Session end time (default: 13:00 ILT)
                           If None, uses default 13:00 ILT

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - Force exit at session end (13:00 ILT by default)
            - Executes BEFORE timeout
        """
        # Default session end: 13:00 ILT (London time)
        if session_end_time is None:
            session_end_time = time(13, 0, 0)  # 13:00:00

        # Convert candle timestamp to London timezone
        london_tz = ZoneInfo("Europe/London")
        
        # Handle timezone-aware and naive timestamps
        if candle.timestamp.tzinfo is None:
            # Assume UTC if naive
            local_dt = candle.timestamp.replace(tzinfo=ZoneInfo("UTC")).astimezone(london_tz)
        else:
            local_dt = candle.timestamp.astimezone(london_tz)

        current_time = local_dt.time()

        # Check if current time >= session end
        if current_time >= session_end_time:
            reason = (
                f"Session end: {current_time.strftime('%H:%M:%S')} ILT >= "
                f"{session_end_time.strftime('%H:%M:%S')} ILT"
            )
            logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
            return True, reason

        return False, None

    def check_htf_structure_invalidation(
        self, trade: Trade, candle: Candle, features: dict | None = None
    ) -> tuple[bool, str | None]:
        """Check if HTF structure breaks opposite to trade direction.

        Args:
            trade: Open trade to check
            candle: Current candle
            features: Optional feature dictionary containing structure labels

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - Long: Invalid if structure breaks bearish (LH, LL, or bearish BOS/CHoCH)
            - Short: Invalid if structure breaks bullish (HH, HL, or bullish BOS/CHoCH)
            - Uses structure labels from features or entry HTF bias
        """
        # Need structure info from features or trade entry
        if features is None:
            return False, None

        # Get entry HTF bias from trade signal
        entry_htf_bias = trade.entry_execution.signal.htf_bias
        if entry_htf_bias is None:
            return False, None

        # Get structure label from features
        structure_label = features.get("structure_label") or features.get("structure_type")
        
        # If no structure label available, can't detect invalidation
        if structure_label is None:
            return False, None

        # Check for structure break against trade direction
        # Long trades invalidated by bearish structure (LH, LL) regardless of entry bias
        # Short trades invalidated by bullish structure (HH, HL) regardless of entry bias
        if trade.direction == "long":
            # Long trade invalidated by bearish structure
            if structure_label in ("LH", "LL"):
                reason = (
                    f"HTF structure invalidation: {structure_label} detected "
                    f"(bearish structure breaks against long trade)"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason
        else:  # short
            # Short trade invalidated by bullish structure
            if structure_label in ("HH", "HL"):
                reason = (
                    f"HTF structure invalidation: {structure_label} detected "
                    f"(bullish structure breaks against short trade)"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason

        return False, None

    def check_dxy_flip(
        self, trade: Trade, candle: Candle, features: dict | None = None
    ) -> tuple[bool, str | None]:
        """Check if DXY structure flips opposite to trade direction.

        Args:
            trade: Open trade to check
            candle: Current candle
            features: Optional feature dictionary containing DXY correlation/structure

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - Exit immediately when DXY breaks alignment
            - Long: Invalid if DXY structure breaks bearish (opposite to GC long)
            - Short: Invalid if DXY structure breaks bullish (opposite to GC short)
            - Can detect via DXY correlation flip or structure break
        """
        # Need DXY info from features
        if features is None:
            return False, None

        # Get DXY correlation from features
        dxy_corr = features.get("dxy_corr")
        
        # For now, use a simple heuristic: if DXY correlation flips significantly
        # against the trade direction, consider it invalidated
        # This is a simplified check - can be enhanced with actual DXY structure detection
        
        # Long trade: DXY should be negatively correlated (DXY down = GC up)
        # If correlation becomes positive or less negative, DXY may be flipping
        if trade.direction == "long":
            if dxy_corr is not None and not (math.isnan(dxy_corr) or math.isinf(dxy_corr)):
                # DXY correlation should be negative for long GC trades
                # If it flips to positive or becomes less negative, DXY may be flipping
                # Use a threshold: if correlation > -0.3, consider it flipped
                if dxy_corr > -0.3:
                    reason = (
                        f"DXY flip: correlation {dxy_corr:.3f} indicates DXY structure "
                        f"breaking against long trade (expected < -0.6)"
                    )
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    return True, reason
        
        # Short trade: DXY should be positively correlated or less negative
        # If correlation becomes very negative, DXY may be flipping
        else:  # short
            if dxy_corr is not None and not (math.isnan(dxy_corr) or math.isinf(dxy_corr)):
                # For short GC trades, DXY correlation can be less negative
                # If it becomes very negative (< -0.6), DXY is strongly inverse (flipping)
                if dxy_corr < -0.6:
                    reason = (
                        f"DXY flip: correlation {dxy_corr:.3f} indicates DXY structure "
                        f"breaking against short trade (strong inverse correlation)"
                    )
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    return True, reason

        return False, None

    def check_setup_window_expired(
        self, trade: Trade, candle: Candle, features: dict | None = None
    ) -> tuple[bool, str | None]:
        """Check if setup-specific execution window has expired.

        Args:
            trade: Open trade to check
            candle: Current candle
            features: Optional feature dictionary

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - VWAP_RECLAIM: Allowed only after VWAP reclaim confirmed
            - VWAP_FADE: Allowed only early, while VWAP not reclaimed
            - DXY_CONTINUATION: Allowed during verified continuation windows
        """
        state = self._get_trade_state(trade.trade_id)

        # VWAP_FADE: Window expires when VWAP is reclaimed
        if trade.setup_type == "VWAP_FADE":
            if state["vwap_reclaimed"]:
                reason = (
                    "Setup window expired: VWAP_FADE window closed "
                    "(VWAP was reclaimed)"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason

        # VWAP_RECLAIM: Window is active after VWAP reclaim
        # For now, assume window stays active (can be enhanced with more specific logic)
        if trade.setup_type == "VWAP_RECLAIM":
            # Window remains active after reclaim
            pass

        # DXY_CONTINUATION: Window active during continuation
        # For now, assume window stays active (can be enhanced with DXY structure tracking)
        if trade.setup_type == "DXY_CONTINUATION":
            # Window remains active during continuation
            pass

        return False, None

    def check_daily_risk_breach(
        self, trade: Trade, candle: Candle, daily_pnl_state: dict | None = None
    ) -> tuple[bool, str | None]:
        """Check if daily risk limits are breached (PDLL/PDRR or loss streak).

        Args:
            trade: Open trade to check
            candle: Current candle
            daily_pnl_state: Optional daily PnL state dict with:
                - consecutive_losses: Number of consecutive losses today
                - daily_pnl: Total PnL for the day
                - pdll: Permitted Daily Loss Limit
                - pdrr: Permitted Daily Risk Reached

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - Stop trading after 2 consecutive losses (or 1 in September)
            - Force exit if PDLL/PDRR reached while trade still open
        """
        # Use provided daily state or internal tracking
        if daily_pnl_state is None:
            daily_pnl_state = self._daily_state

        # Check loss streak (2 consecutive losses, or 1 in September)
        consecutive_losses = daily_pnl_state.get("consecutive_losses", 0)
        month = candle.timestamp.month if hasattr(candle.timestamp, "month") else 1
        
        # September: 1 loss max, others: 2 losses max
        max_losses = 1 if month == 9 else 2
        
        if consecutive_losses >= max_losses:
            reason = (
                f"Daily risk stop: {consecutive_losses} consecutive losses "
                f"(max allowed: {max_losses})"
            )
            logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
            return True, reason

        # Check PDLL/PDRR if provided
        pdll = daily_pnl_state.get("pdll")
        daily_pnl = daily_pnl_state.get("daily_pnl", 0.0)
        
        if pdll is not None and daily_pnl <= -abs(pdll):
            reason = (
                f"Daily risk stop: PDLL breached "
                f"(daily PnL: {daily_pnl:.2f}, PDLL: {pdll:.2f})"
            )
            logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
            return True, reason

        return False, None

    def record_trade_outcome(self, trade: Trade, won: bool) -> None:
        """Record trade outcome to update daily state.

        Args:
            trade: Closed trade
            won: True if trade was profitable, False if loss
        """
        # Reset daily state if new session
        trade_date = trade.exit_timestamp.date() if trade.exit_timestamp else None
        if trade_date and trade_date != self._daily_state.get("last_session_date"):
            self._daily_state["consecutive_losses"] = 0
            self._daily_state["daily_pnl"] = 0.0
            self._daily_state["last_session_date"] = trade_date

        # Update consecutive losses
        if not won:
            self._daily_state["consecutive_losses"] += 1
        else:
            self._daily_state["consecutive_losses"] = 0

        # Update daily PnL
        if trade.pnl is not None:
            self._daily_state["daily_pnl"] += trade.pnl

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

        Checks (in priority order per SOP):
            1. +1R not reached within time limits
            2. VWAP invalidation (for VWAP_RECLAIM and VWAP_FADE)
            3. HTF structure invalidation
            4. DXY flip
            5. Session end (13:00 ILT)
            6. Setup window expiration
            7. Daily risk stop
        """
        # First update state with current candle (pass features for VWAP tracking)
        self.update_state(trade, candle, features)

        # Check +1R time limit
        is_invalid, reason = self.check_no_1r_reached(trade, bars_elapsed)
        if is_invalid:
            return is_invalid, reason

        # Check VWAP invalidation (priority 2 per SOP)
        is_invalid, reason = self.check_vwap_invalidation(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Check HTF structure invalidation (priority 3 per SOP)
        is_invalid, reason = self.check_htf_structure_invalidation(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Check DXY flip (priority 4 per SOP)
        is_invalid, reason = self.check_dxy_flip(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Check session end (priority 5 per SOP, before timeout)
        is_invalid, reason = self.check_session_end(trade, candle)
        if is_invalid:
            return is_invalid, reason

        # Check setup window expiration (priority 6 per SOP)
        is_invalid, reason = self.check_setup_window_expired(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Check daily risk breach (priority 7 per SOP, before timeout)
        # Note: daily_pnl_state should be passed from pipeline if available
        # For now, use internal daily state tracking
        is_invalid, reason = self.check_daily_risk_breach(trade, candle)
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

    def clear_all(self) -> None:
        """Clear all trade states."""
        self._trade_states.clear()

