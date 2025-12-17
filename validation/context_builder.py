"""Validation context builder for SCP trading bot.

This module builds ValidationContext objects from feature data, market state,
session results, and guardrail results to enable SOP validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
from common.logger import get_logger

from validation.schema import (
    BufferPhase,
    EnforcerTier,
    HTFBias,
    ValidationContext,
)

if TYPE_CHECKING:
    from rule_engine.htf.types import HTFBias as HTFBiasDataclass
    from validation.guardrails import GuardrailResult
    from validation.session_validator import SessionResult

logger = get_logger(__name__)


class ValidationContextBuilder:
    """Builds ValidationContext from feature data and market state.

    This class extracts HTF bias, DXY trending status, and other validation
    inputs from feature series and combines them with session/guardrail results
    to produce a complete ValidationContext for SOP enforcement.
    """

    def __init__(self, warn_on_missing_dxy: bool = True) -> None:
        """Initialize context builder.

        Args:
            warn_on_missing_dxy: Whether to log warnings when DXY data is missing
        """
        self._warn_on_missing_dxy = warn_on_missing_dxy

    def build_context(
        self,
        features: pd.Series,
        market_state: dict,
        session_result: SessionResult,
        guardrail_result: GuardrailResult | None = None,
        htf_bias: HTFBiasDataclass | None = None,
    ) -> ValidationContext:
        """Build ValidationContext from all inputs.

        Args:
            features: Feature series containing technical indicators
            market_state: Dict with additional market state:
                - buffer_phase: Current capital buffer phase
                - ceo_directive_active: Whether CEO directive is active
                - news_ok: Whether high-impact news is clear
                - fatigue_flag: Optional manual fatigue flag override
            session_result: Result from SessionValidator evaluation
            guardrail_result: Optional result from BehaviorGuardrails
            htf_bias: Optional HTFBias dataclass from the HTF calculator.
                If provided, uses this instead of computing a separate bias.

        Returns:
            ValidationContext ready for ValidationEngine

        Example:
            >>> builder = ValidationContextBuilder()
            >>> features = pd.Series({
            ...     "close": 2650.0,
            ...     "vwap": 2645.0,
            ...     "ema_9": 2648.0,
            ...     "ema_20": 2645.0,
            ...     "ema_50": 2640.0,
            ...     "dxy_corr": -0.75,
            ...     "structure_type": "HH",
            ... })
            >>> market_state = {
            ...     "buffer_phase": "0-5k",
            ...     "ceo_directive_active": True,
            ...     "news_ok": True,
            ... }
            >>> context = builder.build_context(features, market_state, session_result)
        """
        # Use provided HTF bias if available, otherwise compute from features
        if htf_bias is not None:
            htf_bias_enum = self._convert_htf_bias_to_enum(htf_bias)
        else:
            htf_bias_enum = self._compute_htf_bias(features)


        # Determine DXY trending status
        dxy_trending_clean = self._is_dxy_trending_clean(features)

        # Check if DXY data is available
        dxy_available = self._check_dxy_availability(features)
        if not dxy_available and self._warn_on_missing_dxy:
            logger.warning(
                "DXY data unavailable - continuation setups will be rejected"
            )

        # Extract fatigue flag (from guardrails or manual override)
        fatigue_flag = market_state.get("fatigue_flag", False)
        if guardrail_result:
            # Guardrail fatigue takes precedence

            if hasattr(guardrail_result, "__dict__"):
                # If we have access to state, check fatigue
                fatigue_flag = fatigue_flag or any(
                    "fatigue" in reason.lower() for reason in guardrail_result.reasons
                )

        # Determine risk_allowed based on guardrails and session
        risk_allowed = session_result.session_ok
        if guardrail_result:
            risk_allowed = risk_allowed and guardrail_result.allowed

        # Map buffer phase string to enum
        buffer_phase_str = market_state.get("buffer_phase", "0-5k")
        buffer_phase = self._parse_buffer_phase(buffer_phase_str)

        # Map tier string to enum
        tier_str = market_state.get("tier_active", "Conservative")
        tier_active = self._parse_enforcer_tier(tier_str)

        # Build and return context
        return ValidationContext(
            session_ok=session_result.session_ok,
            tier_active=tier_active,
            htf_bias=htf_bias_enum,
            dxy_trending_clean=dxy_trending_clean,
            fatigue_flag=fatigue_flag,
            risk_allowed=risk_allowed,
            news_ok=market_state.get("news_ok", True),
            ceo_directive_active=market_state.get("ceo_directive_active", False),
            buffer_phase=buffer_phase,
        )

    def _convert_htf_bias_to_enum(self, htf_bias: HTFBiasDataclass) -> HTFBias:
        """Convert HTF calculator's bias dataclass to validation enum.

        Args:
            htf_bias: HTFBias dataclass from rule_engine/htf/types.py

        Returns:
            HTFBias enum for validation schema
        """
        direction = htf_bias.direction.lower() if htf_bias.direction else "neutral"

        if direction == "long":
            return HTFBias.BULLISH
        elif direction == "short":
            return HTFBias.BEARISH
        else:
            return HTFBias.NEUTRAL

    def _compute_htf_bias(self, features: pd.Series) -> HTFBias:
        """Compute HTF bias from structure features, EMAs, and DXY.

        Uses 1H + 15M structure, EMA trend, and DXY alignment to determine
        higher timeframe directional bias.

        NOTE: This is a fallback method. Prefer passing htf_bias from the
        HTF calculator to build_context() for consistent bias values.

        Args:
            features: Feature series with structure and EMA data

        Returns:
            HTFBias enum (BULLISH, BEARISH, or NEUTRAL)
        """
        bullish_signals = 0
        bearish_signals = 0

        # Signal 1: Structure type
        structure_type = features.get("structure_type", "")
        if structure_type in ("HH", "HL"):
            bullish_signals += 1
        elif structure_type in ("LH", "LL"):
            bearish_signals += 1

        # Signal 2: EMA alignment
        ema_9 = features.get("ema_9", 0)
        ema_20 = features.get("ema_20", 0)
        ema_50 = features.get("ema_50", 0)

        if ema_9 > ema_20 > ema_50:
            bullish_signals += 1
        elif ema_9 < ema_20 < ema_50:
            bearish_signals += 1

        # Signal 3: Price relative to VWAP
        close = features.get("close", 0)
        vwap = features.get("vwap", 0)
        if vwap != 0:
            if close > vwap:
                bullish_signals += 1
            elif close < vwap:
                bearish_signals += 1

        # Signal 4: DXY alignment (inverse correlation for Gold)
        dxy_corr = features.get("dxy_corr")
        if dxy_corr is not None and not pd.isna(dxy_corr) and dxy_corr < -0.6:
            # Strong inverse correlation suggests DXY and Gold moving opposite
            # This acts as a confirmation signal that adds weight to the leading direction
            if bullish_signals > bearish_signals:
                bullish_signals += 1
            elif bearish_signals > bullish_signals:
                bearish_signals += 1
            # If tied, DXY doesn't break the tie (requires other signals to lead)

        # Determine final bias
        if bullish_signals >= 2 and bullish_signals > bearish_signals:
            return HTFBias.BULLISH
        elif bearish_signals >= 2 and bearish_signals > bullish_signals:
            return HTFBias.BEARISH
        else:
            return HTFBias.NEUTRAL

    def _is_dxy_trending_clean(self, features: pd.Series) -> bool:
        """Determine if DXY trend is clean for continuation setups.

        Args:
            features: Feature series with DXY data

        Returns:
            True if DXY trend is clean, False if unclear or unavailable
        """
        # Check if DXY data is available FIRST
        if not self._check_dxy_availability(features):
            return False

        # Get DXY correlation - now safe since availability check passed
        dxy_corr = features.get("dxy_corr")

        # Double-check for None/NaN (defensive)
        if dxy_corr is None or pd.isna(dxy_corr):
            return False

        # Check DXY correlation strength
        if abs(dxy_corr) < 0.6:
            # Weak correlation = unclear trend
            return False

        # Check if DXY itself has clear structure
        # For now, strong correlation is sufficient
        # Future: Could add DXY-specific structure checks
        return True

    def _check_dxy_availability(self, features: pd.Series) -> bool:
        """Check if DXY data is available in features.

        Args:
            features: Feature series

        Returns:
            True if DXY data is present and valid
        """
        dxy_corr = features.get("dxy_corr", None)

        # Check if DXY correlation exists and is not NaN
        if dxy_corr is None:
            return False

        if pd.isna(dxy_corr):
            return False

        return True

    def _parse_buffer_phase(self, phase_str: str) -> BufferPhase:
        """Parse buffer phase string to enum.

        Args:
            phase_str: Buffer phase string (e.g., "0-5k", "5-15k")

        Returns:
            BufferPhase enum
        """
        phase_map = {
            "0-5k": BufferPhase.STARTUP,
            "5-15k": BufferPhase.GROWTH,
            "15-40k": BufferPhase.SCALING,
            "40k+": BufferPhase.INSTITUTIONAL,
        }

        return phase_map.get(phase_str, BufferPhase.STARTUP)

    def _parse_enforcer_tier(self, tier_str: str) -> EnforcerTier:
        """Parse enforcer tier string to enum.

        Args:
            tier_str: Tier string (e.g., "Conservative", "Early Mild")

        Returns:
            EnforcerTier enum
        """
        tier_map = {
            "Conservative": EnforcerTier.CONSERVATIVE,
            "EarlyMild": EnforcerTier.EARLY_MILD,
            "Early Mild": EnforcerTier.EARLY_MILD,
            "Mild": EnforcerTier.MILD,
            "Offensive": EnforcerTier.OFFENSIVE,
        }

        return tier_map.get(tier_str, EnforcerTier.CONSERVATIVE)


def check_dxy_handling_for_setup(
    setup_type: str, dxy_available: bool
) -> tuple[bool, str | None]:
    """Check if setup is allowed when DXY data is unavailable.

    Per SOP:
    - VWAP_RECLAIM: Reject if DXY unavailable
    - DXY_CONTINUATION: Reject if DXY unavailable
    - VWAP_FADE: Allow with warning if DXY unavailable

    Args:
        setup_type: Setup type name
        dxy_available: Whether DXY data is available

    Returns:
        Tuple of (allowed, warning_message)
    """
    if dxy_available:
        return True, None

    # DXY unavailable - check setup type
    if setup_type in ("VWAP_RECLAIM", "DXY_CONTINUATION"):
        return (
            False,
            f"{setup_type} requires DXY data - rejecting due to unavailability",
        )
    elif setup_type == "VWAP_FADE":
        return True, f"{setup_type} proceeding without DXY data (allowed with warning)"
    else:
        # Unknown setup type - default to reject
        return (
            False,
            f"Unknown setup type {setup_type} - rejecting due to DXY unavailability",
        )
