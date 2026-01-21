"""Unit tests for TP structural target validation (SOP Section 4.3)."""

import pytest
from scp_shared.messaging.schemas import FeaturesMessage
from bot_core_svc.signal_engine import validate_tp_target
from datetime import datetime, timezone


@pytest.fixture
def base_features():
    """Base features message for testing."""
    return FeaturesMessage(
        timestamp=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        vwap=2645.0,
    )


class TestSLValidation:
    """Test SL placement validation (SOP critical requirement)."""
    
    def test_long_rejects_sl_above_entry(self, base_features):
        """Long trade rejected when SL is above entry price (invalid stop)."""
        entry_price = 2650.0
        sl_price = 2655.0  # INVALID: SL above entry for long
        
        base_features.nearest_liquidity_long = 2680.0
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
        assert "Invalid SL" in rejection
        assert "below entry" in rejection
    
    def test_long_rejects_sl_equal_to_entry(self, base_features):
        """Long trade rejected when SL equals entry (zero risk)."""
        entry_price = 2650.0
        sl_price = 2650.0  # INVALID: Zero risk distance
        
        base_features.nearest_liquidity_long = 2680.0
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
        assert "Invalid SL" in rejection
        # Zero risk is caught by direction-specific check (sl_price >= entry_price)
        assert "below entry" in rejection
    
    def test_short_rejects_sl_below_entry(self, base_features):
        """Short trade rejected when SL is below entry price (invalid stop)."""
        entry_price = 2650.0
        sl_price = 2645.0  # INVALID: SL below entry for short
        
        base_features.nearest_liquidity_short = 2620.0
        
        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
        assert "Invalid SL" in rejection
        assert "above entry" in rejection
    
    def test_short_rejects_sl_equal_to_entry(self, base_features):
        """Short trade rejected when SL equals entry (zero risk)."""
        entry_price = 2650.0
        sl_price = 2650.0  # INVALID: Zero risk distance
        
        base_features.nearest_liquidity_short = 2620.0
        
        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
        assert "Invalid SL" in rejection
        # Zero risk is caught by direction-specific check (sl_price <= entry_price)
        assert "above entry" in rejection
    
    def test_long_accepts_valid_sl_below_entry(self, base_features):
        """Long trade accepted when SL is correctly below entry."""
        entry_price = 2650.0
        sl_price = 2640.0  # VALID: SL below entry for long
        
        base_features.nearest_liquidity_long = 2680.0
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert rejection is None
        assert tp_price == 2680.0
    
    def test_short_accepts_valid_sl_above_entry(self, base_features):
        """Short trade accepted when SL is correctly above entry."""
        entry_price = 2640.0
        sl_price = 2650.0  # VALID: SL above entry for short
        
        base_features.nearest_liquidity_short = 2610.0
        
        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert rejection is None
        assert tp_price == 2610.0


class TestTPStructuralValidation:
    """Test TP structural target validation (SOP Section 4.3)."""
    
    def test_long_accepts_target_at_exactly_3r(self, base_features):
        """Long trade accepted when target exists at exactly 3R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = entry + (3 * 10) = 2680.0
        
        base_features.nearest_liquidity_long = 2680.0
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert rejection is None
        assert tp_price == 2680.0
    
    def test_long_accepts_target_above_3r(self, base_features):
        """Long trade accepted when target exists above 3R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0
        
        base_features.nearest_liquidity_long = 2690.0  # Above 3R
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert rejection is None
        assert tp_price == 2690.0
    
    def test_long_rejects_target_below_3r(self, base_features):
        """Long trade rejected when nearest target is below 3R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0
        
        base_features.nearest_liquidity_long = 2670.0  # Below 3R
        base_features.prior_session_high = None
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
        assert "No structural target" in rejection
        assert "≥3.0R" in rejection
    
    def test_long_rejects_when_no_target_available(self, base_features):
        """Long trade rejected when no structural target exists."""
        entry_price = 2650.0
        sl_price = 2640.0
        
        base_features.nearest_liquidity_long = None
        base_features.prior_session_high = None
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
        assert "No structural target" in rejection
    
    def test_short_accepts_target_at_exactly_3r(self, base_features):
        """Short trade accepted when target exists at exactly 3R."""
        entry_price = 2640.0
        sl_price = 2650.0  # Risk = 10 points
        # 3R = entry - (3 * 10) = 2610.0
        
        base_features.nearest_liquidity_short = 2610.0
        
        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert rejection is None
        assert tp_price == 2610.0
    
    def test_short_accepts_target_below_3r(self, base_features):
        """Short trade accepted when target exists below 3R."""
        entry_price = 2640.0
        sl_price = 2650.0  # Risk = 10 points
        # 3R = 2610.0
        
        base_features.nearest_liquidity_short = 2600.0  # Below 3R (better)
        
        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert rejection is None
        assert tp_price == 2600.0
    
    def test_short_rejects_target_above_3r(self, base_features):
        """Short trade rejected when nearest target is above 3R."""
        entry_price = 2640.0
        sl_price = 2650.0  # Risk = 10 points
        # 3R = 2610.0
        
        base_features.nearest_liquidity_short = 2620.0  # Above 3R (not far enough)
        base_features.prior_session_low = None
        
        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
        assert "No structural target" in rejection
    
    def test_short_rejects_when_no_target_available(self, base_features):
        """Short trade rejected when no structural target exists."""
        entry_price = 2640.0
        sl_price = 2650.0
        
        base_features.nearest_liquidity_short = None
        base_features.prior_session_low = None
        
        tp_price, rejection = validate_tp_target(
            direction="short",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
    
    def test_priority_order_nearest_liquidity_first(self, base_features):
        """Nearest liquidity target has priority over prior session high."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0
        
        base_features.nearest_liquidity_long = 2685.0  # Valid at 3.5R
        base_features.prior_session_high = 2695.0  # Also valid at 4.5R
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert rejection is None
        assert tp_price == 2685.0, "Should use nearest_liquidity (first priority)"
    
    def test_fallback_to_prior_session_high_when_liquidity_invalid(self, base_features):
        """Falls back to prior session high when nearest liquidity below 3R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0
        
        base_features.nearest_liquidity_long = 2670.0  # Below 3R (invalid)
        base_features.prior_session_high = 2690.0  # Above 3R (valid)
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert rejection is None
        assert tp_price == 2690.0, "Should fallback to prior_session_high"
    
    def test_configurable_min_rr_2r(self, base_features):
        """Test with configurable minimum R:R (2R instead of 3R)."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 2R = entry + (2 * 10) = 2670.0
        
        base_features.nearest_liquidity_long = 2670.0
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=2.0,  # VWAP_FADE uses 2R
        )
        
        assert rejection is None
        assert tp_price == 2670.0
    
    def test_rejects_when_only_target_below_required_rr(self, base_features):
        """Rejects when only available target is below required R:R."""
        entry_price = 2650.0
        sl_price = 2640.0  # Risk = 10 points
        # 3R = 2680.0
        
        # Both targets below 3R
        base_features.nearest_liquidity_long = 2675.0
        base_features.prior_session_high = 2678.0
        
        tp_price, rejection = validate_tp_target(
            direction="long",
            entry_price=entry_price,
            sl_price=sl_price,
            features=base_features,
            min_rr=3.0,
        )
        
        assert tp_price is None
        assert rejection is not None
        assert "No structural target" in rejection
