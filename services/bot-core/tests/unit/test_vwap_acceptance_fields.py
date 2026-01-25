"""Test that VWAP acceptance fields are properly converted from FeaturesMessage to Series.

This test verifies the fix for the issue where bars_near_vwap and bars_since_last_vwap_touch
were missing from the features Series, causing the min_vwap_acceptance and reclaim_timing_gate
constraints to always pass.
"""

from datetime import datetime, timezone

import pytest

from bot_core_svc.signal_engine import features_message_to_series
from scp_shared.messaging.schemas import FeaturesMessage


class TestVWAPAcceptanceFields:
    """Test VWAP acceptance fields in features_message_to_series."""

    def test_bars_near_vwap_included_in_series(self):
        """bars_near_vwap should be included in converted Series."""
        # GIVEN: FeaturesMessage with bars_near_vwap set
        features_msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            bars_near_vwap=5,  # 5 bars near VWAP
        )

        # WHEN: Converting to Series
        series = features_message_to_series(features_msg)

        # THEN: bars_near_vwap should be present and correct
        assert "bars_near_vwap" in series.index, "bars_near_vwap missing from Series"
        assert series["bars_near_vwap"] == 5

    def test_bars_since_last_vwap_touch_included_in_series(self):
        """bars_since_last_vwap_touch should be included in converted Series."""
        # GIVEN: FeaturesMessage with bars_since_last_vwap_touch set
        features_msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            bars_since_last_vwap_touch=8,  # 8 bars since last touch
        )

        # WHEN: Converting to Series
        series = features_message_to_series(features_msg)

        # THEN: bars_since_last_vwap_touch should be present and correct
        assert (
            "bars_since_last_vwap_touch" in series.index
        ), "bars_since_last_vwap_touch missing from Series"
        assert series["bars_since_last_vwap_touch"] == 8

    def test_vwap_acceptance_fields_none_handling(self):
        """VWAP acceptance fields should handle None values correctly."""
        # GIVEN: FeaturesMessage with None VWAP acceptance fields
        features_msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            bars_near_vwap=None,
            bars_since_last_vwap_touch=None,
        )

        # WHEN: Converting to Series
        series = features_message_to_series(features_msg)

        # THEN: Fields should be present with None values
        assert "bars_near_vwap" in series.index
        assert series["bars_near_vwap"] is None
        assert "bars_since_last_vwap_touch" in series.index
        assert series["bars_since_last_vwap_touch"] is None

    def test_drive_by_reclaim_detection(self):
        """min_vwap_acceptance constraint should reject drive-by reclaims (bars_near_vwap < 3)."""
        # GIVEN: FeaturesMessage with only 1 bar near VWAP (drive-by reclaim)
        features_msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            bars_near_vwap=1,  # Only 1 bar - should fail min_vwap_acceptance
        )

        # WHEN: Converting to Series
        series = features_message_to_series(features_msg)

        # THEN: bars_near_vwap should be available for constraint evaluation
        # The constraint expression: "bars_near_vwap is None or bars_near_vwap >= 3"
        # With bars_near_vwap=1, this should evaluate to False
        assert series["bars_near_vwap"] == 1
        # Constraint will reject: 1 < 3

    def test_delayed_reclaim_detection(self):
        """reclaim_timing_gate constraint should reject delayed reclaims (bars_since_last_vwap_touch > 10)."""
        # GIVEN: FeaturesMessage with 15 bars since last VWAP touch (too delayed)
        features_msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            bars_since_last_vwap_touch=15,  # 15 bars - should fail reclaim_timing_gate
        )

        # WHEN: Converting to Series
        series = features_message_to_series(features_msg)

        # THEN: bars_since_last_vwap_touch should be available for constraint evaluation
        # The constraint expression: "bars_since_last_vwap_touch is None or bars_since_last_vwap_touch <= 10"
        # With bars_since_last_vwap_touch=15, this should evaluate to False
        assert series["bars_since_last_vwap_touch"] == 15
        # Constraint will reject: 15 > 10

    def test_valid_vwap_reclaim_acceptance(self):
        """Valid VWAP reclaim should pass both constraints."""
        # GIVEN: FeaturesMessage with valid VWAP acceptance (3+ bars near VWAP, ≤10 bars since touch)
        features_msg = FeaturesMessage(
            timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            bars_near_vwap=4,  # ≥3 bars - passes min_vwap_acceptance
            bars_since_last_vwap_touch=6,  # ≤10 bars - passes reclaim_timing_gate
        )

        # WHEN: Converting to Series
        series = features_message_to_series(features_msg)

        # THEN: Both fields should be available and pass constraints
        assert series["bars_near_vwap"] == 4  # Passes: 4 >= 3
        assert series["bars_since_last_vwap_touch"] == 6  # Passes: 6 <= 10
