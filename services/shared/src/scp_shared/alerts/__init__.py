"""Alerting module for critical system events.

This module provides structured alerts for:
- PDLL (Per Day Loss Limit) hits
- Kill switch activation/deactivation
- Service startup and crash events

Alerts are logged in a structured JSON format with an "ALERT" prefix
for easy filtering and can be extended to support external notification
channels (email, Slack, etc.) in the future.
"""

from scp_shared.alerts.sender import AlertLevel, AlertType, send_alert

__all__ = ["AlertLevel", "AlertType", "send_alert"]
