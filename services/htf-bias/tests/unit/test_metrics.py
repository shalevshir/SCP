"""Unit tests for HTF Bias service metrics."""

import pytest
from scp_shared.messaging.schemas import HTFBiasMessage
from datetime import datetime

from htf_bias_svc import metrics


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metric state before each test."""
    metrics._last_bias = None
    yield


def test_update_bias_metrics_bullish():
    """Test updating bias metrics for bullish bias."""
    metrics.update_bias_metrics("bullish", "test", "htf-bias")

    # Verify the gauge was set to 1.0 for bullish
    gauge = metrics.htf_bias_current.labels(mode="test", service="htf-bias")
    assert gauge._value._value == 1.0


def test_update_bias_metrics_bearish():
    """Test updating bias metrics for bearish bias."""
    metrics.update_bias_metrics("bearish", "test", "htf-bias")

    # Verify the gauge was set to -1.0 for bearish
    gauge = metrics.htf_bias_current.labels(mode="test", service="htf-bias")
    assert gauge._value._value == -1.0


def test_update_bias_metrics_neutral():
    """Test updating bias metrics for neutral bias."""
    metrics.update_bias_metrics("neutral", "test", "htf-bias")

    # Verify the gauge was set to 0.0 for neutral
    gauge = metrics.htf_bias_current.labels(mode="test", service="htf-bias")
    assert gauge._value._value == 0.0


def test_update_bias_metrics_tracks_changes():
    """Test that bias changes are tracked."""
    # Set initial bias
    metrics.update_bias_metrics("bullish", "test", "htf-bias")

    # Change bias
    metrics.update_bias_metrics("bearish", "test", "htf-bias")

    # Verify change was tracked (counter should have incremented)
    counter = metrics.htf_bias_changes_total.labels(
        mode="test", service="htf-bias", from_bias="bullish", to_bias="bearish"
    )
    assert counter._value._value == 1.0


def test_update_htf_detail_metrics_all_fields():
    """Test updating detailed HTF metrics with all fields present."""
    bias_msg = HTFBiasMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        bias="bullish",
        score=9.5,
        confidence="A+",
        structure_15m="HH",
        structure_1h="HH",
        dxy_aligned=True,
        chop_detected=False,
        conflict_detected=False,
        vwap_trend_confirmed=True,
        bos_detected=True,
        liquidity_sweep_detected=False,
        seasonality_adjustment=0.8,
        seasonality_period="november_december",
        structure_clarity=0.85,
    )

    metrics.update_htf_detail_metrics(bias_msg, "test", "htf-bias")

    # Verify all gauges were set correctly
    assert (
        metrics.htf_bias_score.labels(mode="test", service="htf-bias")._value._value
        == 9.5
    )
    assert (
        metrics.htf_bias_confidence.labels(
            mode="test", service="htf-bias"
        )._value._value
        == 4.0
    )  # A+ = 4
    assert (
        metrics.htf_dxy_aligned.labels(mode="test", service="htf-bias")._value._value
        == 1.0
    )
    assert (
        metrics.htf_chop_detected.labels(mode="test", service="htf-bias")._value._value
        == 0.0
    )
    assert (
        metrics.htf_conflict_detected.labels(
            mode="test", service="htf-bias"
        )._value._value
        == 0.0
    )
    assert (
        metrics.htf_vwap_trend_confirmed.labels(
            mode="test", service="htf-bias"
        )._value._value
        == 1.0
    )
    assert (
        metrics.htf_bos_detected.labels(mode="test", service="htf-bias")._value._value
        == 1.0
    )
    assert (
        metrics.htf_liquidity_sweep_detected.labels(
            mode="test", service="htf-bias"
        )._value._value
        == 0.0
    )
    assert (
        metrics.htf_structure_15m.labels(mode="test", service="htf-bias")._value._value
        == 1.0
    )  # HH = 1
    assert (
        metrics.htf_structure_1h.labels(mode="test", service="htf-bias")._value._value
        == 1.0
    )  # HH = 1
    assert (
        metrics.htf_seasonality_adjustment.labels(
            mode="test", service="htf-bias"
        )._value._value
        == 0.8
    )


def test_update_htf_detail_metrics_confidence_encoding():
    """Test that confidence levels are encoded correctly."""
    test_cases = [
        ("A+", 4.0),
        ("A", 3.0),
        ("B", 2.0),
        ("C", 1.0),
    ]

    for confidence, expected_value in test_cases:
        bias_msg = HTFBiasMessage(
            timestamp=datetime(2025, 1, 17, 10, 0, 0),
            bias="bullish",
            score=8.0,
            confidence=confidence,
            structure_15m="HH",
            structure_1h=None,
            dxy_aligned=True,
            chop_detected=False,
        )

        metrics.update_htf_detail_metrics(bias_msg, "test", "htf-bias")

        assert (
            metrics.htf_bias_confidence.labels(
                mode="test", service="htf-bias"
            )._value._value
            == expected_value
        )


def test_update_htf_detail_metrics_structure_encoding():
    """Test that structure labels are encoded correctly."""
    test_cases = [
        ("HH", 1.0),
        ("HL", 2.0),
        ("LH", 3.0),
        ("LL", 4.0),
        ("NEUTRAL", 0.0),
        (None, 0.0),
    ]

    for structure, expected_value in test_cases:
        bias_msg = HTFBiasMessage(
            timestamp=datetime(2025, 1, 17, 10, 0, 0),
            bias="bullish",
            score=8.0,
            confidence="A",
            structure_15m=structure,
            structure_1h=None,
            dxy_aligned=True,
            chop_detected=False,
        )

        metrics.update_htf_detail_metrics(bias_msg, "test", "htf-bias")

        assert (
            metrics.htf_structure_15m.labels(
                mode="test", service="htf-bias"
            )._value._value
            == expected_value
        )


def test_update_htf_detail_metrics_handles_missing_optional_fields():
    """Test that function handles missing optional fields gracefully."""
    # Minimal bias message with only required fields
    bias_msg = HTFBiasMessage(
        timestamp=datetime(2025, 1, 17, 10, 0, 0),
        bias="neutral",
        score=5.0,
        confidence="B",
        structure_15m=None,
        structure_1h=None,
        dxy_aligned=False,
        chop_detected=True,
    )

    # Should not raise any exceptions
    metrics.update_htf_detail_metrics(bias_msg, "test", "htf-bias")

    # Verify optional fields default to 0
    assert (
        metrics.htf_conflict_detected.labels(
            mode="test", service="htf-bias"
        )._value._value
        == 0.0
    )
    assert (
        metrics.htf_vwap_trend_confirmed.labels(
            mode="test", service="htf-bias"
        )._value._value
        == 0.0
    )
    assert (
        metrics.htf_bos_detected.labels(mode="test", service="htf-bias")._value._value
        == 0.0
    )
    assert (
        metrics.htf_seasonality_adjustment.labels(
            mode="test", service="htf-bias"
        )._value._value
        == 0.0
    )
