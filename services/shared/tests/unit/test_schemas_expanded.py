"""Unit tests for expanded FeaturesMessage schema.

Tests for new fields required by invalidation and scoring:
- OHLC data (open, high, low, volume)
- vwap_slope
- dxy_corr, dxy_5m_corr, dxy_structure
- expansion_detected, expansion_reasons
- second_confirmation_long, second_confirmation_short
- htf_structure_label

Following strict TDD - these tests are written FIRST and should FAIL until
the schema is expanded.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from scp_shared.messaging.schemas import FeaturesMessage


def utc_datetime(*args, **kwargs):
    """Create UTC timezone-aware datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


class TestFeaturesMessageExpansion:
    """Tests for expanded FeaturesMessage fields."""

    def test_features_message_with_ohlc_fields(self):
        """FeaturesMessage should accept OHLC fields."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            open=2649.0,
            high=2652.0,
            low=2648.0,
            volume=1000.0,
        )
        
        assert msg.open == 2649.0
        assert msg.high == 2652.0
        assert msg.low == 2648.0
        assert msg.volume == 1000.0

    def test_features_message_with_vwap_slope(self):
        """FeaturesMessage should accept vwap_slope field."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap=2649.5,
            vwap_slope=0.5,
        )
        
        assert msg.vwap_slope == 0.5

    def test_features_message_with_dxy_fields(self):
        """FeaturesMessage should accept DXY correlation and structure fields."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            dxy_corr=-0.75,
            dxy_5m_corr=-0.70,
            dxy_structure="HH",
        )
        
        assert msg.dxy_corr == -0.75
        assert msg.dxy_5m_corr == -0.70
        assert msg.dxy_structure == "HH"

    def test_features_message_with_expansion_fields(self):
        """FeaturesMessage should accept expansion gate fields."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            expansion_detected=True,
            expansion_reasons=["vwap_range", "atr_expansion"],
        )
        
        assert msg.expansion_detected is True
        assert "vwap_range" in msg.expansion_reasons
        assert len(msg.expansion_reasons) == 2

    def test_features_message_with_confirmation_fields(self):
        """FeaturesMessage should accept confirmation tracking fields."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            second_confirmation_long=True,
            second_confirmation_short=False,
        )
        
        assert msg.second_confirmation_long is True
        assert msg.second_confirmation_short is False

    def test_features_message_with_htf_structure(self):
        """FeaturesMessage should accept HTF structure label."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            htf_structure_label="HH",
        )
        
        assert msg.htf_structure_label == "HH"

    def test_features_message_all_new_fields_together(self):
        """FeaturesMessage should accept all new fields together."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            # OHLC
            open=2649.0,
            high=2652.0,
            low=2648.0,
            volume=1000.0,
            # VWAP
            vwap=2649.5,
            vwap_slope=0.5,
            vwap_deviation=0.02,
            # DXY
            dxy_corr=-0.75,
            dxy_5m_corr=-0.70,
            dxy_structure="HH",
            # Structure
            structure_label="HH",
            htf_structure_label="HH",
            # Expansion
            expansion_detected=True,
            expansion_reasons=["vwap_range"],
            # Confirmation
            second_confirmation_long=True,
            second_confirmation_short=False,
        )
        
        # Verify all fields are present
        assert msg.open == 2649.0
        assert msg.vwap_slope == 0.5
        assert msg.dxy_corr == -0.75
        assert msg.expansion_detected is True
        assert msg.htf_structure_label == "HH"

    def test_features_message_defaults_for_optional_fields(self):
        """Optional new fields should have proper defaults."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
        )
        
        # All new fields should be None or have sensible defaults
        assert msg.open is None
        assert msg.high is None
        assert msg.low is None
        assert msg.volume is None
        assert msg.vwap_slope is None
        assert msg.dxy_corr is None
        assert msg.dxy_5m_corr is None
        assert msg.dxy_structure is None
        assert msg.expansion_detected is False
        assert msg.expansion_reasons == []
        assert msg.second_confirmation_long is False
        assert msg.second_confirmation_short is False
        assert msg.htf_structure_label is None

    def test_features_message_json_serialization(self):
        """FeaturesMessage should serialize to/from JSON correctly."""
        msg = FeaturesMessage(
            timestamp=utc_datetime(2024, 10, 15, 10, 0),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            vwap_slope=0.5,
            dxy_corr=-0.75,
            expansion_detected=True,
            expansion_reasons=["test"],
        )
        
        # Serialize to JSON
        json_str = msg.model_dump_json()
        
        # Deserialize back
        msg2 = FeaturesMessage.model_validate_json(json_str)
        
        assert msg2.vwap_slope == 0.5
        assert msg2.dxy_corr == -0.75
        assert msg2.expansion_detected is True
        assert msg2.expansion_reasons == ["test"]

