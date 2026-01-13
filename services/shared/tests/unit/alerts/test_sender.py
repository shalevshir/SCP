"""Unit tests for the alert sender module."""

import json
import logging
from datetime import datetime
from unittest.mock import patch

import pytest

from scp_shared.alerts import AlertLevel, AlertType, send_alert


class TestAlertLevel:
    """Tests for AlertLevel enum."""

    def test_alert_levels_exist(self) -> None:
        """All expected alert levels should exist."""
        assert AlertLevel.CRITICAL == "CRITICAL"
        assert AlertLevel.WARNING == "WARNING"
        assert AlertLevel.INFO == "INFO"

    def test_alert_level_is_string_enum(self) -> None:
        """AlertLevel should be usable as string."""
        assert str(AlertLevel.CRITICAL) == "AlertLevel.CRITICAL"
        assert AlertLevel.CRITICAL.value == "CRITICAL"


class TestAlertType:
    """Tests for AlertType enum."""

    def test_all_alert_types_exist(self) -> None:
        """All expected alert types should exist."""
        assert AlertType.PDLL_HIT == "PDLL_HIT"
        assert AlertType.KILL_SWITCH_ACTIVATED == "KILL_SWITCH_ACTIVATED"
        assert AlertType.KILL_SWITCH_RESUMED == "KILL_SWITCH_RESUMED"
        assert AlertType.SERVICE_STARTED == "SERVICE_STARTED"
        assert AlertType.SERVICE_CRASHED == "SERVICE_CRASHED"

    def test_alert_type_is_string_enum(self) -> None:
        """AlertType should be usable as string."""
        assert AlertType.PDLL_HIT.value == "PDLL_HIT"


class TestSendAlert:
    """Tests for send_alert function."""

    def test_send_alert_returns_payload(self) -> None:
        """send_alert should return the alert payload dict."""
        payload = send_alert(
            AlertLevel.CRITICAL,
            AlertType.PDLL_HIT,
            "Test message",
        )

        assert payload["alert_type"] == "PDLL_HIT"
        assert payload["level"] == "CRITICAL"
        assert payload["message"] == "Test message"
        assert "timestamp" in payload
        assert payload["context"] == {}

    def test_send_alert_with_context(self) -> None:
        """send_alert should include context in payload."""
        context = {
            "daily_pnl": -650.0,
            "pdll_limit": 600.0,
            "trades_count": 2,
        }

        payload = send_alert(
            AlertLevel.CRITICAL,
            AlertType.PDLL_HIT,
            "Daily loss limit reached",
            context=context,
        )

        assert payload["context"] == context
        assert payload["context"]["daily_pnl"] == -650.0
        assert payload["context"]["pdll_limit"] == 600.0

    def test_send_alert_logs_at_correct_level(self, caplog: pytest.LogCaptureFixture) -> None:
        """send_alert should log at the correct level."""
        with caplog.at_level(logging.INFO, logger="ALERT"):
            send_alert(
                AlertLevel.INFO,
                AlertType.SERVICE_STARTED,
                "Service started",
            )

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.INFO
        assert "[SERVICE_STARTED]" in caplog.records[0].message

    def test_send_alert_logs_critical(self, caplog: pytest.LogCaptureFixture) -> None:
        """send_alert should log CRITICAL level alerts correctly."""
        with caplog.at_level(logging.CRITICAL, logger="ALERT"):
            send_alert(
                AlertLevel.CRITICAL,
                AlertType.PDLL_HIT,
                "PDLL hit",
            )

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.CRITICAL

    def test_send_alert_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """send_alert should log WARNING level alerts correctly."""
        with caplog.at_level(logging.WARNING, logger="ALERT"):
            send_alert(
                AlertLevel.WARNING,
                AlertType.PDLL_HIT,
                "Approaching PDLL",
            )

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING

    def test_send_alert_includes_json_payload_in_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """send_alert log message should include JSON payload."""
        with caplog.at_level(logging.INFO, logger="ALERT"):
            send_alert(
                AlertLevel.INFO,
                AlertType.SERVICE_STARTED,
                "Test",
                context={"key": "value"},
            )

        log_message = caplog.records[0].message
        # The log should contain the JSON payload after the pipe
        assert "|" in log_message
        json_part = log_message.split("|")[1].strip()
        parsed = json.loads(json_part)
        assert parsed["context"]["key"] == "value"

    def test_send_alert_timestamp_is_iso_format(self) -> None:
        """send_alert timestamp should be in ISO format."""
        payload = send_alert(
            AlertLevel.INFO,
            AlertType.SERVICE_STARTED,
            "Test",
        )

        # Should be parseable as ISO format
        datetime.fromisoformat(payload["timestamp"])

    def test_send_alert_kill_switch_activated(self) -> None:
        """Test KILL_SWITCH_ACTIVATED alert type."""
        payload = send_alert(
            AlertLevel.CRITICAL,
            AlertType.KILL_SWITCH_ACTIVATED,
            "Kill switch activated: Manual intervention",
            context={
                "service": "execution",
                "killed_by": "admin",
                "reason": "Manual intervention",
            },
        )

        assert payload["alert_type"] == "KILL_SWITCH_ACTIVATED"
        assert payload["context"]["service"] == "execution"
        assert payload["context"]["killed_by"] == "admin"

    def test_send_alert_kill_switch_resumed(self) -> None:
        """Test KILL_SWITCH_RESUMED alert type."""
        payload = send_alert(
            AlertLevel.INFO,
            AlertType.KILL_SWITCH_RESUMED,
            "Kill switch deactivated",
            context={"service": "bot-core", "resumed_by": "admin"},
        )

        assert payload["alert_type"] == "KILL_SWITCH_RESUMED"
        assert payload["level"] == "INFO"

    def test_send_alert_service_crashed(self) -> None:
        """Test SERVICE_CRASHED alert type."""
        payload = send_alert(
            AlertLevel.CRITICAL,
            AlertType.SERVICE_CRASHED,
            "Service crashed: ConnectionError",
            context={
                "service": "execution",
                "error_type": "ConnectionError",
                "error_message": "Connection refused",
            },
        )

        assert payload["alert_type"] == "SERVICE_CRASHED"
        assert payload["level"] == "CRITICAL"
        assert payload["context"]["error_type"] == "ConnectionError"

    def test_send_alert_context_serializes_datetime(self) -> None:
        """send_alert should handle datetime in context."""
        now = datetime.now()
        payload = send_alert(
            AlertLevel.INFO,
            AlertType.SERVICE_STARTED,
            "Test",
            context={"timestamp": now},
        )

        # The context should have the datetime (as-is in dict)
        # The JSON serialization in the log uses default=str
        assert payload["context"]["timestamp"] == now

    def test_send_alert_context_none_becomes_empty_dict(self) -> None:
        """send_alert with context=None should use empty dict."""
        payload = send_alert(
            AlertLevel.INFO,
            AlertType.SERVICE_STARTED,
            "Test",
            context=None,
        )

        assert payload["context"] == {}
