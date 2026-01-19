"""Tests for DXY alignment computation using behavior-based SOP rules."""

from scp_shared.rule_engine.htf.dxy.alignment import compute_dxy_alignment


class TestComputeDXYAlignment:
    """Test behavior-based DXY alignment computation."""

    def test_full_alignment_long(self) -> None:
        """Test full alignment for long trade with all conditions met."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",  # Bearish DXY supports long
            dxy_chop_5m=False,  # No chop
            dxy_corr_1m=-0.4,  # Inverse micro correlation
            dxy_corr_5m=-0.5,  # Inverse micro correlation
            dxy_corr_15m=-0.4,  # HTF correlation
            dxy_corr_1h=-0.3,  # HTF correlation
        )

        assert is_aligned is True
        assert score == 0.5  # 0.25 from 15M + 0.25 from 1H
        assert "LL" in rationale
        assert "bearish, supports long" in rationale
        assert "no chop" in rationale
        assert "inverse" in rationale

    def test_full_alignment_short(self) -> None:
        """Test full alignment for short trade with all conditions met."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="short",
            dxy_structure="HH",  # Bullish DXY supports short
            dxy_chop_5m=False,
            dxy_corr_1m=-0.35,
            dxy_corr_5m=-0.45,  # Need > -0.4 for 5M correlation
            dxy_corr_15m=-0.35,
            dxy_corr_1h=-0.28,
        )

        assert is_aligned is True
        assert score == 0.5
        assert "HH" in rationale
        assert "bullish, supports short" in rationale

    def test_structure_mismatch(self) -> None:
        """Test alignment fails when DXY structure conflicts with direction."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="HH",  # Bullish DXY conflicts with long
            dxy_chop_5m=False,
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
        )

        assert is_aligned is False
        assert score == 0.0
        assert "conflicts with long" in rationale

    def test_chop_detected(self) -> None:
        """Test alignment fails when DXY is in chop."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",
            dxy_chop_5m=True,  # Chop detected
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
        )

        assert is_aligned is False
        assert score == 0.0
        assert "in chop" in rationale

    def test_weak_micro_correlation(self) -> None:
        """Test alignment fails when best available correlation is weak."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",
            dxy_chop_5m=False,
            dxy_corr_1m=-0.2,  # Too weak
            dxy_corr_5m=-0.2,  # Also too weak (5M takes priority)
        )

        assert is_aligned is False
        assert score == 0.0
        assert "weak/positive" in rationale

    def test_missing_micro_correlation(self) -> None:
        """Test alignment fails when all correlation data is missing."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",
            dxy_chop_5m=False,
            dxy_corr_1m=None,  # Missing
            dxy_corr_5m=None,  # Missing
            dxy_corr_15m=None,  # Missing
        )

        assert is_aligned is False
        assert score == 0.0
        assert "N/A" in rationale

    def test_no_structure_label(self) -> None:
        """Test alignment passes when structure unavailable but correlation strong (streaming mode)."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure=None,  # No swing detected (streaming mode)
            dxy_chop_5m=False,
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
        )

        # Streaming mode: structure optional, relies on correlation
        assert is_aligned is True
        assert "relying on correlation" in rationale

    def test_htf_correlation_bonus(self) -> None:
        """Test HTF correlation adds bonus when aligned."""
        # With HTF correlation
        is_aligned_with, score_with, _ = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",
            dxy_chop_5m=False,
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_corr_15m=-0.4,
            dxy_corr_1h=-0.3,
        )

        # Without HTF correlation
        is_aligned_without, score_without, _ = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",
            dxy_chop_5m=False,
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_corr_15m=None,
            dxy_corr_1h=None,
        )

        assert is_aligned_with is True
        assert is_aligned_without is True
        assert score_with > score_without
        assert score_with == 0.5
        assert score_without == 0.0

    def test_partial_htf_correlation(self) -> None:
        """Test partial HTF correlation bonus."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",
            dxy_chop_5m=False,
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_corr_15m=-0.4,  # Strong
            dxy_corr_1h=-0.1,  # Weak
        )

        assert is_aligned is True
        assert score == 0.25  # Only 15M contributes
        assert "15M=-0.40" in rationale

    def test_lh_structure_supports_long(self) -> None:
        """Test LH (Lower High) structure supports long trades."""
        is_aligned, _, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LH",  # Also bearish DXY
            dxy_chop_5m=False,
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
        )

        assert is_aligned is True
        assert "LH" in rationale
        assert "bearish, supports long" in rationale

    def test_hl_structure_supports_short(self) -> None:
        """Test HL (Higher Low) structure supports short trades."""
        is_aligned, _, rationale = compute_dxy_alignment(
            trade_direction="short",
            dxy_structure="HL",  # Also bullish DXY
            dxy_chop_5m=False,
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
        )

        assert is_aligned is True
        assert "HL" in rationale
        assert "bullish, supports short" in rationale





