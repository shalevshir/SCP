"""Unit tests for Feature Engine service metrics."""

from datetime import UTC, datetime

import pytest
from scp_shared.messaging.schemas import FeaturesMessage

from feature_engine_svc import metrics


def test_update_feature_metrics_all_fields():
    """Test updating feature metrics with all fields present."""
    features_msg = FeaturesMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        open=2649.0,
        high=2652.0,
        low=2648.0,
        volume=1000.0,
        vwap=2650.5,
        vwap_slope=0.05,
        vwap_deviation=0.02,
        rsi=55.2,
        ema_9=2649.8,
        ema_20=2648.5,
        ema_50=2647.0,
        dxy_corr=-0.75,
        dxy_5m_corr=-0.72,
        bos_recent=True,
        bos_age=3,
        choch_detected=False,
        structure_clarity=0.85,
        expansion_detected=True,
        second_confirmation_long=True,
        second_confirmation_short=False,
    )
    
    metrics.update_feature_metrics(features_msg, "test", "feature-engine")
    
    # Verify VWAP indicators
    assert metrics.feature_vwap.labels(mode="test", service="feature-engine")._value._value == 2650.5
    assert metrics.feature_vwap_slope.labels(mode="test", service="feature-engine", symbol="GC")._value._value == 0.05
    assert metrics.feature_vwap_deviation.labels(mode="test", service="feature-engine")._value._value == 0.02
    
    # Verify trend indicators
    assert metrics.feature_rsi.labels(mode="test", service="feature-engine")._value._value == 55.2
    assert metrics.feature_ema_9.labels(mode="test", service="feature-engine")._value._value == 2649.8
    assert metrics.feature_ema_20.labels(mode="test", service="feature-engine")._value._value == 2648.5
    assert metrics.feature_ema_50.labels(mode="test", service="feature-engine")._value._value == 2647.0
    
    # Verify DXY correlation
    assert metrics.feature_dxy_corr.labels(mode="test", service="feature-engine")._value._value == -0.75
    assert metrics.feature_dxy_5m_corr.labels(mode="test", service="feature-engine")._value._value == -0.72
    
    # Verify structure fields
    assert metrics.feature_bos_recent.labels(mode="test", service="feature-engine")._value._value == 1.0
    assert metrics.feature_bos_age.labels(mode="test", service="feature-engine")._value._value == 3.0
    assert metrics.feature_choch_detected.labels(mode="test", service="feature-engine")._value._value == 0.0
    assert metrics.feature_structure_clarity.labels(mode="test", service="feature-engine")._value._value == 0.85
    
    # Verify expansion and confirmation
    assert metrics.feature_expansion_detected.labels(mode="test", service="feature-engine")._value._value == 1.0
    assert metrics.feature_second_confirmation_long.labels(mode="test", service="feature-engine")._value._value == 1.0
    assert metrics.feature_second_confirmation_short.labels(mode="test", service="feature-engine")._value._value == 0.0


def test_update_feature_metrics_handles_none_values():
    """Test that function handles None values gracefully."""
    features_msg = FeaturesMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        # All other fields are None
        vwap=None,
        vwap_slope=None,
        vwap_deviation=None,
        rsi=None,
        ema_9=None,
        ema_20=None,
        ema_50=None,
        dxy_corr=None,
        dxy_5m_corr=None,
        bos_recent=None,
        bos_age=None,
        choch_detected=None,
        structure_clarity=None,
        expansion_detected=False,
        second_confirmation_long=False,
        second_confirmation_short=False,
    )
    
    # Should not raise any exceptions
    metrics.update_feature_metrics(features_msg, "test", "feature-engine")
    
    # Boolean fields should still be set (as 0.0)
    assert metrics.feature_bos_recent.labels(mode="test", service="feature-engine")._value._value == 0.0
    assert metrics.feature_choch_detected.labels(mode="test", service="feature-engine")._value._value == 0.0
    assert metrics.feature_expansion_detected.labels(mode="test", service="feature-engine")._value._value == 0.0
    assert metrics.feature_second_confirmation_long.labels(mode="test", service="feature-engine")._value._value == 0.0
    assert metrics.feature_second_confirmation_short.labels(mode="test", service="feature-engine")._value._value == 0.0


def test_update_feature_metrics_dxy_correlation_fallback():
    """Test that dxy_correlation field is used as fallback for dxy_corr."""
    # Test with only dxy_correlation (legacy field)
    features_msg = FeaturesMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        dxy_correlation=-0.80,  # Legacy field
        dxy_corr=None,  # New field is None
    )
    
    metrics.update_feature_metrics(features_msg, "test", "feature-engine")
    
    # Should use dxy_correlation as fallback
    assert metrics.feature_dxy_corr.labels(mode="test", service="feature-engine")._value._value == -0.80


def test_update_feature_metrics_dxy_corr_prefers_new_field():
    """Test that dxy_corr is preferred over dxy_correlation when both present."""
    features_msg = FeaturesMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        dxy_correlation=-0.80,  # Legacy field
        dxy_corr=-0.75,  # New field (should be preferred)
    )
    
    metrics.update_feature_metrics(features_msg, "test", "feature-engine")
    
    # Should prefer dxy_corr
    assert metrics.feature_dxy_corr.labels(mode="test", service="feature-engine")._value._value == -0.75


def test_update_feature_metrics_boolean_conversions():
    """Test that boolean fields are converted to 0.0/1.0 correctly."""
    test_cases = [
        (True, 1.0),
        (False, 0.0),
        (None, 0.0),
    ]
    
    for bool_value, expected_metric in test_cases:
        features_msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 17, 10, 0, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            bos_recent=bool_value,
            choch_detected=bool_value,
            expansion_detected=bool_value if bool_value is not None else False,
            second_confirmation_long=bool_value if bool_value is not None else False,
            second_confirmation_short=bool_value if bool_value is not None else False,
        )
        
        metrics.update_feature_metrics(features_msg, "test", "feature-engine")
        
        assert metrics.feature_bos_recent.labels(mode="test", service="feature-engine")._value._value == expected_metric
        assert metrics.feature_choch_detected.labels(mode="test", service="feature-engine")._value._value == expected_metric
        assert metrics.feature_expansion_detected.labels(mode="test", service="feature-engine")._value._value == expected_metric


def test_update_feature_metrics_partial_fields():
    """Test updating with only some fields populated."""
    features_msg = FeaturesMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        # Only populate VWAP and RSI
        vwap=2650.5,
        rsi=55.0,
        # Rest are None or default
        bos_recent=True,
        expansion_detected=False,
    )
    
    metrics.update_feature_metrics(features_msg, "test", "feature-engine")
    
    # Verify populated fields
    assert metrics.feature_vwap.labels(mode="test", service="feature-engine")._value._value == 2650.5
    assert metrics.feature_rsi.labels(mode="test", service="feature-engine")._value._value == 55.0
    assert metrics.feature_bos_recent.labels(mode="test", service="feature-engine")._value._value == 1.0
    assert metrics.feature_expansion_detected.labels(mode="test", service="feature-engine")._value._value == 0.0


def test_update_feature_metrics_dxy_structure_encoding():
    """Test that DXY structure labels are encoded correctly as numeric values."""
    test_cases = [
        ("HH", 4.0),  # Higher High
        ("HL", 3.0),  # Higher Low
        ("LH", 2.0),  # Lower High
        ("LL", 1.0),  # Lower Low
        (None, 0.0),  # N/A
    ]
    
    for structure_label, expected_value in test_cases:
        features_msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 17, 10, 0, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            dxy_structure=structure_label,
        )
        
        metrics.update_feature_metrics(features_msg, "test", "feature-engine")
        
        assert (
            metrics.feature_dxy_structure.labels(mode="test", service="feature-engine")._value._value
            == expected_value
        ), f"Expected {structure_label} to encode to {expected_value}"


def test_update_feature_metrics_dxy_structure_unknown():
    """Test that unknown DXY structure labels default to 0.0."""
    features_msg = FeaturesMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        dxy_structure="UNKNOWN",  # Not in encoding map
    )
    
    metrics.update_feature_metrics(features_msg, "test", "feature-engine")
    
    # Unknown structure should map to 0.0 (N/A)
    assert metrics.feature_dxy_structure.labels(mode="test", service="feature-engine")._value._value == 0.0


def test_update_feature_metrics_dxy_structure_in_full_message():
    """Test DXY structure metric is set correctly with all other fields present."""
    features_msg = FeaturesMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        vwap=2650.5,
        rsi=55.2,
        dxy_corr=-0.75,
        dxy_structure="HH",  # DXY structure
    )
    
    metrics.update_feature_metrics(features_msg, "test", "feature-engine")
    
    # Verify DXY structure is encoded correctly
    assert metrics.feature_dxy_structure.labels(mode="test", service="feature-engine")._value._value == 4.0
    
    # Verify other metrics are also set
    assert metrics.feature_vwap.labels(mode="test", service="feature-engine")._value._value == 2650.5
    assert metrics.feature_rsi.labels(mode="test", service="feature-engine")._value._value == 55.2
    assert metrics.feature_dxy_corr.labels(mode="test", service="feature-engine")._value._value == -0.75
