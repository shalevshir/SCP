"""Tests for signal state metrics updates on early rejections."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from scp_shared.messaging.schemas import FeaturesMessage

from bot_core_svc import metrics


def utc_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """Create a UTC timestamp for test messages."""
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def build_features(
    timestamp: datetime,
    dxy_correlation: float | None = -0.75,
    dxy_corr: float | None = None,
) -> FeaturesMessage:
    """Build a minimal FeaturesMessage for early rejection checks."""
    return FeaturesMessage(
        timestamp=timestamp,
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        dxy_correlation=dxy_correlation,
        dxy_corr=dxy_corr,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "kill_switch",
        "warmup",
        # session_filter removed - session blocking moved to execution service
        "risk_limit",
        "invalid_context",
        "active_trade",
    ],
)
async def test_early_rejections_update_signal_state_metrics(
    reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Early rejections should update signal state metrics."""
    from bot_core_svc import main as main_module
    from bot_core_svc.bias_cache import HTFBiasCache
    from bot_core_svc.guardrails import GuardrailsService
    from bot_core_svc.main import process_feature_message
    from bot_core_svc.publisher import SignalPublisher
    from bot_core_svc.session import SessionValidationService
    from bot_core_svc.signal_engine import SignalEngine

    mode = "test"
    service = f"bot-core-{reason}"
    monkeypatch.setattr(main_module.config, "service_mode", mode)
    monkeypatch.setattr(main_module.config, "service_name", service)
    monkeypatch.setattr(main_module, "_is_killed", False)

    bias_cache = HTFBiasCache()
    signal_engine = Mock(spec=SignalEngine)
    signal_publisher = Mock(spec=SignalPublisher)
    signal_publisher.publish = AsyncMock()
    signal_repository = AsyncMock()
    guardrails_service = Mock(spec=GuardrailsService)
    session_service = Mock(spec=SessionValidationService)
    active_trade_checker = Mock()
    active_trade_checker.can_take_new_trade = AsyncMock(return_value=(True, 0))

    session_service.evaluate.return_value = Mock(
        session_ok=True, constraints={}, reason="outside_window"
    )
    guardrails_service.evaluate.return_value = Mock(allowed=True, reasons=[])

    warmup_bar_count = 60
    warmup_bars = 60
    features = build_features(timestamp=utc_datetime(2025, 1, 2, 10, 0))

    if reason == "kill_switch":
        monkeypatch.setattr(main_module, "_is_killed", True)
        warmup_bar_count = 0
    elif reason == "warmup":
        warmup_bar_count = 0
    elif reason == "risk_limit":
        guardrails_service.evaluate.return_value = Mock(
            allowed=False, reasons=["pdll_limit"]
        )
    elif reason == "invalid_context":
        features = build_features(
            timestamp=features.timestamp, dxy_correlation=None, dxy_corr=None
        )
    elif reason == "active_trade":
        active_trade_checker.can_take_new_trade = AsyncMock(return_value=(False, 1))

    metrics.signal_aplus_verdict.labels(mode=mode, service=service).set(1.0)
    metrics.signal_last_rejection.labels(mode=mode, service=service).set(0.0)

    await process_feature_message(
        features,
        bias_cache,
        signal_engine,
        signal_publisher,
        signal_repository,
        guardrails_service,
        session_service,
        active_trade_checker,
        warmup_bar_count,
        warmup_bars,
    )

    verdict_value = metrics.signal_aplus_verdict.labels(
        mode=mode, service=service
    )._value._value
    rejection_value = metrics.signal_last_rejection.labels(
        mode=mode, service=service
    )._value._value

    assert verdict_value == 0.0
    assert rejection_value == metrics.REJECTION_ENCODING[reason]
