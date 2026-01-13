"""Alert sender for critical system events.

Provides structured logging for critical alerts that can be easily
filtered in log aggregation systems and extended for external notifications.
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any

# Use a dedicated logger for alerts with "ALERT" prefix
_alert_logger = logging.getLogger("ALERT")


class AlertLevel(str, Enum):
    """Alert severity levels."""

    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class AlertType(str, Enum):
    """Types of system alerts."""

    # Risk management
    PDLL_HIT = "PDLL_HIT"

    # Kill switch
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    KILL_SWITCH_RESUMED = "KILL_SWITCH_RESUMED"

    # Service lifecycle
    SERVICE_STARTED = "SERVICE_STARTED"
    SERVICE_CRASHED = "SERVICE_CRASHED"


def send_alert(
    level: AlertLevel,
    alert_type: AlertType,
    message: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a structured alert.

    Logs the alert in a structured JSON format with all context for easy
    parsing and filtering. Returns the alert payload for potential future
    use with external notification systems.

    Args:
        level: Alert severity level (CRITICAL, WARNING, INFO)
        alert_type: Type of alert (PDLL_HIT, KILL_SWITCH_ACTIVATED, etc.)
        message: Human-readable alert message
        context: Additional context dict (e.g., daily_pnl, loss_streak)

    Returns:
        Alert payload dict containing all alert information

    Example:
        >>> send_alert(
        ...     AlertLevel.CRITICAL,
        ...     AlertType.PDLL_HIT,
        ...     "Daily loss limit reached: -650.00 points",
        ...     context={
        ...         "daily_pnl": -650.0,
        ...         "pdll_limit": 600.0,
        ...         "trades_count": 2,
        ...     }
        ... )
    """
    # Build alert payload
    alert_payload = {
        "alert_type": alert_type.value,
        "level": level.value,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "context": context or {},
    }

    # Format as JSON for structured logging
    json_payload = json.dumps(alert_payload, default=str)

    # Log at appropriate level
    log_level = getattr(logging, level.value, logging.INFO)
    _alert_logger.log(
        log_level,
        f"[{alert_type.value}] {message} | {json_payload}",
    )

    return alert_payload
