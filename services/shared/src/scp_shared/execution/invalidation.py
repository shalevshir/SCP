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

# Setup-specific grace periods (prevent premature stop-outs)
GRACE_PERIODS = {
    "VWAP_RECLAIM": {"sl_tp": 8, "invalidation": 8},
    "DXY_CONTINUATION": {"sl_tp": 6, "invalidation": 6},
    "VWAP_FADE": {"sl_tp": 0, "invalidation": 3},
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
        # Track consecutive DXY flip bars for VWAP_RECLAIM (3-bar persistence required)
        self._dxy_flip_count: dict[str, int] = {}
        # Daily state for risk breach checking
        self._daily_state: dict[str, Any] = {
            "consecutive_losses": 0,
            "daily_pnl": 0.0,
            "last_session_date": None,
        }

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
        self, trade: TradeRecord, candle: Candle, bars_elapsed: int = 0
    ) -> tuple[bool, str | None]:
        """Check if stop-loss or take-profit was hit.

        Args:
            trade: Open trade to check
            candle: Current candle
            bars_elapsed: Number of bars since entry (for grace period)

        Returns:
            Tuple of (is_exited, exit_reason)
        """
        # Get grace period for this setup type
        grace = GRACE_PERIODS.get(trade.setup_type, {}).get("sl_tp", 2)
        
        # Skip SL/TP check during grace period
        if bars_elapsed < grace:
            return False, None
        
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
        self, trade: TradeRecord, bars_elapsed: int, candle: Candle | None = None, month: int | None = None
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
            - VWAP_RECLAIM: Must reach +1R within 60 bars
            - DXY_CONTINUATION: Must reach +1R within 20 bars
            - VWAP_FADE: Must reach +1R within 10 bars
            
        Time-Stop Protection (narrowly scoped per CEO directive):
            - VWAP_RECLAIM only
            - September defensive mode only
            - Exit at half time limit if < -0.2R
            - Logged as 'time_stop_protection' for separate measurement
        """
        # Get time limit for this setup type
        time_limit = R1_TIME_LIMITS.get(trade.setup_type, 20)

        # TIME-STOP PROTECTION: Early exit for deep red losses (VWAP_RECLAIM + September only)
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
                reason = f"time_stop_protection: {current_r:.2f}R at bar {bars_elapsed} (September mode)"
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
            # AND require VWAP slope confirmation to prevent noise-based exits
            trade_id = trade.trade_id

            # Extract VWAP slope for confirmation (prevents noise-based exits)
            vwap_slope = _sanitize_float(features.get("vwap_slope"))

            # Check if invalidation condition is met on THIS bar
            condition_met = False

            if trade.direction == "long":
                # Long fade: invalid if price RECLAIMS ABOVE VWAP AND slope is positive
                if candle.close > vwap and (vwap_slope is not None and vwap_slope > 0):
                    condition_met = True
            else:  # short
                # Short fade: invalid if price BREAKS BELOW VWAP AND slope is negative
                if candle.close < vwap and (vwap_slope is not None and vwap_slope < 0):
                    condition_met = True

            # Track consecutive bars meeting condition
            if condition_met:
                # Increment counter
                current_count = self._fade_invalidation_count.get(trade_id, 0)
                self._fade_invalidation_count[trade_id] = current_count + 1

                # Require 2 consecutive bars
                if self._fade_invalidation_count[trade_id] >= 2:
                    slope_str = f", slope {vwap_slope:.4f}" if vwap_slope is not None else ""
                    reason = (
                        f"VWAP invalidation (2-bar confirmed): "
                        f"close {candle.close:.2f} {'>' if trade.direction == 'long' else '<'} "
                        f"VWAP {vwap:.2f}{slope_str}"
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

    def check_micro_structure_invalidation(
        self, trade: TradeRecord, candle: Candle, features: dict[str, Any] | None = None
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
                htf_structure = features.get("htf_structure_label") or features.get("structure_15m")
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
                logger.debug(
                    f"Trade {trade.trade_id} VWAP_RECLAIM: micro break {structure_label} "
                    f"NOT confirmed (VWAP/HTF intact) - HOLDING"
                )
                return False, None
            
            # Confirmed micro break for VWAP_RECLAIM
            logger.info(f"Trade {trade.trade_id} invalidated: {confirmation_reason}")
            return True, confirmation_reason

        # Step 3: Non-VWAP_RECLAIM setups use immediate micro invalidation
        reason = f"Micro structure break: {structure_label} on {computed_timeframe}"
        logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
        return True, reason

    def check_dxy_flip(
        self, trade: TradeRecord, candle: Candle, features: dict[str, Any] | None = None
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
            - VWAP_RECLAIM: 3-bar persistence required
            - Other setups: Simpler correlation-based checks
        """
        # Need DXY info from features
        if features is None:
            return False, None

        # Stricter logic for DXY_CONTINUATION setups
        if trade.setup_type == "DXY_CONTINUATION":
            # Get micro correlations and structure
            corr_1m = _sanitize_float(
                features.get("dxy_corr_1m") or features.get("dxy_corr_micro")
            )
            corr_5m = _sanitize_float(
                features.get("dxy_corr_5m") or features.get("dxy_corr_micro")
            )
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
                    reason = (
                        f"DXY continuation invalidated: structure + correlation flip "
                        f"(corr_1m={corr_1m:.3f}, corr_5m={corr_5m:.3f}, "
                        f"dxy_structure={dxy_structure})"
                    )
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
            # Reset consecutive counter on missing data to preserve
            # "3 consecutive bars" requirement for VWAP_RECLAIM
            if trade_id in self._dxy_flip_count:
                self._dxy_flip_count[trade_id] = 0
            return False, None

        # VWAP_RECLAIM DXY invalidation:
        # Uses raw features["dxy_corr"] field (same as entry scoring uses)
        # Model is inverse-correlation: alignment = corr <= threshold, flip = corr >= 0.0
        # Exit requires 3-bar persistence to avoid premature exits
        if trade.setup_type == "VWAP_RECLAIM":
            dxy_flip_bars_required = 3  # Require 3 consecutive bars of flip

            # Log actual value for verification
            logger.debug(
                f"Trade {trade.trade_id} DXY exit check: dxy_corr={dxy_corr:.3f}"
            )

            # Inverse-correlation model: flip when correlation goes non-negative (>= 0.0)
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
                    f"breaking against long trade (expected < -0.6)"
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
        self, trade: TradeRecord, candle: Candle, features: dict[str, Any] | None = None
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
        self, trade: TradeRecord, candle: Candle, daily_pnl_state: dict[str, Any] | None = None
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

    def record_trade_outcome(self, trade: TradeRecord, won: bool | None) -> None:
        """Record trade outcome to update daily state for loss streak tracking.
        
        Args:
            trade: Closed trade
            won: True if profitable (pnl > 0), False if loss (pnl < 0), None if breakeven
        
        Note:
            Breakeven trades (won=None) do not affect the loss streak.
            Only actual losses (won=False) increment the streak.
            Wins (won=True) reset the streak to 0.
        """
        # Reset daily state if new session
        trade_date = trade.entry_timestamp.date()
        if trade_date != self._daily_state.get("last_session_date"):
            self._daily_state["consecutive_losses"] = 0
            self._daily_state["daily_pnl"] = 0.0
            self._daily_state["last_session_date"] = trade_date
            logger.debug(
                f"Session reset on {trade_date}: consecutive_losses=0, daily_pnl=0.0"
            )

        # Update consecutive losses
        if won is True:
            # Win: reset streak
            self._daily_state["consecutive_losses"] = 0
            logger.debug(f"Win recorded: consecutive_losses reset to 0")
        elif won is False:
            # Loss: increment streak
            self._daily_state["consecutive_losses"] += 1
            logger.debug(
                f"Loss recorded: consecutive_losses now {self._daily_state['consecutive_losses']}"
            )
        # If won is None (breakeven): do nothing, streak unchanged

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
            4. Micro structure invalidation (1m structure break)
            5. DXY flip
            6. Setup window expiration
            7. Daily risk breach
        """
        # First update state with current candle
        self.update_state(trade, candle, features)

        # Priority 1: SL/TP (with grace period protection)
        should_exit, reason = self.check_sl_tp(trade, candle, bars_elapsed)
        if should_exit:
            return should_exit, reason

        # Check invalidation grace period
        invalidation_grace = GRACE_PERIODS.get(trade.setup_type, {}).get("invalidation", 0)
        skip_invalidations = bars_elapsed < invalidation_grace

        # Priority 2: +1R time limit (with September time-stop protection)
        month = candle.timestamp.month if hasattr(candle.timestamp, 'month') else None
        is_invalid, reason = self.check_no_1r_reached(trade, bars_elapsed, candle, month)
        if is_invalid:
            return is_invalid, reason

        # Skip remaining invalidation checks during grace period
        if skip_invalidations:
            return False, None

        # Priority 3: VWAP invalidation
        is_invalid, reason = self.check_vwap_invalidation(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Priority 4: Micro structure invalidation (1m structure break)
        is_invalid, reason = self.check_micro_structure_invalidation(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Priority 5: DXY flip
        is_invalid, reason = self.check_dxy_flip(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Priority 6: Setup window expiration
        is_invalid, reason = self.check_setup_window_expired(trade, candle, features)
        if is_invalid:
            return is_invalid, reason

        # Priority 7: Daily risk breach
        is_invalid, reason = self.check_daily_risk_breach(trade, candle)
        if is_invalid:
            return is_invalid, reason

        return False, None

    def restore_trade_state(
        self, trade_id: str, reached_1r: bool = False, vwap_reclaimed: bool = False
    ) -> None:
        """Restore trade state from persistence (for service restart recovery).

        Args:
            trade_id: Trade ID to restore
            reached_1r: Whether trade has reached +1R
            vwap_reclaimed: Whether VWAP has been reclaimed (for FADE setups)
        """
        self._trade_states[trade_id] = {
            "reached_1r": reached_1r,
            "vwap_reclaimed": vwap_reclaimed,
        }
        logger.debug(
            f"Restored state for trade {trade_id}: reached_1r={reached_1r}, "
            f"vwap_reclaimed={vwap_reclaimed}"
        )

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


