"""Tests for seasonality scoring adjustments.

Tests the integration of seasonality into HTF bias scoring.

Task: Integrate seasonality into scoring
Epic: Full HTF Bias Engine Upgrade
"""

from __future__ import annotations

from datetime import UTC

import pytest
from rule_engine.htf.seasonality.scoring import apply_seasonality_adjustment


class TestApplySeasonalityAdjustment:
    """Tests for seasonality-based score adjustments."""

    def test_september_no_adjustment_for_high_scores(self) -> None:
        """September should not penalize scores >= 8.5."""
        base_score = 9.0
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="september",
            dxy_corr=-0.7,
        )

        assert adjusted_score >= base_score or abs(adjusted_score - base_score) < 0.01
        assert adjustment >= 0.0  # No penalty for meeting threshold

    def test_september_penalty_for_low_scores(self) -> None:
        """September should penalize scores below 8.5 threshold."""
        base_score = 8.0
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="september",
            dxy_corr=-0.6,
        )

        # Score should be reduced or flagged
        assert adjusted_score < 8.5  # Doesn't meet September minimum
        assert adjustment < 0.0  # Penalty applied

    def test_september_boundary_at_threshold(self) -> None:
        """Test September behavior at exactly 8.5 threshold."""
        base_score = 8.5
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="september",
            dxy_corr=-0.65,
        )

        # At threshold, should not be penalized
        assert adjusted_score >= 8.5 or abs(adjusted_score - 8.5) < 0.01

    def test_november_december_relaxed_dxy_threshold(self) -> None:
        """Nov-Dec should accept -0.55 DXY correlation as valid."""
        base_score = 8.0
        # -0.57 is below standard -0.6 but above Nov-Dec threshold of -0.55
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=-0.57,
        )

        # Should receive bonus for meeting relaxed threshold
        assert adjusted_score >= base_score

    def test_november_december_trend_season_bonus(self) -> None:
        """Nov-Dec should give bonus for strong trends."""
        base_score = 8.5
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=-0.6,
        )

        # Trend season should add bonus
        assert adjusted_score > base_score
        assert adjustment > 0.0

    def test_october_baseline_thresholds(self) -> None:
        """October should use standard baseline thresholds."""
        base_score = 8.0
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="october",
            dxy_corr=-0.6,
        )

        # Should behave neutrally at baseline
        assert 8.0 <= adjusted_score <= 8.5

    def test_other_months_baseline_thresholds(self) -> None:
        """Other months should use standard baseline thresholds."""
        base_score = 8.0
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="other",
            dxy_corr=-0.6,
        )

        # Should behave neutrally at baseline
        assert 8.0 <= adjusted_score <= 8.5

    def test_strong_dxy_correlation_adds_bonus(self) -> None:
        """Strong DXY inverse correlation should add bonus across all periods."""
        base_score = 7.5

        for period in ["september", "october", "november_december", "other"]:
            adjusted_score, adjustment = apply_seasonality_adjustment(
                base_score=base_score,
                period=period,
                dxy_corr=-0.75,  # Very strong inverse correlation
            )

            # Should get bonus for strong correlation
            if period != "september" or base_score >= 8.0:
                assert adjusted_score >= base_score, f"Failed for {period}"

    def test_weak_dxy_correlation_no_bonus(self) -> None:
        """Weak DXY correlation should not add bonus."""
        base_score = 8.0
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="october",
            dxy_corr=-0.3,  # Weak correlation
        )

        # Should not receive DXY bonus
        assert abs(adjusted_score - base_score) < 0.6  # Minimal change

    def test_none_dxy_correlation_handled_gracefully(self) -> None:
        """None DXY correlation should not crash, apply other adjustments."""
        base_score = 8.5
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=None,
        )

        # Should still return valid score
        assert 0.0 <= adjusted_score <= 10.0
        assert isinstance(adjustment, float)

    def test_score_capped_at_10(self) -> None:
        """Adjusted score should never exceed 10."""
        base_score = 9.8
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=-0.8,
        )

        assert adjusted_score <= 10.0

    def test_score_floored_at_0(self) -> None:
        """Adjusted score should never go below 0."""
        base_score = 0.5
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="september",
            dxy_corr=-0.3,
        )

        assert adjusted_score >= 0.0

    def test_zero_base_score(self) -> None:
        """Zero base score should be handled correctly."""
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=0.0,
            period="october",
            dxy_corr=-0.6,
        )

        assert adjusted_score >= 0.0
        assert isinstance(adjustment, float)

    def test_perfect_10_base_score(self) -> None:
        """Perfect 10 score should remain 10."""
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=10.0,
            period="october",
            dxy_corr=-0.7,
        )

        assert adjusted_score == 10.0

    def test_september_strictest_penalties(self) -> None:
        """September should have strictest requirements."""
        # Same score, same DXY, different periods
        base_score = 8.2
        dxy_corr = -0.62

        sep_score, sep_adj = apply_seasonality_adjustment(
            base_score, "september", dxy_corr
        )
        oct_score, oct_adj = apply_seasonality_adjustment(
            base_score, "october", dxy_corr
        )
        nov_score, nov_adj = apply_seasonality_adjustment(
            base_score, "november_december", dxy_corr
        )

        # September should be strictest (lowest adjusted score)
        assert sep_score <= oct_score
        assert sep_score <= nov_score

    def test_november_december_most_generous(self) -> None:
        """November-December should be most generous with adjustments."""
        base_score = 8.0
        dxy_corr = -0.57  # Above Nov-Dec threshold, below standard

        sep_score, _ = apply_seasonality_adjustment(base_score, "september", dxy_corr)
        oct_score, _ = apply_seasonality_adjustment(base_score, "october", dxy_corr)
        nov_score, _ = apply_seasonality_adjustment(
            base_score, "november_december", dxy_corr
        )

        # Nov-Dec should be most generous
        assert nov_score >= oct_score
        assert nov_score >= sep_score

    @pytest.mark.parametrize(
        "period", ["september", "october", "november_december", "other"]
    )
    def test_all_periods_return_valid_scores(self, period: str) -> None:
        """All periods should return valid scores in [0, 10] range."""
        base_score = 7.5
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period=period,
            dxy_corr=-0.65,
        )

        assert 0.0 <= adjusted_score <= 10.0
        assert isinstance(adjustment, float)

    @pytest.mark.parametrize("base_score", [0.0, 2.5, 5.0, 7.5, 8.0, 8.5, 9.0, 10.0])
    def test_various_base_scores(self, base_score: float) -> None:
        """Test adjustment logic across various base scores."""
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="october",
            dxy_corr=-0.6,
        )

        assert 0.0 <= adjusted_score <= 10.0
        assert adjusted_score - base_score == adjustment

    def test_adjustment_amount_matches_score_change(self) -> None:
        """Adjustment amount should equal score change."""
        base_score = 8.0
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=-0.7,
        )

        # Allow small floating point errors
        assert abs((adjusted_score - base_score) - adjustment) < 0.001

    def test_september_dxy_threshold_strict(self) -> None:
        """September should use -0.65 as DXY threshold (strictest)."""
        base_score = 8.5

        # -0.64 is above September threshold, should not get bonus
        weak_score, weak_adj = apply_seasonality_adjustment(
            base_score, "september", -0.64
        )

        # -0.66 is below September threshold, should get bonus
        strong_score, strong_adj = apply_seasonality_adjustment(
            base_score, "september", -0.66
        )

        assert strong_score >= weak_score

    def test_november_december_dxy_threshold_relaxed(self) -> None:
        """November-December should use -0.55 as DXY threshold (most relaxed)."""
        base_score = 8.0

        # -0.56 is below Nov-Dec threshold, should get bonus
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=-0.56,
        )

        # Should receive bonus for meeting relaxed threshold
        assert adjustment > 0.0
        assert adjusted_score > base_score


class TestSeasonalityIntegration:
    """Integration tests for seasonality in HTF bias calculation."""

    def test_htf_bias_includes_seasonality_fields(self) -> None:
        """HTFBias should include seasonality_period and seasonality_adjustment."""
        from datetime import datetime

        import pandas as pd
        from rule_engine.htf.calculator import compute_htf_bias

        # Create sample features
        features_1h = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2500,
                "ema_20": 2490,
                "ema_50": 2480,
                "dxy_corr": -0.7,
            }
        )
        features_15m = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2501,
                "ema_20": 2491,
                "ema_50": 2481,
                "dxy_corr": -0.65,
            }
        )

        # November timestamp (trend season)
        timestamp = pd.Timestamp(datetime(2024, 11, 15, 12, 0, tzinfo=UTC))

        htf_bias = compute_htf_bias(features_1h, features_15m, timestamp=timestamp)

        # Verify seasonality fields are populated
        assert htf_bias.seasonality_period == "november_december"
        assert isinstance(htf_bias.seasonality_adjustment, float)
        assert htf_bias.seasonality_adjustment > 0.0  # Trend season bonus

    def test_compute_htf_bias_with_timestamp_applies_seasonality(self) -> None:
        """compute_htf_bias() with timestamp should apply seasonality."""
        from datetime import datetime

        import pandas as pd
        from rule_engine.htf.calculator import compute_htf_bias

        # Use features that produce lower base score (no DXY bonus)
        features_1h = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2500,
                "ema_20": 2490,
                "ema_50": 2480,
                "dxy_corr": -0.61,  # Just above standard threshold, no bonus yet
            }
        )
        features_15m = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2501,
                "ema_20": 2491,
                "ema_50": 2481,
                "dxy_corr": -0.59,  # Below standard threshold
            }
        )

        # September timestamp (defensive mode)
        sep_timestamp = pd.Timestamp(datetime(2024, 9, 15, 12, 0, tzinfo=UTC))
        htf_bias_sep = compute_htf_bias(
            features_1h, features_15m, timestamp=sep_timestamp
        )

        # November timestamp (trend season)
        nov_timestamp = pd.Timestamp(datetime(2024, 11, 15, 12, 0, tzinfo=UTC))
        htf_bias_nov = compute_htf_bias(
            features_1h, features_15m, timestamp=nov_timestamp
        )

        # November should have higher score due to trend season bonus
        assert htf_bias_nov.score > htf_bias_sep.score
        assert htf_bias_nov.seasonality_period == "november_december"
        assert htf_bias_sep.seasonality_period == "september"
        assert (
            htf_bias_nov.seasonality_adjustment > 0.0
        )  # Trend bonus + DXY bonus for -0.61 > -0.55

    def test_compute_htf_bias_without_timestamp_skips_seasonality(self) -> None:
        """compute_htf_bias() without timestamp should skip seasonality (backward compat)."""
        import pandas as pd
        from rule_engine.htf.calculator import compute_htf_bias

        features_1h = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2500,
                "ema_20": 2490,
                "ema_50": 2480,
                "dxy_corr": -0.7,
            }
        )
        features_15m = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2501,
                "ema_20": 2491,
                "ema_50": 2481,
                "dxy_corr": -0.65,
            }
        )

        # No timestamp provided
        htf_bias = compute_htf_bias(features_1h, features_15m)

        # Seasonality fields should be None/0
        assert htf_bias.seasonality_period is None
        assert htf_bias.seasonality_adjustment == 0.0

    def test_september_penalty_applied_in_calculator(self) -> None:
        """September defensive mode should penalize low scores in calculator."""
        from datetime import datetime

        import pandas as pd
        from rule_engine.htf.calculator import compute_htf_bias

        # Create features that produce score around 8.0
        features_1h = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2500,
                "ema_20": 2490,
                "ema_50": 2480,
                "dxy_corr": -0.5,  # Weaker correlation, lower score
            }
        )
        features_15m = pd.Series(
            {
                "structure_label": "HL",
                "ema_9": 2501,
                "ema_20": 2491,
                "ema_50": 2481,
                "dxy_corr": -0.5,
            }
        )

        sep_timestamp = pd.Timestamp(datetime(2024, 9, 15, 12, 0, tzinfo=UTC))
        htf_bias = compute_htf_bias(features_1h, features_15m, timestamp=sep_timestamp)

        # Should have negative adjustment for September if score < 8.5
        if htf_bias.score < 8.5:
            assert htf_bias.seasonality_adjustment < 0.0
