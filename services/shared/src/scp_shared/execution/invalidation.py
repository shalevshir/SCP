"""Trade invalidation checker for streaming execution.

Simplified version adapted from backtester/invalidations.py for real-time use.
Focuses on essential invalidation rules for production trading.
"""

import math
from datetime import datetime
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

# DXY_CONTINUATION tiered time stops (replaces hard 20-bar limit)
# Allows continuation trades to "breathe" while still enforcing discipline
DXY_CONTINUATION_TIME_TIERS = {
    "de_risk_bars": 30,  # De-risk if not +0.5R by this bar
    "de_risk_r_threshold": 0.5,  # Must be at least this R to avoid de-risk
    "exit_bars": 60,  # Exit if not +1R AND structure deteriorated
    "hard_exit_bars": 90,  # Hard exit regardless of structure (prevents infinite hold)
}

# DXY flip persistence for DXY_CONTINUATION (replaces immediate exit)
# Correlation is noisy (~50% any_positive); require persistence before exit
DXY_CONTINUATION_FLIP_BARS = 5  # Require 5 consecutive bars of flip condition

# Phase 2: Runner unlock configuration
DXY_CONTINUATION_RUNNER_CONFIG = {
    "unlock_window_bars": 15,  # ONLY bars, no minutes (backtest determinism)
    "be_buffer_r": 0.10,  # 0.1R buffer in R terms
}

# Phase 2: Runner unlock fallback configuration (Section 4-6 of spec)
# TODO Phase 2: Implement Fallback B (HTF Room Gate) - unlock if room_R >= 1.5 to HTF target
# TODO Phase 2: Implement Fallback C (VWAP Separation Hold) - unlock if >=8/10 bars above VWAP + slope
DXY_CONTINUATION_RUNNER_FALLBACK_CONFIG = {
    # Hard invalidation (Section 4)
    "dxy_misaligned_exit_bars": 5,  # Exit if dxy_aligned==False for this many bars
    # Fallback A: Hold + Impulse (Section 6)
    "hold_buffer_r": 0.25,  # Hold within 0.25R of TP1
    "impulse_body_ratio_threshold": 0.6,  # Body ratio for impulse candle
    # Post-unlock management (Section 8)
    "tp2_max_r": 4.0,  # Cap TP2 at 4R
    "tp2_default_r": 3.0,  # Fallback TP2 if no HTF target
    # TODO Phase 2: Add Fallback B config: "min_runner_room_r": 1.5
    # TODO Phase 2: Add Fallback C config: "vwap_hold_bars": 8, "vwap_lookback": 10
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
        ...     is_invalid, reason, action = checker.check_all(trade, candle, bars_elapsed, features)
        ...     if action == "partial_profit":
        ...         # Handle partial profit at +1R
        ...         pass
        ...     if is_invalid:
        ...         break
    """

    def __init__(
        self, pdll_limit: float | None = None, vwap_hold_confirm_bars: int = 2
    ) -> None:
        """Initialize invalidation checker with empty state.

        Args:
            pdll_limit: Permitted Daily Loss Limit in points (optional).
                If provided, enables PDLL breach detection in check_daily_risk_breach.
            vwap_hold_confirm_bars: Number of consecutive bars required to confirm VWAP hold (default: 2).
                Implements SOP Section 3.6 "Hold" definition.
        """
        self._trade_states: dict[str, dict[str, Any]] = {}
        # Track consecutive invalidation bars for FADE setups (2-bar confirmation)
        self._fade_invalidation_count: dict[str, int] = {}
        # Track consecutive DXY flip bars for VWAP_RECLAIM (3-bar persistence required)
        self._dxy_flip_count: dict[str, int] = {}
        # Track consecutive DXY flip bars for DXY_CONTINUATION (5-bar persistence required)
        self._dxy_continuation_flip_count: dict[str, int] = {}
        # Track consecutive VWAP invalidation bars for VWAP_RECLAIM (N-bar confirmation per SOP Section 3.6)
        self._vwap_reclaim_invalidation_count: dict[str, int] = {}
        self._vwap_hold_confirm_bars = vwap_hold_confirm_bars
        # Daily state for risk breach checking
        self._daily_state: dict[str, Any] = {
            "consecutive_losses": 0,
            "daily_pnl": 0.0,
            "last_session_date": None,
            "pdll": pdll_limit,  # Store PDLL limit for breach detection
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
                # DXY_CONTINUATION-specific state
                "reached_half_r": False,  # +0.5R milestone for tiered time stop
                "partial_taken": False,  # 40% taken at +1R
                "breakeven_set": False,  # SL moved to entry (legacy)
                "de_risked": False,  # Position de-risked at 30 bars
                # Phase 2.0: Explicit BE tracking (separate from partial)
                "be_set": False,  # BE explicitly set
                "be_price": None,  # BE price with buffer
                "be_set_bar_idx": None,  # Bar when BE was set
                "tp1_hit_bar_idx": None,  # Bar when +1R was hit
                # Phase 2: Runner unlock state
                "runner_unlocked": False,
                "runner_unlock_bar_idx": None,
                "runner_unlock_reason": None,  # "micro_bos", "hold_impulse"
                # Phase 2: Hard invalidation tracking
                "dxy_misaligned_bars": 0,  # Counter for consecutive dxy_aligned==False
                # Phase 2: Fallback A tracking (Hold + Impulse)
                "min_low_since_tp1": None,  # For long: track lowest low since TP1
                "max_high_since_tp1": None,  # For short: track highest high since TP1
                "impulse_detected": False,  # Track if impulse seen in window
                "prior_bar_high": None,  # For impulse check: prior bar's high
                "prior_bar_low": None,  # For impulse check: prior bar's low
            }
        return self._trade_states[trade_id]

    def update_state(
        self, trade: TradeRecord, candle: Candle, features: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Update trade state based on current candle.

        Tracks whether +1R has been reached, VWAP reclaim status, and
        returns management actions for DXY_CONTINUATION partial profit.

        Args:
            trade: Open trade to track
            candle: Current candle to check
            features: Optional feature dictionary for VWAP tracking

        Returns:
            Management action dict if action needed, None otherwise.
            Action dict format: {"action": "partial_profit", "close_pct": 40, "move_sl_to_breakeven": True}
        """
        state = self._get_trade_state(trade.trade_id)

        # Check if +1R reached (convert to float to handle Decimal types from production)
        if not state["reached_1r"]:
            entry_price = float(trade.entry_price)
            risk_amount = float(trade.risk_amount) if trade.risk_amount else 0
            candle_high = float(candle.high)
            candle_low = float(candle.low)

            r1_price = entry_price + risk_amount  # +1R for long
            if trade.direction == "short":
                r1_price = entry_price - risk_amount  # +1R for short

            # Check if candle reached +1R
            if trade.direction == "long":
                if candle_high >= r1_price:
                    state["reached_1r"] = True
                    logger.debug(
                        f"Trade {trade.trade_id} reached +1R at {candle.timestamp}"
                    )
            else:  # short
                if candle_low <= r1_price:
                    state["reached_1r"] = True
                    logger.debug(
                        f"Trade {trade.trade_id} reached +1R at {candle.timestamp}"
                    )

        # DXY_CONTINUATION: Return partial profit action when +1R reached
        # Take 40% at +1R (per spec), move SL to BE+buffer, let runner target TP2
        if (
            trade.setup_type == "DXY_CONTINUATION"
            and state["reached_1r"]
            and not state.get("partial_taken")
        ):
            state["partial_taken"] = True
            state["breakeven_set"] = True  # Legacy field

            # Phase 2.0: Calculate BE price with 0.1R buffer
            # CRITICAL: Use risk_points (price units), NOT risk_amount (money)
            be_buffer_r = 0.10  # 0.1R buffer
            risk_points = trade.risk_points
            if risk_points is None:
                # Fallback: compute from entry/sl if risk_points not set
                risk_points = abs(float(trade.entry_price) - float(trade.sl_price))

            be_buffer_points = be_buffer_r * risk_points
            if trade.direction == "long":
                be_price = float(trade.entry_price) + be_buffer_points
            else:
                be_price = float(trade.entry_price) - be_buffer_points

            # Update explicit BE state
            state["be_set"] = True
            state["be_price"] = be_price
            # Note: be_set_bar_idx and tp1_hit_bar_idx set by caller with current_bar_idx

            logger.info(
                f"Trade {trade.trade_id} DXY_CONTINUATION: +1R reached, "
                f"triggering partial profit (40%) + BE at {be_price:.2f} "
                f"(entry {trade.entry_price} + {be_buffer_points:.2f} buffer)"
            )
            return {
                "action": "partial_profit",
                "close_pct": 40,  # Per spec: partial_pct = 0.40
                "move_sl_to_breakeven": True,
                "new_sl_price": be_price,  # BE with buffer, not exact entry
                "be_price": be_price,  # Explicit BE price
                "be_buffer_r": be_buffer_r,  # Buffer in R terms
            }

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

        return None

    def check_runner_unlock(
        self,
        trade: TradeRecord,
        candle: Candle,
        current_bar_idx: int,
        features: dict[str, Any] | None,
        htf_bias: dict[str, Any] | None = None,
    ) -> tuple[str | None, str | None]:
        """Check if runner should be unlocked, invalidated, or closed at market.

        Phase-2 runner unlock logic for DXY_CONTINUATION trades (per spec):
        1. HARD INVALIDATION (checked first) - exit if thesis broken
        2. PRIMARY UNLOCK (Mode A) - post-TP1 BOS in trade direction
        3. FALLBACK UNLOCK (Fallback A) - hold + impulse continuation
        4. WINDOW EXPIRY - close at market if no unlock within 15 bars

        Args:
            trade: Open trade to check (must be DXY_CONTINUATION with partial taken)
            candle: Current candle
            current_bar_idx: Current bar index
            features: Feature dict with BOS detection fields
            htf_bias: HTF bias dict with dxy_aligned, chop_detected, conflict_detected

        Returns:
            Tuple of (action, reason) where action is:
            - "exit_runner": Hard invalidation, exit remainder immediately
            - "unlock_runner": Runner unlocked (BOS or fallback), target TP2
            - "close_at_market": Window expired without unlock
            - None: Still waiting for unlock (no action needed)
        """
        state = self._get_trade_state(trade.trade_id)

        # Pre-conditions: only applies to DXY_CONTINUATION after partial taken
        if trade.setup_type != "DXY_CONTINUATION":
            return None, None

        if not state.get("partial_taken"):
            return None, None

        # Already unlocked or already exited at market
        if state.get("runner_unlocked"):
            return None, None

        # Get TP1 hit bar from trade record or internal state
        tp1_hit_bar = trade.tp1_hit_bar_idx
        if tp1_hit_bar is None:
            tp1_hit_bar = state.get("tp1_hit_bar_idx")
        if tp1_hit_bar is None:
            # TP1 not recorded yet - can't proceed
            logger.debug(
                f"Trade {trade.trade_id}: tp1_hit_bar_idx not set, cannot check runner unlock"
            )
            return None, None

        # Get config
        unlock_window = DXY_CONTINUATION_RUNNER_CONFIG["unlock_window_bars"]
        bars_since_tp1 = current_bar_idx - tp1_hit_bar

        # === STEP 1: HARD INVALIDATION (checked FIRST per spec Section 4) ===
        action, reason = self.check_runner_hard_invalidation(
            trade, candle, current_bar_idx, features, htf_bias
        )
        if action is not None:
            return action, reason

        # === STEP 2: PRIMARY UNLOCK (Mode A - Post-TP1 BOS) ===
        if features is not None:
            bos_detected = features.get("bos_detected", False)
            bos_direction = features.get("bos_direction")

            # BOS must be detected on THIS bar (bos_detected=True means current bar)
            # The BOS is inherently post-TP1 because we're checking AFTER TP1 was hit
            if bos_detected and bos_direction is not None:
                expected_bos = "bullish" if trade.direction == "long" else "bearish"
                if bos_direction == expected_bos:
                    # Unlock the runner!
                    state["runner_unlocked"] = True
                    state["runner_unlock_bar_idx"] = current_bar_idx
                    state["runner_unlock_reason"] = "micro_bos"
                    reason = (
                        f"micro_bos: Post-TP1 {bos_direction} BOS at bar {current_bar_idx} "
                        f"({bars_since_tp1} bars after TP1)"
                    )
                    logger.info(f"Trade {trade.trade_id} RUNNER UNLOCKED: {reason}")
                    return "unlock_runner", reason

        # === STEP 3: FALLBACK UNLOCK (Fallback A - Hold + Impulse) ===
        # Only check if primary BOS hasn't triggered
        action, reason = self.check_runner_fallback_unlock(
            trade, candle, current_bar_idx, features
        )
        if action is not None:
            state["runner_unlocked"] = True
            state["runner_unlock_bar_idx"] = current_bar_idx
            state["runner_unlock_reason"] = "hold_impulse"
            return action, reason

        # === STEP 4: WINDOW EXPIRY ===
        if bars_since_tp1 >= unlock_window:
            # Window expired - close at market (NOT at synthetic BE fill)
            reason = (
                f"Runner unlock window expired: {bars_since_tp1} bars since TP1 "
                f"(max {unlock_window}), no unlock achieved"
            )
            logger.info(f"Trade {trade.trade_id} RUNNER CLOSE AT MARKET: {reason}")
            return "close_at_market", reason

        # Still within window, waiting for unlock
        logger.debug(
            f"Trade {trade.trade_id}: Runner candidate, bar {bars_since_tp1}/{unlock_window} "
            f"since TP1, waiting for BOS or fallback"
        )
        return None, None

    def check_runner_hard_invalidation(
        self,
        trade: TradeRecord,
        candle: Candle,
        _current_bar_idx: int,
        _features: dict[str, Any] | None,
        htf_bias: dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        """Check hard invalidation conditions for runner candidate.

        These conditions indicate the continuation thesis is BROKEN and
        remaining position should be exited immediately.

        Checked BEFORE any unlock attempt per spec Section 4.

        Hard invalidation conditions (in order):
        1. chop_detected == True -> exit immediately
        2. htf_conflict_detected == True -> exit immediately
        3. dxy_aligned == False for >= 5 bars -> exit (requires counter)

        Args:
            trade: Open trade (must be DXY_CONTINUATION with partial taken)
            candle: Current candle
            current_bar_idx: Current bar index
            features: FeaturesMessage as dict
            htf_bias: HTFBiasMessage as dict (contains dxy_aligned, chop_detected, conflict_detected)

        Returns:
            Tuple of (action, reason):
            - ("exit_runner", "chop_detected") if chop detected
            - ("exit_runner", "htf_conflict_detected") if HTF conflict
            - ("exit_runner", "dxy_misaligned_5_bars") if DXY misaligned >= 5 bars
            - (None, None) if no invalidation
        """
        # Pre-conditions
        if trade.setup_type != "DXY_CONTINUATION":
            return None, None

        state = self._get_trade_state(trade.trade_id)
        if not state.get("partial_taken"):
            return None, None

        if htf_bias is None:
            # Cannot check hard invalidation without HTF data
            logger.debug(
                f"Trade {trade.trade_id}: No HTF bias, skipping hard invalidation check"
            )
            return None, None

        config = DXY_CONTINUATION_RUNNER_FALLBACK_CONFIG

        # Check 1: chop_detected == True => immediate exit
        if htf_bias.get("chop_detected", False):
            reason = "chop_detected: continuation thesis invalidated"
            logger.info(f"Trade {trade.trade_id} RUNNER HARD INVALIDATION: {reason}")
            return "exit_runner", reason

        # Check 2: htf_conflict_detected == True => immediate exit
        if htf_bias.get("conflict_detected", False):
            conflict_reason = htf_bias.get("conflict_reason", "unknown")
            reason = f"htf_conflict_detected: {conflict_reason}"
            logger.info(f"Trade {trade.trade_id} RUNNER HARD INVALIDATION: {reason}")
            return "exit_runner", reason

        # Check 3: dxy_aligned == False for >= 5 consecutive bars
        dxy_aligned = htf_bias.get("dxy_aligned", True)  # Default to aligned

        if not dxy_aligned:
            state["dxy_misaligned_bars"] = state.get("dxy_misaligned_bars", 0) + 1
            if state["dxy_misaligned_bars"] >= config["dxy_misaligned_exit_bars"]:
                reason = (
                    f"dxy_misaligned_{config['dxy_misaligned_exit_bars']}_bars: "
                    f"correlation broken for {state['dxy_misaligned_bars']} bars"
                )
                logger.info(f"Trade {trade.trade_id} RUNNER HARD INVALIDATION: {reason}")
                return "exit_runner", reason
            else:
                logger.debug(
                    f"Trade {trade.trade_id}: dxy_misaligned bar "
                    f"{state['dxy_misaligned_bars']}/{config['dxy_misaligned_exit_bars']}"
                )
        else:
            # Reset counter when DXY realigns
            if state.get("dxy_misaligned_bars", 0) > 0:
                logger.debug(f"Trade {trade.trade_id}: DXY realigned, resetting counter")
            state["dxy_misaligned_bars"] = 0

        return None, None

    def check_runner_fallback_unlock(
        self,
        trade: TradeRecord,
        candle: Candle,
        current_bar_idx: int,
        _features: dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        """Check fallback unlock conditions (Fallback A: Hold + Impulse).

        Only called if primary BOS unlock hasn't triggered.

        Fallback A (RECOMMENDED per spec Section 6):
        - Hold: price stays within 0.25R of TP1 since TP1 hit
        - Impulse: close > prior_high OR body_ratio >= 0.6

        Both conditions must be met to unlock.

        Args:
            trade: Open trade
            candle: Current candle
            current_bar_idx: Current bar index
            features: FeaturesMessage as dict (needs OHLC)

        Returns:
            Tuple of (action, reason):
            - ("unlock_runner", "hold_impulse: ...details...") if fallback unlocks
            - (None, None) if conditions not met
        """
        state = self._get_trade_state(trade.trade_id)
        config = DXY_CONTINUATION_RUNNER_FALLBACK_CONFIG

        # Get TP1 price and R
        entry_price = float(trade.entry_price)
        risk_points = trade.risk_points
        if risk_points is None:
            risk_points = abs(entry_price - float(trade.sl_price))

        if trade.direction == "long":
            tp1_price = entry_price + risk_points  # +1R
        else:
            tp1_price = entry_price - risk_points  # -1R for short

        # === HOLD CONDITION ===
        hold_buffer = config["hold_buffer_r"] * risk_points  # 0.25R

        # Track extremes since TP1
        if trade.direction == "long":
            # Track min low since TP1
            if state.get("min_low_since_tp1") is None:
                state["min_low_since_tp1"] = candle.low
            else:
                state["min_low_since_tp1"] = min(state["min_low_since_tp1"], candle.low)

            hold_floor = tp1_price - hold_buffer
            hold_met = state["min_low_since_tp1"] >= hold_floor
        else:  # short
            # Track max high since TP1
            if state.get("max_high_since_tp1") is None:
                state["max_high_since_tp1"] = candle.high
            else:
                state["max_high_since_tp1"] = max(state["max_high_since_tp1"], candle.high)

            hold_ceiling = tp1_price + hold_buffer
            hold_met = state["max_high_since_tp1"] <= hold_ceiling

        # === IMPULSE CONDITION ===
        # Check on THIS bar if:
        # 1. close > prior_high (long) / close < prior_low (short)
        # 2. OR body_ratio >= 0.6

        prior_high = state.get("prior_bar_high")
        prior_low = state.get("prior_bar_low")

        # Calculate body ratio for this candle
        candle_range = candle.high - candle.low
        body_size = abs(candle.close - candle.open)
        body_ratio = body_size / max(candle_range, 0.001)

        impulse_met_this_bar = False
        impulse_reason = ""

        if trade.direction == "long":
            if prior_high is not None and candle.close > prior_high:
                impulse_met_this_bar = True
                impulse_reason = f"close {candle.close:.2f} > prior_high {prior_high:.2f}"
            elif body_ratio >= config["impulse_body_ratio_threshold"]:
                impulse_met_this_bar = True
                impulse_reason = f"body_ratio {body_ratio:.2f} >= {config['impulse_body_ratio_threshold']}"
        else:  # short
            if prior_low is not None and candle.close < prior_low:
                impulse_met_this_bar = True
                impulse_reason = f"close {candle.close:.2f} < prior_low {prior_low:.2f}"
            elif body_ratio >= config["impulse_body_ratio_threshold"]:
                impulse_met_this_bar = True
                impulse_reason = f"body_ratio {body_ratio:.2f} >= {config['impulse_body_ratio_threshold']}"

        # Track impulse if detected (persists once seen in window)
        if impulse_met_this_bar:
            state["impulse_detected"] = True
            state["impulse_detected_bar"] = current_bar_idx
            state["impulse_reason"] = impulse_reason

        # Update prior bar for next iteration
        state["prior_bar_high"] = candle.high
        state["prior_bar_low"] = candle.low

        # === UNLOCK CHECK ===
        # Both hold AND impulse (at any point in window) must be met
        impulse_ever_detected = state.get("impulse_detected", False)

        if hold_met and impulse_ever_detected:
            saved_impulse_reason = state.get("impulse_reason", impulse_reason)
            reason = (
                f"hold_impulse: hold within {config['hold_buffer_r']}R "
                f"(floor/ceiling maintained), {saved_impulse_reason}"
            )
            logger.info(f"Trade {trade.trade_id} RUNNER FALLBACK UNLOCK: {reason}")
            return "unlock_runner", reason

        # Log status for debugging
        logger.debug(
            f"Trade {trade.trade_id}: Fallback A status - hold_met={hold_met}, "
            f"impulse_detected={impulse_ever_detected}"
        )

        return None, None

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

        # Convert to float to handle Decimal types from production
        sl_price = float(trade.sl_price)
        tp_price = float(trade.tp_price)
        candle_high = float(candle.high)
        candle_low = float(candle.low)

        # Check stop-loss
        if trade.direction == "long":
            if candle_low <= sl_price:
                reason = f"SL_HIT: low {candle_low:.2f} <= SL {sl_price:.2f}"
                logger.info(f"Trade {trade.trade_id} stopped out: {reason}")
                return True, reason
        else:  # short
            if candle_high >= sl_price:
                reason = f"SL_HIT: high {candle_high:.2f} >= SL {sl_price:.2f}"
                logger.info(f"Trade {trade.trade_id} stopped out: {reason}")
                return True, reason

        # Check take-profit
        if trade.direction == "long":
            if candle_high >= tp_price:
                reason = f"TP_HIT: high {candle_high:.2f} >= TP {tp_price:.2f}"
                logger.info(f"Trade {trade.trade_id} take profit hit: {reason}")
                return True, reason
        else:  # short
            if candle_low <= tp_price:
                reason = f"TP_HIT: low {candle_low:.2f} <= TP {tp_price:.2f}"
                logger.info(f"Trade {trade.trade_id} take profit hit: {reason}")
                return True, reason

        return False, None

    def check_no_1r_reached(
        self,
        trade: TradeRecord,
        bars_elapsed: int,
        candle: Candle | None = None,
        month: int | None = None,
        features: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """Check if +1R not reached within time limits (with optional protection).

        Args:
            trade: Open trade to check
            bars_elapsed: Number of bars since entry
            candle: Current candle (for time_stop_protection calculation)
            month: Current month (for September defensive mode)
            features: Optional features dict (for DXY_CONTINUATION HTF structure check)

        Returns:
            Tuple of (is_invalid, reason, action)
            - action can be: "exit", "de_risk", or None

        SOP Rules:
            - VWAP_RECLAIM: Must reach +1R within 60 bars
            - DXY_CONTINUATION: Tiered approach (de-risk at 30, exit at 60 if deteriorated)
            - VWAP_FADE: Must reach +1R within 10 bars

        Time-Stop Protection (narrowly scoped per CEO directive):
            - VWAP_RECLAIM only
            - September defensive mode only
            - Exit at half time limit if < -0.2R
            - Logged as 'time_stop_protection' for separate measurement

        DXY_CONTINUATION Tiered Time Stops:
            - Allows continuation trades to "breathe" during pullback/base phases
            - 30 bars: de-risk if not +0.5R (tighten SL, don't exit)
            - 60 bars: exit only if HTF structure has deteriorated
        """
        # DXY_CONTINUATION: Use tiered time stops instead of hard 20-bar limit
        if trade.setup_type == "DXY_CONTINUATION" and candle is not None:
            return self._check_dxy_continuation_tiered_time_stop(
                trade, bars_elapsed, candle, features
            )

        # Get time limit for this setup type (non-DXY_CONTINUATION)
        time_limit = R1_TIME_LIMITS.get(trade.setup_type, 20)

        # TIME-STOP PROTECTION: Early exit for deep red losses (VWAP_RECLAIM + September only)
        if (
            trade.setup_type == "VWAP_RECLAIM"
            and candle is not None
            and month == 9
            and bars_elapsed >= time_limit // 2
        ):
            # Calculate current R (convert to float to handle Decimal types)
            entry_price = float(trade.entry_price)
            close_price = float(candle.close)
            risk_amount = float(trade.risk_amount) if trade.risk_amount else 0

            if trade.direction == "long":
                current_pnl = close_price - entry_price
            else:
                current_pnl = entry_price - close_price
            current_r = current_pnl / risk_amount if risk_amount > 0 else 0

            # Early exit if deep red (< -0.2R)
            if current_r < -0.2:
                reason = f"time_stop_protection: {current_r:.2f}R at bar {bars_elapsed} (September mode)"
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason, "exit"

        # Standard time-stop check: only at the time limit
        if bars_elapsed < time_limit:
            return False, None, None

        # Check if +1R was reached
        state = self._get_trade_state(trade.trade_id)
        if not state["reached_1r"]:
            reason = (
                f"+1R not reached within {time_limit} bars " f"({trade.setup_type})"
            )
            logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
            return True, reason, "exit"

        return False, None, None

    def _check_dxy_continuation_tiered_time_stop(
        self,
        trade: TradeRecord,
        bars_elapsed: int,
        candle: Candle,
        features: dict[str, Any] | None,
    ) -> tuple[bool, str | None, str | None]:
        """Tiered time stop for DXY_CONTINUATION trades.

        Continuation trades need room to "breathe" during pullback/base phases.
        Instead of hard 20-bar exit, use tiered approach:

        Tier 1 (30 bars): De-risk if not +0.5R
            - Signal to tighten SL (e.g., to breakeven or smaller loss)
            - Does NOT exit the trade

        Tier 2 (60 bars): Exit only if structure deteriorated
            - If HTF (15m) structure still intact, continue holding
            - If HTF structure broken, exit

        Args:
            trade: Open trade to check
            bars_elapsed: Number of bars since entry
            candle: Current candle
            features: Feature dict for HTF structure check

        Returns:
            Tuple of (should_exit, reason, action)
            - action: "de_risk" at tier 1, "exit" at tier 2, None otherwise
        """
        state = self._get_trade_state(trade.trade_id)

        # Calculate current R (convert to float to handle Decimal types from production)
        entry_price = float(trade.entry_price)
        close_price = float(candle.close)
        risk_amount = float(trade.risk_amount) if trade.risk_amount else 0

        if trade.direction == "long":
            current_pnl = close_price - entry_price
        else:
            current_pnl = entry_price - close_price
        current_r = current_pnl / risk_amount if risk_amount > 0 else 0

        # Track +0.5R milestone
        r_threshold = DXY_CONTINUATION_TIME_TIERS["de_risk_r_threshold"]
        if current_r >= r_threshold and not state.get("reached_half_r"):
            state["reached_half_r"] = True
            logger.debug(f"Trade {trade.trade_id} reached +{r_threshold}R milestone")

        # Hard exit cap: exit at 90 bars regardless of structure (prevents infinite hold)
        hard_exit_bars = DXY_CONTINUATION_TIME_TIERS["hard_exit_bars"]
        if bars_elapsed >= hard_exit_bars and not state.get("reached_1r"):
            reason = (
                f"+1R not reached within {hard_exit_bars} bars "
                f"(DXY_CONTINUATION hard cap)"
            )
            logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
            return True, reason, "exit"

        # Tier 2: Exit at 60 bars if not +1R AND structure deteriorated
        # Check this FIRST so we don't trigger de-risk at bar 60+
        exit_bars = DXY_CONTINUATION_TIME_TIERS["exit_bars"]
        if bars_elapsed >= exit_bars and not state.get("reached_1r"):
            # Check if HTF structure has deteriorated
            structure_ok = self._check_htf_structure_intact(trade, features)

            if not structure_ok:
                reason = (
                    f"+1R not reached within {exit_bars} bars AND "
                    f"HTF structure deteriorated (DXY_CONTINUATION)"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason, "exit"
            # Structure still intact - continue to other checks (don't return here)
            # Trade may still exit via DXY flip, HTF invalidation, or hard cap

        # Tier 1: De-risk at 30 bars if not +0.5R (only between 30-60 bars)
        de_risk_bars = DXY_CONTINUATION_TIME_TIERS["de_risk_bars"]
        if (
            bars_elapsed >= de_risk_bars
            and not state.get("de_risked")
            and not state.get("reached_half_r")
        ):
            state["de_risked"] = True
            reason = (
                f"de_risk: {current_r:.2f}R at bar {bars_elapsed} "
                f"(< +{r_threshold}R threshold)"
            )
            logger.info(f"Trade {trade.trade_id}: {reason}")
            # Signal de-risk action, but don't exit
            return False, reason, "de_risk"

        return False, None, None

    def _check_htf_structure_intact(
        self, trade: TradeRecord, features: dict[str, Any] | None
    ) -> bool:
        """Check if HTF (15m) structure is still intact for the trade direction.

        Args:
            trade: Open trade to check
            features: Feature dict with HTF structure label

        Returns:
            True if structure supports trade direction, False if deteriorated
        """
        if features is None:
            # No features = assume structure deteriorated (safer to exit)
            logger.debug(
                f"Trade {trade.trade_id}: No features provided, assuming HTF deteriorated"
            )
            return False

        htf_structure = features.get("htf_structure_label") or features.get(
            "structure_15m"
        )

        if htf_structure is None:
            # No HTF structure data = assume deteriorated (safer to exit)
            logger.debug(
                f"Trade {trade.trade_id}: No HTF structure label, assuming deteriorated"
            )
            return False

        # Long trades: structure intact if HH or HL
        if trade.direction == "long":
            return htf_structure in ("HH", "HL")

        # Short trades: structure intact if LH or LL
        return htf_structure in ("LH", "LL")

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
            # RECLAIM setups require N CONSECUTIVE bars meeting invalidation criteria
            # Implements SOP Section 3.6 "Hold" definition
            trade_id = trade.trade_id
            condition_met = False

            if trade.direction == "long":
                # Long reclaim: invalid if price closes below VWAP
                if candle.close < vwap:
                    condition_met = True
            else:  # short
                # Short reclaim: invalid if price closes above VWAP
                if candle.close > vwap:
                    condition_met = True

            # Track consecutive bars meeting condition
            if condition_met:
                # Increment counter
                current_count = self._vwap_reclaim_invalidation_count.get(trade_id, 0)
                self._vwap_reclaim_invalidation_count[trade_id] = current_count + 1

                # Require N consecutive bars (configurable, default 2)
                if (
                    self._vwap_reclaim_invalidation_count[trade_id]
                    >= self._vwap_hold_confirm_bars
                ):
                    reason = (
                        f"VWAP invalidation ({self._vwap_hold_confirm_bars}-bar confirmed): "
                        f"close {candle.close:.2f} {'<' if trade.direction == 'long' else '>'} "
                        f"VWAP {vwap:.2f}"
                    )
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    # Clear counter after invalidation
                    self._vwap_reclaim_invalidation_count[trade_id] = 0
                    return True, reason
            else:
                # Condition NOT met - reset counter
                if trade_id in self._vwap_reclaim_invalidation_count:
                    self._vwap_reclaim_invalidation_count[trade_id] = 0

        elif trade.setup_type == "VWAP_FADE":
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
                    slope_str = (
                        f", slope {vwap_slope:.4f}" if vwap_slope is not None else ""
                    )
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

        DXY_CONTINUATION SPECIAL HANDLING:
        Continuation trades EXPECT micro breaks during pullback/noise.
        Do NOT exit on 1m micro breaks - use HTF-based invalidation only.

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
            - DXY_CONTINUATION: micro break ignored - uses HTF invalidation only
        """
        # Need structure info from features
        if features is None:
            return False, None

        # DXY_CONTINUATION: Skip micro structure invalidation entirely
        # Continuation trades expect micro breaks during pullback/noise
        # Use HTF-based invalidation instead
        if trade.setup_type == "DXY_CONTINUATION":
            return self._check_htf_invalidation_dxy_continuation(trade, candle, features)

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
                htf_structure = features.get("htf_structure_label") or features.get(
                    "structure_15m"
                )
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

    def _check_htf_invalidation_dxy_continuation(
        self, trade: TradeRecord, candle: Candle, features: dict[str, Any] | None
    ) -> tuple[bool, str | None]:
        """HTF-based invalidation for DXY_CONTINUATION trades.

        Continuation trades expect micro (1m) structure breaks during pullback/noise.
        Instead of exiting on micro breaks, we use higher-timeframe invalidation:

        Exit only if:
        1. 15m structure breaks against direction (HTF thesis broken), OR
        2. Price closes back through VWAP with EMA stack flip (trend failure)

        Args:
            trade: Open trade to check
            candle: Current candle
            features: Feature dictionary containing HTF structure and indicators

        Returns:
            Tuple of (is_invalid, reason)
        """
        if features is None:
            return False, None

        # Check 1: 15m structure break against direction
        htf_structure = features.get("htf_structure_label") or features.get(
            "structure_15m"
        )
        if htf_structure is not None:
            if trade.direction == "long" and htf_structure in ("LH", "LL"):
                reason = (
                    f"HTF (15m) structure break: {htf_structure} invalidates "
                    f"{trade.direction} DXY_CONTINUATION"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason
            elif trade.direction == "short" and htf_structure in ("HH", "HL"):
                reason = (
                    f"HTF (15m) structure break: {htf_structure} invalidates "
                    f"{trade.direction} DXY_CONTINUATION"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason

        # Check 2: VWAP trend failure (price closes through VWAP + EMA stack flips)
        vwap = _sanitize_float(features.get("vwap"))
        ema_9 = _sanitize_float(features.get("ema_9"))
        ema_20 = _sanitize_float(features.get("ema_20"))

        if vwap is not None:
            # Check if price violated VWAP
            vwap_violated = False
            if trade.direction == "long" and candle.close < vwap:
                vwap_violated = True
            elif trade.direction == "short" and candle.close > vwap:
                vwap_violated = True

            # Check if EMA stack has flipped (requires both EMAs)
            ema_flipped = False
            if ema_9 is not None and ema_20 is not None:
                if trade.direction == "long" and ema_9 < ema_20:
                    ema_flipped = True
                elif trade.direction == "short" and ema_9 > ema_20:
                    ema_flipped = True

            # Both conditions must be true for trend failure exit
            if vwap_violated and ema_flipped:
                reason = (
                    f"VWAP trend failure: close "
                    f"{'<' if trade.direction == 'long' else '>'} "
                    f"VWAP {vwap:.2f} + EMA stack flipped "
                    f"(EMA9={ema_9:.2f}, EMA20={ema_20:.2f})"
                )
                logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                return True, reason

        # No HTF invalidation detected - continue holding
        logger.debug(
            f"Trade {trade.trade_id} DXY_CONTINUATION: HTF structure intact, HOLDING"
        )
        return False, None

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

        # DXY_CONTINUATION: Require 5-bar persistence (no instant exits)
        # Correlation is noisy (~50% any_positive); require true contradiction to persist
        if trade.setup_type == "DXY_CONTINUATION":
            trade_id = trade.trade_id

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

            # Detect flip condition: BOTH correlations positive (true contradiction)
            # AND DXY structure flipped against trade direction
            # Tightened threshold: corr > 0 (was > -0.1) for true contradiction
            flip_detected = False

            if corr_1m is not None and corr_5m is not None:
                # True contradiction = both correlations positive
                both_positive = corr_1m > 0 and corr_5m > 0

                if trade.direction == "long":
                    # Long invalidated when DXY turns bullish (HH/HL)
                    if both_positive and dxy_structure in ("HH", "HL"):
                        flip_detected = True
                else:  # short
                    # Short invalidated when DXY turns bearish (LH/LL)
                    if both_positive and dxy_structure in ("LH", "LL"):
                        flip_detected = True

            # Track persistence - require 5 consecutive bars
            if flip_detected:
                current_count = self._dxy_continuation_flip_count.get(trade_id, 0)
                self._dxy_continuation_flip_count[trade_id] = current_count + 1

                logger.debug(
                    f"Trade {trade_id} DXY flip bar {self._dxy_continuation_flip_count[trade_id]}"
                    f"/{DXY_CONTINUATION_FLIP_BARS} (corr_1m={corr_1m:.3f}, "
                    f"corr_5m={corr_5m:.3f}, dxy_structure={dxy_structure})"
                )

                # Exit only after persistence threshold reached
                if self._dxy_continuation_flip_count[trade_id] >= DXY_CONTINUATION_FLIP_BARS:
                    reason = (
                        f"DXY flip ({DXY_CONTINUATION_FLIP_BARS}-bar confirmed): "
                        f"corr_1m={corr_1m:.3f}, corr_5m={corr_5m:.3f}, "
                        f"dxy_structure={dxy_structure}"
                    )
                    # Reset counter after exit
                    self._dxy_continuation_flip_count[trade_id] = 0
                    logger.info(f"Trade {trade.trade_id} invalidated: {reason}")
                    return True, reason
            else:
                # Condition NOT met - reset counter
                if trade_id in self._dxy_continuation_flip_count:
                    self._dxy_continuation_flip_count[trade_id] = 0

            # No flip exit yet
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
        self,
        trade: TradeRecord,
        candle: Candle,
        daily_pnl_state: dict[str, Any] | None = None,
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

    def record_trade_outcome(
        self,
        trade: TradeRecord,
        won: bool | None,
        pnl_points: float | None = None,
        close_timestamp: datetime | None = None,
    ) -> None:
        """Record trade outcome to update daily state for loss streak and PnL tracking.

        Args:
            trade: Closed trade
            won: True if profitable (pnl > 0), False if loss (pnl < 0), None if breakeven
            pnl_points: Actual trade PnL in points (optional). If provided, updates daily_pnl.
                If None, only updates loss streak based on won flag.
            close_timestamp: Timestamp when trade closed (optional). If provided, uses this
                for session date determination. Otherwise falls back to trade.exit_timestamp
                if available, or trade.entry_timestamp for backward compatibility.

        Note:
            Breakeven trades (won=None) do not affect the loss streak.
            Only actual losses (won=False) increment the streak.
            Wins (won=True) reset the streak to 0.
            If pnl_points is provided, daily_pnl is updated with the actual PnL value.

            Session date is determined by the close timestamp (when the trade closed),
            not the entry timestamp. This ensures trades that span multiple days are
            attributed to the correct session (the day they closed).
        """
        # Determine session date from close timestamp (when trade closed)
        # This is critical for trades that span multiple days - they should be
        # attributed to the day they closed, not the day they opened.
        if close_timestamp is not None:
            trade_date = close_timestamp.date()
        elif trade.exit_timestamp is not None:
            trade_date = trade.exit_timestamp.date()
        else:
            # Fallback to entry_timestamp for backward compatibility
            # (e.g., when called from tests or legacy code)
            # WARNING: This is incorrect for multi-day trades and can cause:
            # - Loss/win attributed to wrong day
            # - Session date flip-flopping if trades from different entry dates
            #   close on the same day in interleaved order
            # - Incorrect loss streak and daily PnL tracking
            trade_date = trade.entry_timestamp.date()
            logger.warning(
                f"Using entry_timestamp.date() for trade {trade.trade_id} session date "
                f"(close_timestamp not provided, exit_timestamp=None). "
                f"This may cause incorrect session attribution for multi-day trades. "
                f"Entry: {trade.entry_timestamp.date()}, "
                f"Expected close date: unknown (exit_timestamp=None). "
                f"Please pass close_timestamp parameter to fix this issue."
            )

        # Reset daily state if new session
        if trade_date != self._daily_state.get("last_session_date"):
            self._daily_state["consecutive_losses"] = 0
            self._daily_state["daily_pnl"] = 0.0
            self._daily_state["last_session_date"] = trade_date
            logger.debug(
                f"Session reset on {trade_date}: consecutive_losses=0, daily_pnl=0.0"
            )

        # Update daily PnL if provided
        if pnl_points is not None:
            self._daily_state["daily_pnl"] += pnl_points
            logger.debug(
                f"Trade PnL recorded: {pnl_points:.2f} points, "
                f"daily_pnl now {self._daily_state['daily_pnl']:.2f}"
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
    ) -> tuple[bool, str | None, str | None]:
        """Check all invalidation and exit conditions.

        Args:
            trade: Open trade to check
            candle: Current candle
            bars_elapsed: Number of bars since entry
            features: Optional feature dictionary

        Returns:
            Tuple of (should_exit, reason, action)
            - action can be: "exit", "de_risk", "partial_profit", or None

        Checks (in priority order):
            1. SL/TP hit (immediate exit)
            2. +1R not reached within time limits (tiered for DXY_CONTINUATION)
            3. VWAP invalidation
            4. Micro structure invalidation (1m structure break, HTF for DXY_CONTINUATION)
            5. DXY flip (5-bar persistence for DXY_CONTINUATION)
            6. Setup window expiration
            7. Daily risk breach
        """
        # First update state with current candle
        mgmt_action = self.update_state(trade, candle, features)

        # Priority 1: SL/TP (with grace period protection)
        # Must check BEFORE partial profit - on volatile candles both can trigger
        should_exit, reason = self.check_sl_tp(trade, candle, bars_elapsed)
        if should_exit:
            return should_exit, reason, "exit"

        # Check for partial profit action from update_state (after SL/TP check)
        if mgmt_action is not None:
            action_type = mgmt_action.get("action")
            if action_type == "partial_profit":
                # Return partial profit action - does not exit the trade
                return False, "partial_profit at +1R", "partial_profit"

        # Check invalidation grace period
        invalidation_grace = GRACE_PERIODS.get(trade.setup_type, {}).get(
            "invalidation", 0
        )
        skip_invalidations = bars_elapsed < invalidation_grace

        # Priority 2: +1R time limit (with September time-stop protection / tiered for DXY_CONTINUATION)
        month = candle.timestamp.month if hasattr(candle.timestamp, "month") else None
        is_invalid, reason, action = self.check_no_1r_reached(
            trade, bars_elapsed, candle, month, features
        )
        if is_invalid:
            return is_invalid, reason, action
        # Handle de_risk action (not an exit, but signals position management)
        if action == "de_risk":
            return False, reason, "de_risk"

        # Skip remaining invalidation checks during grace period
        if skip_invalidations:
            return False, None, None

        # Priority 3: VWAP invalidation
        is_invalid, reason = self.check_vwap_invalidation(trade, candle, features)
        if is_invalid:
            return is_invalid, reason, "exit"

        # Priority 4: Micro structure invalidation (1m structure break, HTF for DXY_CONTINUATION)
        is_invalid, reason = self.check_micro_structure_invalidation(
            trade, candle, features
        )
        if is_invalid:
            return is_invalid, reason, "exit"

        # Priority 5: DXY flip (5-bar persistence for DXY_CONTINUATION)
        is_invalid, reason = self.check_dxy_flip(trade, candle, features)
        if is_invalid:
            return is_invalid, reason, "exit"

        # Priority 6: Setup window expiration
        is_invalid, reason = self.check_setup_window_expired(trade, candle, features)
        if is_invalid:
            return is_invalid, reason, "exit"

        # Priority 7: Daily risk breach
        is_invalid, reason = self.check_daily_risk_breach(trade, candle)
        if is_invalid:
            return is_invalid, reason, "exit"

        return False, None, None

    def restore_trade_state(
        self,
        trade_id: str,
        reached_1r: bool = False,
        vwap_reclaimed: bool = False,
        reached_half_r: bool = False,
        partial_taken: bool = False,
        breakeven_set: bool = False,
        de_risked: bool = False,
    ) -> None:
        """Restore trade state from persistence (for service restart recovery).

        Args:
            trade_id: Trade ID to restore
            reached_1r: Whether trade has reached +1R
            vwap_reclaimed: Whether VWAP has been reclaimed (for FADE setups)
            reached_half_r: Whether trade reached +0.5R (for DXY_CONTINUATION)
            partial_taken: Whether partial profit was taken at +1R
            breakeven_set: Whether SL was moved to breakeven
            de_risked: Whether position was de-risked at tier 1 time stop
        """
        self._trade_states[trade_id] = {
            "reached_1r": reached_1r,
            "vwap_reclaimed": vwap_reclaimed,
            "reached_half_r": reached_half_r,
            "partial_taken": partial_taken,
            "breakeven_set": breakeven_set,
            "de_risked": de_risked,
        }
        logger.debug(
            f"Restored state for trade {trade_id}: reached_1r={reached_1r}, "
            f"vwap_reclaimed={vwap_reclaimed}, reached_half_r={reached_half_r}, "
            f"partial_taken={partial_taken}, de_risked={de_risked}"
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
        if trade_id in self._dxy_continuation_flip_count:
            del self._dxy_continuation_flip_count[trade_id]
        if trade_id in self._vwap_reclaim_invalidation_count:
            del self._vwap_reclaim_invalidation_count[trade_id]

    def clear_all(self) -> None:
        """Clear all trade states."""
        self._trade_states.clear()
        self._fade_invalidation_count.clear()
        self._dxy_flip_count.clear()
        self._dxy_continuation_flip_count.clear()
        self._vwap_reclaim_invalidation_count.clear()

    def reset_daily_state(self) -> None:
        """Reset daily state to initial values while preserving PDLL limit.

        Used for testing/admin reset to clear daily tracking state:
        - consecutive_losses: reset to 0
        - daily_pnl: reset to 0.0
        - last_session_date: reset to None
        - pdll: preserved (not reset, as it's a configuration value)

        This ensures that after a reset, the InvalidationChecker doesn't
        use stale loss streaks or PnL values from before the reset.
        """
        pdll_limit = self._daily_state.get("pdll")  # Preserve PDLL limit
        self._daily_state = {
            "consecutive_losses": 0,
            "daily_pnl": 0.0,
            "last_session_date": None,
            "pdll": pdll_limit,  # Preserve configuration
        }
        logger.info("InvalidationChecker daily state reset (preserved pdll_limit)")
