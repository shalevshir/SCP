"""Tests for second confirmation fields in build_diagnostics.

Verifies that build_diagnostics correctly maps direction-specific second confirmation
fields from features to the generic keys expected by entry_model.py.

The entry model expects:
- second_confirmation_satisfied: bool
- second_confirmation_type: str | None
- second_confirmation_reasons: list[str]
- bars_since_reclaim: int

But streaming.py computes direction-specific fields:
- second_confirmation_long / second_confirmation_short
- second_confirmation_long_type / second_confirmation_short_type
- second_confirmation_long_reasons / second_confirmation_short_reasons
- bars_since_vwap_reclaim
"""

import pandas as pd
import pytest

from rule_engine.htf.types import HTFBias
from rule_engine.scoring import build_diagnostics


class TestBuildDiagnosticsSecondConfirmation:
    """Tests for second confirmation fields in diagnostics."""

    def test_long_direction_maps_confirmation_fields(self):
        """Test that long direction maps second_confirmation_long to generic keys."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "structure_clarity": 0.6,
            # Direction-specific fields computed by streaming.py
            "second_confirmation_long": True,
            "second_confirmation_short": False,
            "second_confirmation_long_type": "vwap_hold",
            "second_confirmation_short_type": None,
            "second_confirmation_long_reasons": ["vwap_hold: price holding above VWAP"],
            "second_confirmation_short_reasons": [],
            "bars_since_vwap_reclaim": 3,
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )

        diagnostics = build_diagnostics(features, htf_bias, direction="long")

        # Entry model expects these generic keys
        assert "second_confirmation_satisfied" in diagnostics, \
            "build_diagnostics must include second_confirmation_satisfied"
        assert diagnostics["second_confirmation_satisfied"] is True
        
        assert "second_confirmation_type" in diagnostics
        assert diagnostics["second_confirmation_type"] == "vwap_hold"
        
        assert "second_confirmation_reasons" in diagnostics
        assert len(diagnostics["second_confirmation_reasons"]) == 1
        assert "vwap_hold" in diagnostics["second_confirmation_reasons"][0]
        
        assert "bars_since_reclaim" in diagnostics
        assert diagnostics["bars_since_reclaim"] == 3

    def test_short_direction_maps_confirmation_fields(self):
        """Test that short direction maps second_confirmation_short to generic keys."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2648.0,
            "vwap": 2649.0,
            # Direction-specific fields
            "second_confirmation_long": False,
            "second_confirmation_short": True,
            "second_confirmation_long_type": None,
            "second_confirmation_short_type": "micro_bos",
            "second_confirmation_long_reasons": [],
            "second_confirmation_short_reasons": ["micro_bos: break of structure confirmed"],
            "bars_since_vwap_reclaim": 5,
        })

        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=8.0,
            confidence="high",
        )

        diagnostics = build_diagnostics(features, htf_bias, direction="short")

        assert diagnostics["second_confirmation_satisfied"] is True
        assert diagnostics["second_confirmation_type"] == "micro_bos"
        assert len(diagnostics["second_confirmation_reasons"]) == 1
        assert diagnostics["bars_since_reclaim"] == 5

    def test_missing_confirmation_fields_default_to_false(self):
        """Test that missing confirmation fields default to safe values."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "structure_clarity": 0.6,
            # No second confirmation fields present
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )

        diagnostics = build_diagnostics(features, htf_bias, direction="long")

        # Should default to False when fields are missing
        assert diagnostics["second_confirmation_satisfied"] is False
        assert diagnostics["second_confirmation_type"] is None
        assert diagnostics["second_confirmation_reasons"] == []
        assert diagnostics["bars_since_reclaim"] == 0

    def test_unconfirmed_long_correctly_reported(self):
        """Test that unconfirmed long is correctly mapped."""
        features = pd.Series({
            "timestamp": pd.Timestamp("2025-01-01 10:00:00", tz="UTC"),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2650.0,
            "vwap": 2649.0,
            "second_confirmation_long": False,  # Not confirmed
            "second_confirmation_short": False,
            "second_confirmation_long_type": None,
            "second_confirmation_short_type": None,
            "second_confirmation_long_reasons": [],
            "second_confirmation_short_reasons": [],
            "bars_since_vwap_reclaim": 1,
        })

        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )

        diagnostics = build_diagnostics(features, htf_bias, direction="long")

        assert diagnostics["second_confirmation_satisfied"] is False
        assert diagnostics["bars_since_reclaim"] == 1







