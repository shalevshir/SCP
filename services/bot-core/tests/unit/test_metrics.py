"""Unit tests for Bot Core service metrics."""

import pytest

from bot_core_svc import metrics


def test_session_valid_gauge_set_valid():
    """Test setting session_valid gauge to valid (1.0)."""
    metrics.session_valid.labels(mode="test", service="bot-core").set(1.0)
    
    assert metrics.session_valid.labels(mode="test", service="bot-core")._value._value == 1.0


def test_session_valid_gauge_set_invalid():
    """Test setting session_valid gauge to invalid (0.0)."""
    metrics.session_valid.labels(mode="test", service="bot-core").set(0.0)
    
    assert metrics.session_valid.labels(mode="test", service="bot-core")._value._value == 0.0


def test_current_setup_type_vwap_reclaim():
    """Test setting current_setup_type to VWAP_RECLAIM."""
    setup_value = metrics.SETUP_TYPE_ENCODING["VWAP_RECLAIM"]
    metrics.current_setup_type.labels(mode="test", service="bot-core").set(setup_value)
    
    assert metrics.current_setup_type.labels(mode="test", service="bot-core")._value._value == 1.0


def test_current_setup_type_vwap_fade():
    """Test setting current_setup_type to VWAP_FADE."""
    setup_value = metrics.SETUP_TYPE_ENCODING["VWAP_FADE"]
    metrics.current_setup_type.labels(mode="test", service="bot-core").set(setup_value)
    
    assert metrics.current_setup_type.labels(mode="test", service="bot-core")._value._value == 2.0


def test_current_setup_type_dxy_continuation():
    """Test setting current_setup_type to DXY_CONTINUATION."""
    setup_value = metrics.SETUP_TYPE_ENCODING["DXY_CONTINUATION"]
    metrics.current_setup_type.labels(mode="test", service="bot-core").set(setup_value)
    
    assert metrics.current_setup_type.labels(mode="test", service="bot-core")._value._value == 3.0


def test_current_setup_type_none():
    """Test setting current_setup_type to NONE."""
    setup_value = metrics.SETUP_TYPE_ENCODING[None]
    metrics.current_setup_type.labels(mode="test", service="bot-core").set(setup_value)
    
    assert metrics.current_setup_type.labels(mode="test", service="bot-core")._value._value == 0.0


def test_setup_type_encoding_complete():
    """Test that SETUP_TYPE_ENCODING contains all expected setup types."""
    expected_setups = {
        "VWAP_RECLAIM": 1.0,
        "VWAP_FADE": 2.0,
        "DXY_CONTINUATION": 3.0,
        None: 0.0,
    }
    
    assert metrics.SETUP_TYPE_ENCODING == expected_setups


def test_record_signal_rejection_valid_reason():
    """Test recording signal rejection with valid reason."""
    # Valid reason from REJECTION_REASONS
    metrics.record_signal_rejection("htf_validity", "test", "bot-core")
    
    counter = metrics.signals_rejected_total.labels(
        mode="test", service="bot-core", reason="htf_validity"
    )
    # Counter should have incremented (exact value depends on test execution order)
    assert counter._value._value >= 1.0


def test_record_signal_rejection_invalid_reason_fallback():
    """Test that invalid rejection reasons fall back to 'invalid_context'."""
    # Invalid reason (not in REJECTION_REASONS)
    metrics.record_signal_rejection("some_invalid_reason", "test", "bot-core")
    
    # Should have been recorded as "invalid_context"
    counter = metrics.signals_rejected_total.labels(
        mode="test", service="bot-core", reason="invalid_context"
    )
    assert counter._value._value >= 1.0


def test_rejection_reasons_set_complete():
    """Test that REJECTION_REASONS contains all expected reasons."""
    expected_reasons = {
        "risk_limit",
        "session_filter",
        "confidence_filter",
        "htf_validity",
        "neutral_direction",
        "cooldown",
        "invalid_context",
        "warmup",
        "kill_switch",
        "active_trade",
    }
    
    assert metrics.REJECTION_REASONS == expected_reasons


def test_enforcer_tier_map_complete():
    """Test that ENFORCER_TIER_MAP contains all expected tiers."""
    expected_tiers = {
        "Conservative": 1.0,
        "Early Mild": 2.0,
        "Mild": 3.0,
        "Offensive": 4.0,
    }
    
    assert metrics.ENFORCER_TIER_MAP == expected_tiers


def test_signal_score_gauge():
    """Test setting signal_score gauge."""
    metrics.signal_score.labels(mode="test", service="bot-core").set(9.2)
    
    assert metrics.signal_score.labels(mode="test", service="bot-core")._value._value == 9.2


def test_last_signal_score_gauge():
    """Test setting last_signal_score gauge."""
    metrics.last_signal_score.labels(mode="test", service="bot-core").set(8.5)
    
    assert metrics.last_signal_score.labels(mode="test", service="bot-core")._value._value == 8.5


def test_enforcer_tier_gauge():
    """Test setting enforcer_tier gauge."""
    tier_value = metrics.ENFORCER_TIER_MAP["Mild"]
    metrics.enforcer_tier.labels(mode="test", service="bot-core").set(tier_value)
    
    assert metrics.enforcer_tier.labels(mode="test", service="bot-core")._value._value == 3.0
