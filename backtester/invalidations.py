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

from common.logger import get_logger
from common.types import Candle

from backtester.trade import Trade

logger = get_logger(__name__)

# SOP time limits for +1R achievement
R1_TIME_LIMITS = {
    "VWAP_RECLAIM": 60,  # Extended from 20 to allow reclaim setups more time
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
        # Track consecutive invalidation bars for FADE setups (2-bar confirmation)
        self._fade_invalidation_count: dict[str, int] = {}
        # Track consecutive DXY flip bars for VWAP_RECLAIM (3-bar persistence required)
        self._dxy_flip_count: dict[str, int] = {}

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
                vwap = _sanitize_float(features.get("vwap"))
                if vwap is not None:
                    # VWAP reclaimed if price closes above (long) or below (short)
                    if trade.direction == "long":
                        if candle.close > vwap:
                            state["vwap_reclaimed"] = True
                            msg = f"Trade {trade.trade_id} VWAP reclaimed"
                            logger.debug(f"{msg} at {candle.timestamp}")
                    else:  # short
                        if candle.close < vwap:
                            state["vwap_reclaimed"] = True
                            msg = f"Trade {trade.trade_id} VWAP reclaimed"
                            logger.debug(f"{msg} at {candle.timestamp}")

    def check_no_1r_reached(
        self,
        trade: Trade,
        bars_elapsed: int,
        candle: Candle | None = None,
        month: int | None = None,
    ) -> tuple[bool, str | None]:
        """Check if +1R not reached within time limits (with optional protection).

        Args:
            trade: Open trade to check
            bars_elapsed: Number of bars since entry
            candle: Current candle (for time_stop_protection calculation)
            month: Current month (for September defensive mode)

        Returns:
            Tuple of (is_invalid, reason)

        SOP Rules:
            - Continuation: Must reach +1R within 20 bars
            - Fade: Must reach +1R within 10 bars
            
        Time-Stop Protection (narrowly scoped per CEO directive):
            - VWAP_RECLAIM only
            - September defensive mode only
            - Exit at half time limit if < -0.2R
            - Logged as 'time_stop_protection' for separate measurement
        """
        # Get time limit for this setup type
        time_limit = R1_TIME_LIMITS.get(trade.setup_type, 20)

        # TIME-STOP PROTECTION: Early exit for deep red losses
        # (VWAP_RECLAIM + September only)
        if (
            trade.setup_type == "VWAP_RECLAIM"
            and candle is not None
            and month == 9
            and bars_elapsed >= time_limit // 2
        ):
            # Calculate current R
            if trade.direction == "long":
                current_pnl = candle.close - trade.entry_price
            else:
                current_pnl = trade.entry_price - candle.close
            current_r = current_pnl / trade.risk_amount if trade.risk_amount > 0 else 0
            
            # Early exit if deep red (< -0.2R)
            if current_r < -0.2:
                reason = (
                    f"time_stop_protection: {current_r:.2f}R "
                    f"at bar {bars_elapsed} (September mode)"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason

        # Standard time-stop check: only at the time limit
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
            - VWAP_RECLAIM (continuation):
              * Long: Invalid if close < VWAP (breaks continuation)  # noqa: E501
              * Short: Invalid if close > VWAP (breaks continuation)  # noqa: E501
            - VWAP_FADE (fading VWAP):
              * Long: Invalid if close > VWAP (invalidates fade)  # noqa: E501
              * Short: Invalid if close < VWAP (invalidates fade)  # noqa: E501
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

        # PATCH PART 3: Extract VWAP slope for confirmation (prevents noise-based exits)
        vwap_slope = _sanitize_float(features.get("vwap_slope"))

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
            # This prevents premature exits on micro-noise and intrabar wicks
            trade_id = trade.trade_id

            # Check if invalidation condition is met on THIS bar
            condition_met = False

            if trade.direction == "long":
                # Long fade (short position): invalid if price RECLAIMS ABOVE VWAP
                if candle.close > vwap and (vwap_slope is not None and vwap_slope > 0):
                    condition_met = True
            else:  # short
                # Short fade (long position): invalid if price BREAKS BELOW VWAP
                if candle.close < vwap and (vwap_slope is not None and vwap_slope < 0):
                    condition_met = True

            # Track consecutive bars meeting condition
            if condition_met:
                # Increment counter
                current_count = self._fade_invalidation_count.get(trade_id, 0)
                self._fade_invalidation_count[trade_id] = current_count + 1

                # Require 2 consecutive bars
                if self._fade_invalidation_count[trade_id] >= 2:
                    op = '>' if trade.direction == 'long' else '<'
                    reason = (
                        f"VWAP invalidation (2-bar confirmed): "
                        f"close {candle.close:.2f} {op} "
                        f"VWAP {vwap:.2f}, slope {vwap_slope:.4f}"
                    )
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    # Clear counter after invalidation
                    self._fade_invalidation_count[trade_id] = 0
                    return True, reason
                else:
                    # First bar meeting condition - not yet invalid
                    logger.debug(
                        f"Trade {trade.trade_id}: FADE invalidation condition met "
                        f"(bar {self._fade_invalidation_count[trade_id]}/2)"
                    )
            else:
                # Condition NOT met - reset counter
                if trade_id in self._fade_invalidation_count:
                    logger.debug(
                        f"Trade {trade.trade_id}: FADE invalidation condition reset "
                        f"(was at {self._fade_invalidation_count[trade_id]} bars)"
                    )
                    self._fade_invalidation_count[trade_id] = 0

        return False, None

    def check_session_end(
        self, trade: Trade, candle: Candle, session_end_time: time | None = None
    ) -> tuple[bool, str | None]:
        """Check if session has ended (FIX #6: NO force exit at session close).

        FIX #6: Session guard must NOT force auto-exits.
        Trades entered during valid session must run to TP/SL, not force-closed.

        This function now always returns (False, None) to prevent session-based exits.
        Session validation should only block NEW entries, not close existing trades.

        Args:
            trade: Open trade to check
            candle: Current candle
            session_end_time: Ignored (kept for signature compatibility)

        Returns:
            Tuple of (is_invalid, reason) - always (False, None)

        SOP Rules (Updated):
            - Session end does NOT close open trades
            - Trades run to TP/SL regardless of session time
            - Session validation is for entry blocking only
        """
        # FIX #6: Do not auto-exit trades based on session end
        # Session validation is for entry blocking only
        logger.debug(
            f"Trade {trade.trade_id}: session end check disabled (FIX #6). "
            f"Trade will run to TP/SL."
        )
        return False, None

    def check_micro_structure_invalidation(
        self, trade: Trade, candle: Candle, features: dict | None = None
    ) -> tuple[bool, str | None]:
        """Check if micro (1m) structure breaks opposite to trade direction.

        NOTE: This uses structure labels computed from 1m candle data, NOT HTF (15m/1h).
        The exit reason is 'micro_structure' to reflect the actual timeframe.

        VWAP_RECLAIM SPECIAL HANDLING:
        Micro invalidation must NOT act as a scalp stop for VWAP_RECLAIM.
        It may only invalidate if the RECLAIM THESIS is broken, confirmed by:
        a) VWAP invalidation (price regains VWAP for shorts / loses VWAP for longs)
        b) HTF structure invalidation (15m/1h)
        c) Reclaim-specific swing level break

        Args:
            trade: Open trade to check
            candle: Current candle
            features: Optional feature dictionary containing structure labels

        Returns:
            Tuple of (is_invalid, reason)

        Rules:
            - Long: Invalid if structure breaks bearish (LL on 1m)
            - Short: Invalid if structure breaks bullish (HH on 1m)
            - VWAP_RECLAIM: micro break ALONE is NOT sufficient - requires confirmation
        """
        # Need structure info from features
        if features is None:
            return False, None

        # Get structure label from features (1m timeframe)
        structure_label = features.get("structure_label") or features.get(
            "structure_type"
        )

        # If no structure label available, can't detect invalidation
        if structure_label is None:
            return False, None

        # Get computed timeframe for reason message
        computed_timeframe = features.get("timeframe", "1m")

        # Step 1: Detect micro structure break
        micro_break_detected = False
        if trade.direction == "long" and structure_label == "LL":
            micro_break_detected = True
        elif trade.direction == "short" and structure_label == "HH":
            micro_break_detected = True

        # If no micro break detected, MUST return (False, None)
        if not micro_break_detected:
            return False, None

        # Step 2: For VWAP_RECLAIM, micro break ALONE is NOT sufficient
        # Requires confirmation from VWAP loss/regain OR HTF structure break
        if trade.setup_type == "VWAP_RECLAIM":
            confirmation_reason = None
            
            # Confirmation A: VWAP invalidation
            current_vwap = _sanitize_float(features.get("vwap"))
            if current_vwap is not None:
                if trade.direction == "long" and candle.close < current_vwap:
                    confirmation_reason = (
                        f"Micro break {structure_label} + VWAP loss: "
                        f"close {candle.close:.2f} < VWAP {current_vwap:.2f}"
                    )
                elif trade.direction == "short" and candle.close > current_vwap:
                    confirmation_reason = (
                        f"Micro break {structure_label} + VWAP regain: "
                        f"close {candle.close:.2f} > VWAP {current_vwap:.2f}"
                    )
            
            # Confirmation B: HTF structure break (15m)
            if confirmation_reason is None:
                htf_structure = features.get(
                    "htf_structure_label"
                ) or features.get("structure_15m")
                if htf_structure is not None:
                    if trade.direction == "long" and htf_structure in ("LH", "LL"):
                        confirmation_reason = (
                            f"Micro break {structure_label} + HTF break: "
                            f"HTF structure={htf_structure}"
                        )
                    elif trade.direction == "short" and htf_structure in ("HH", "HL"):
                        confirmation_reason = (
                            f"Micro break {structure_label} + HTF break: "
                            f"HTF structure={htf_structure}"
                        )
            
            # No confirmation - VWAP_RECLAIM micro break alone is NOT enough to exit
            if confirmation_reason is None:
                msg = (
                    f"Trade {trade.trade_id} VWAP_RECLAIM: "
                    f"micro break {structure_label} "
                    f"NOT confirmed (VWAP/HTF intact) - HOLDING"
                )
                logger.debug(msg)
                return False, None
            
            # Confirmed micro break for VWAP_RECLAIM
            logger.info(f"Trade {trade.trade_id} invalidated: {confirmation_reason}")
            return True, confirmation_reason

        # Step 3: Non-VWAP_RECLAIM setups use immediate micro invalidation
        reason = f"Micro structure break: {structure_label} on {computed_timeframe}"
        logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
        return True, reason

    def check_htf_structure_invalidation(
        self, trade: Trade, candle: Candle, features: dict | None = None
    ) -> tuple[bool, str | None]:
        """Check if HTF (15m/1h) structure breaks opposite to trade direction.

        Args:
            trade: Open trade to check
            candle: Current candle
            features: Optional feature dictionary containing structure labels

        Returns:
            Tuple of (is_invalid, reason)

        Rules:
            - Long: Invalid if structure breaks bearish (LL)
            - Short: Invalid if structure breaks bullish (HH)
            - Uses structure labels from features
        """
        # Need structure info from features
        if features is None:
            return False, None

        # Get structure label from features
        structure_label = features.get("structure_label") or features.get(
            "structure_type"
        )

        # If no structure label available, can't detect invalidation
        if structure_label is None:
            return False, None

        # Check for confirmed structure break against trade direction
        # Long trades: only invalidate on LL (confirmed bearish break)
        # Short trades: only invalidate on HH (confirmed bullish break)
        if trade.direction == "long":
            # Long trade invalidated only by LL (confirmed bearish break)
            if structure_label == "LL":
                reason = "HTF break: LL structure (bearish)"
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason
        else:  # short
            # Short trade invalidated only by HH (confirmed bullish break)
            if structure_label == "HH":
                reason = "HTF break: HH structure (bullish)"
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
            - DXY_CONTINUATION setups: Strict correlation + structure validation
            - Other setups: Simpler correlation-based checks
            - Exit immediately when DXY breaks alignment
        """
        # Need DXY info from features
        if features is None:
            return False, None

        # Stricter logic for DXY_CONTINUATION setups
        if trade.setup_type == "DXY_CONTINUATION":
            # Get micro correlations and structure
            # Support HTFBias keys (dxy_corr_1m/5m) and streaming (dxy_corr_micro)  # noqa: E501
            corr_1m = _sanitize_float(
                features.get("dxy_corr_1m") or features.get("dxy_corr_micro")
            )
            corr_5m = _sanitize_float(
                features.get("dxy_corr_5m") or features.get("dxy_corr_micro")
            )
            # Support both dxy_structure and dxy_structure_label
            dxy_structure = features.get("dxy_structure") or features.get(
                "dxy_structure_label"
            )

            # For continuation setups, require BOTH correlation flip AND structure break
            if trade.direction == "long":
                # Long continuation invalidated when:
                # - Correlation weakens (both > -0.1) AND
                # - DXY structure turns bullish (HH/HL)
                if (
                    corr_1m is not None
                    and corr_5m is not None
                    and corr_1m > -0.1
                    and corr_5m > -0.1
                    and dxy_structure in ("HH", "HL")
                ):
                    # Add invalidation diagnostics
                    from backtester.diagnostics import add_nested_diag

                    add_nested_diag(
                        trade, "invalidation_context", "type", "dxy_continuation"
                    )
                    add_nested_diag(
                        trade, "invalidation_context", "dxy_corr_1m", corr_1m
                    )
                    add_nested_diag(
                        trade, "invalidation_context", "dxy_corr_5m", corr_5m
                    )
                    add_nested_diag(
                        trade,
                        "invalidation_context",
                        "dxy_structure_label",
                        dxy_structure,
                    )

                    reason = (
                        f"DXY continuation invalidated: structure + correlation flip "
                        f"(corr_1m={corr_1m:.3f}, corr_5m={corr_5m:.3f}, "
                        f"dxy_structure={dxy_structure})"
                    )
                    add_nested_diag(trade, "invalidation_context", "reason", reason)
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    return True, reason

            else:  # short
                # Short continuation invalidated when:
                # - Correlation weakens (both > -0.1, moving toward zero) AND
                # - DXY structure turns bearish (LH/LL)
                if (
                    corr_1m is not None
                    and corr_5m is not None
                    and corr_1m > -0.1
                    and corr_5m > -0.1
                    and dxy_structure in ("LH", "LL")
                ):
                    reason = (
                        f"DXY continuation invalidated: structure + correlation flip "
                        f"(corr_1m={corr_1m:.3f}, corr_5m={corr_5m:.3f}, "
                        f"dxy_structure={dxy_structure})"
                    )
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    return True, reason

            # Continuation setup but no invalidation yet
            return False, None

        # Standard logic for other setups (VWAP_RECLAIM, VWAP_FADE)
        dxy_corr = _sanitize_float(features.get("dxy_corr"))
        trade_id = trade.trade_id

        if dxy_corr is None:
            # FIX: Reset consecutive counter on missing data to preserve
            # "3 consecutive bars" requirement for VWAP_RECLAIM.
            # A None breaks the consecutive sequence.
            if trade_id in self._dxy_flip_count:
                self._dxy_flip_count[trade_id] = 0
            return False, None

        # VWAP_RECLAIM DXY invalidation:
        # Uses raw features["dxy_corr"] field (same as entry scoring uses)
        # Inverse-correlation: alignment = corr <= threshold, flip >= 0.0  # noqa: E501
        # Exit requires 3-bar persistence to avoid premature exits
        if trade.setup_type == "VWAP_RECLAIM":
            dxy_flip_bars_required = 3  # Require 3 consecutive bars of flip

            # Log actual value for verification
            logger.debug(
                f"Trade {trade.trade_id} DXY exit check: dxy_corr={dxy_corr:.3f}"
            )

            # Inverse-correlation: flip when >= 0.0  # noqa: E501
            # Consistent with entry (dxy_corr < threshold)  # noqa: E501
            condition_met = dxy_corr >= 0.0

            # Track consecutive bars meeting condition
            if condition_met:
                current_count = self._dxy_flip_count.get(trade_id, 0)
                self._dxy_flip_count[trade_id] = current_count + 1

                # Require N consecutive bars for VWAP_RECLAIM
                if self._dxy_flip_count[trade_id] >= dxy_flip_bars_required:
                    reason = (
                        f"DXY flip ({dxy_flip_bars_required}-bar confirmed): "
                        f"dxy_corr={dxy_corr:.3f} >= 0.0 "
                        f"(inverse relationship broken for {trade.direction} trade)"
                    )
                    # Clear counter after invalidation
                    self._dxy_flip_count[trade_id] = 0
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    return True, reason
            else:
                # Condition NOT met - reset counter
                if trade_id in self._dxy_flip_count:
                    self._dxy_flip_count[trade_id] = 0

            return False, None

        # Original logic for VWAP_FADE (unchanged)
        # Long trade: DXY should be negatively correlated (DXY down = GC up)
        if trade.direction == "long":
            if dxy_corr > -0.3:
                reason = (
                    f"DXY flip: correlation {dxy_corr:.3f} indicates DXY structure "
                    f"breaking against long trade (expected < -0.3)"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason

        # Short trade: DXY should be positively correlated or less negative
        else:  # short
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
        # Assume window stays active (can enhance with DXY tracking)  # noqa: E501
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

    def record_trade_outcome(self, trade: Trade, won: bool | None) -> None:
        """Record trade outcome to update daily state.

        Args:
            trade: Closed trade
            won: True if trade was profitable (pnl > 0),
                 False if trade was a loss (pnl < 0),
                 None if trade was breakeven (pnl == 0)

        Note:
            Breakeven trades (won=None) do not affect the loss streak.
            Only actual losses (won=False) increment the streak.
        """
        # Reset daily state if new session
        trade_date = trade.exit_timestamp.date() if trade.exit_timestamp else None
        if trade_date and trade_date != self._daily_state.get("last_session_date"):
            self._daily_state["consecutive_losses"] = 0
            self._daily_state["daily_pnl"] = 0.0
            self._daily_state["last_session_date"] = trade_date

        # Update consecutive losses
        if won is True:
            # Win: reset streak
            self._daily_state["consecutive_losses"] = 0
        elif won is False:
            # Loss: increment streak
            self._daily_state["consecutive_losses"] += 1
        # If won is None (breakeven): do nothing, streak unchanged

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

        # Check +1R time limit (with time_stop_protection for VWAP_RECLAIM + September)  # noqa: E501
        month = candle.timestamp.month if hasattr(candle.timestamp, 'month') else None  # noqa: E501
        is_invalid, reason = self.check_no_1r_reached(
            trade, bars_elapsed, candle, month
        )
        if is_invalid:
            return is_invalid, reason

        # Check VWAP invalidation (priority 2 per SOP)
        is_invalid, reason = self.check_vwap_invalidation(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Check micro structure invalidation (priority 3 per SOP)
        # NOTE: Uses 1m structure labels, NOT actual HTF (15m/1h)
        is_invalid, reason = self.check_micro_structure_invalidation(
            trade, candle, features
        )
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
        if trade_id in self._fade_invalidation_count:
            del self._fade_invalidation_count[trade_id]
        if trade_id in self._dxy_flip_count:
            del self._dxy_flip_count[trade_id]

    def clear_all(self) -> None:
        """Clear all trade states."""
        self._trade_states.clear()
        self._fade_invalidation_count.clear()
        self._dxy_flip_count.clear()
