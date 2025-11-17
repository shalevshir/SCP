"""Validation schema definitions for SCP trading bot.

This module defines the typed schema for validation context including:
- Buffer phases (Risk Ladder SOP)
- Enforcer tiers (CEO directives)
- Market bias directions
- Validation context container with SOP enforcement rules
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class BufferPhase(str, Enum):
    """Capital buffer phases per Risk Ladder SOP.

    Defines the account equity ranges that determine risk parameters,
    contract sizes, and daily loss limits.
    """

    STARTUP = "0-5k"
    GROWTH = "5-15k"
    SCALING = "15-40k"
    INSTITUTIONAL = "40k+"


class EnforcerTier(str, Enum):
    """Enforcer tier levels per CEO directives.

    Defines the operational mode that determines setup requirements,
    risk tolerance, and session behavior.
    """

    CONSERVATIVE = "Conservative"
    EARLY_MILD = "EarlyMild"
    MILD = "Mild"
    OFFENSIVE = "Offensive"


class HTFBias(str, Enum):
    """Higher timeframe directional bias.

    Represents the market's primary trend direction used for
    structure-first validation and setup confirmation.
    """

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ValidationContext(BaseModel):
    """Container for all validation inputs required for SOP enforcement.

    This schema captures the complete state needed to evaluate whether
    a trade signal satisfies SOP requirements, CEO directives, and
    risk management rules.

    Attributes:
        session_ok: Whether current time is within permitted trading hours
        tier_active: Active enforcement tier (Conservative/EarlyMild/Mild/Offensive)
        htf_bias: Higher timeframe directional bias (bullish/bearish/neutral)
        dxy_trending_clean: DXY structure clarity for continuation setups
        fatigue_flag: Operator fatigue indicator (True blocks trading)
        risk_allowed: Risk budget available for new positions
        news_ok: No high-impact news events blocking trading
        ceo_directive_active: Whether CEO directive is currently active
        buffer_phase: Current capital buffer phase (0-5k, 5-15k, 15-40k, 40k+)

    Raises:
        ValueError: If validation rules are violated (e.g., EarlyMild without directive)

    Example:
        >>> context = ValidationContext(
        ...     session_ok=True,
        ...     tier_active=EnforcerTier.EARLY_MILD,
        ...     htf_bias=HTFBias.BULLISH,
        ...     dxy_trending_clean=True,
        ...     fatigue_flag=False,
        ...     risk_allowed=True,
        ...     news_ok=True,
        ...     ceo_directive_active=True,
        ...     buffer_phase=BufferPhase.STARTUP
        ... )
    """

    model_config = ConfigDict(strict=True)

    session_ok: bool
    tier_active: EnforcerTier
    htf_bias: HTFBias
    dxy_trending_clean: bool
    fatigue_flag: bool
    risk_allowed: bool
    news_ok: bool
    ceo_directive_active: bool
    buffer_phase: BufferPhase

    @model_validator(mode="after")
    def validate_early_mild_requires_directive(self) -> "ValidationContext":
        """Enforce that EarlyMild tier requires active CEO directive.

        Per SOP, the EarlyMild tier can only be activated when a CEO directive
        is explicitly active. This prevents unauthorized use of early mild setups.

        Returns:
            The validated context

        Raises:
            ValueError: If tier is EarlyMild but ceo_directive_active is False
        """
        if (
            self.tier_active == EnforcerTier.EARLY_MILD
            and not self.ceo_directive_active
        ):
            raise ValueError(
                "EarlyMild tier requires active CEO directive. "
                "Set ceo_directive_active=True or use a different tier."
            )
        return self
