"""Time-based session validator enforcing SOP trading windows and seasonality."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from common.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SeasonRule:
    """Configuration for a season-specific trading window and constraints."""

    name: str
    months: frozenset[int]
    window_start: time
    window_end: time
    allowed_tiers: frozenset[str]
    allowed_setups: frozenset[str]
    min_score: float
    max_losses: int
    dxy_correlation_max: float


@dataclass(frozen=True)
class SessionConstraints:
    """Resolved constraints for the active season."""

    name: str
    window_start: time
    window_end: time
    allowed_tiers: frozenset[str]
    allowed_setups: frozenset[str]
    min_score: float
    max_losses: int
    dxy_correlation_max: float

    def describe(self) -> str:
        """Return a human-readable description for logging/debugging."""

        setups = "/".join(sorted(self.allowed_setups))
        tiers = "/".join(sorted(self.allowed_tiers))
        return (
            f"season={self.name} window={self.window_start.strftime('%H:%M')}-"
            f"{self.window_end.strftime('%H:%M')} tiers={tiers} setups={setups} "
            f"min_score={self.min_score} max_losses={self.max_losses} "
            f"dxy_corr<{self.dxy_correlation_max}"
        )


@dataclass(frozen=True)
class SessionResult:
    """Result of evaluating a timestamp against the session rules."""

    session_ok: bool
    constraints: SessionConstraints
    reason: str | None = None


@dataclass(frozen=True)
class SessionConfig:
    """Overall configuration for the session validator."""

    timezone: str
    default_rule: SeasonRule
    seasons: tuple[SeasonRule, ...] = tuple()
    holidays: frozenset[date] = frozenset()


class SessionValidator:
    """Validate whether current time is inside the active trading window."""

    def __init__(self, config: SessionConfig) -> None:
        self._config = config
        self._tz = ZoneInfo(config.timezone)
        self._season_lookup = self._build_season_lookup(config.seasons)

    def evaluate(self, timestamp: datetime) -> SessionResult:
        """Return whether the timestamp is within the allowed session."""

        local_dt = timestamp.astimezone(self._tz)
        rule = self._select_rule(local_dt)
        constraints = self._constraints_from_rule(rule)

        if local_dt.date() in self._config.holidays:
            logger.warning(
                "Session status: blocked | season=%s | reason=holiday | %s",
                constraints.name,
                constraints.describe(),
            )
            return SessionResult(False, constraints, reason="holiday")

        if not self._is_within_window(local_dt, rule):
            logger.warning(
                "Session status: blocked | season=%s | reason=outside_window | %s",
                constraints.name,
                constraints.describe(),
            )
            return SessionResult(False, constraints, reason="outside_window")

        logger.info(
            "Session status: allowed | season=%s | %s",
            constraints.name,
            constraints.describe(),
        )
        return SessionResult(True, constraints)

    def _select_rule(self, local_dt: datetime) -> SeasonRule:
        month = local_dt.month
        for rule in self._season_lookup.get(month, ()):
            return rule
        # Fall back to default rule if it covers the month or for all other cases
        if month in self._config.default_rule.months or not self._config.seasons:
            return self._config.default_rule
        # If default rule does not explicitly list the month, treat it as default
        return self._config.default_rule

    def _is_within_window(self, local_dt: datetime, rule: SeasonRule) -> bool:
        current_time = local_dt.timetz().replace(tzinfo=None)
        start = rule.window_start
        end = rule.window_end

        if start <= end:
            return start <= current_time < end

        # Handle windows that wrap past midnight (rare but supported)
        return current_time >= start or current_time < end

    def _constraints_from_rule(self, rule: SeasonRule) -> SessionConstraints:
        return SessionConstraints(
            name=rule.name,
            window_start=rule.window_start,
            window_end=rule.window_end,
            allowed_tiers=rule.allowed_tiers,
            allowed_setups=rule.allowed_setups,
            min_score=rule.min_score,
            max_losses=rule.max_losses,
            dxy_correlation_max=rule.dxy_correlation_max,
        )

    @staticmethod
    def _build_season_lookup(
        seasons: Iterable[SeasonRule],
    ) -> dict[int, tuple[SeasonRule, ...]]:
        lookup: dict[int, list[SeasonRule]] = {}
        for rule in seasons:
            for month in rule.months:
                lookup.setdefault(month, []).append(rule)
        return {month: tuple(rules) for month, rules in lookup.items()}
