"""Unit tests for FVG alignment scoring module."""

import pytest
import pandas as pd

from scp_shared.rule_engine.htf.vwap.fvg import score_fvg_alignment


def create_fvg_dataframe(
    bullish_count: int = 0,
    bearish_count: int = 0,
    bullish_filled: int = 0,
    bearish_filled: int = 0,
) -> pd.DataFrame:
    """Create a test FVG DataFrame.

    Args:
        bullish_count: Number of unfilled bullish FVGs
        bearish_count: Number of unfilled bearish FVGs
        bullish_filled: Number of filled bullish FVGs
        bearish_filled: Number of filled bearish FVGs
    """
    rows = []

    # Add unfilled bullish FVGs
    for i in range(bullish_count):
        rows.append({"fvg_type": "bullish", "filled": False, "bar_idx": i})

    # Add unfilled bearish FVGs
    for i in range(bearish_count):
        rows.append({"fvg_type": "bearish", "filled": False, "bar_idx": 100 + i})

    # Add filled bullish FVGs
    for i in range(bullish_filled):
        rows.append({"fvg_type": "bullish", "filled": True, "bar_idx": 200 + i})

    # Add filled bearish FVGs
    for i in range(bearish_filled):
        rows.append({"fvg_type": "bearish", "filled": True, "bar_idx": 300 + i})

    return pd.DataFrame(rows)


class TestScoreFVGAlignment:
    """Tests for score_fvg_alignment function."""

    def test_neutral_bias_returns_zero(self) -> None:
        """Neutral bias always returns 0."""
        fvg_df = create_fvg_dataframe(bullish_count=5, bearish_count=3)

        result = score_fvg_alignment(fvg_df, "neutral")

        assert result == 0.0

    def test_empty_dataframe_returns_zero(self) -> None:
        """Empty FVG DataFrame returns 0."""
        fvg_df = pd.DataFrame(columns=["fvg_type", "filled", "bar_idx"])

        result = score_fvg_alignment(fvg_df, "bullish")

        assert result == 0.0

    def test_all_filled_returns_zero(self) -> None:
        """All filled FVGs returns 0."""
        fvg_df = create_fvg_dataframe(
            bullish_filled=3,
            bearish_filled=2,
        )

        result = score_fvg_alignment(fvg_df, "bullish")

        assert result == 0.0

    def test_bullish_bias_with_aligned_fvgs(self) -> None:
        """Bullish bias with bullish FVGs adds positive score."""
        fvg_df = create_fvg_dataframe(bullish_count=3)

        result = score_fvg_alignment(fvg_df, "bullish")

        assert result == 1.5  # 3 * 0.5

    def test_bullish_bias_with_opposing_fvgs(self) -> None:
        """Bullish bias with bearish FVGs subtracts score."""
        fvg_df = create_fvg_dataframe(bearish_count=2)

        result = score_fvg_alignment(fvg_df, "bullish")

        assert result == -1.0  # 2 * -0.5

    def test_bullish_bias_with_mixed_fvgs(self) -> None:
        """Bullish bias with mixed FVGs nets the score."""
        fvg_df = create_fvg_dataframe(bullish_count=3, bearish_count=1)

        result = score_fvg_alignment(fvg_df, "bullish")

        assert result == 1.0  # (3 * 0.5) - (1 * 0.5)

    def test_bearish_bias_with_aligned_fvgs(self) -> None:
        """Bearish bias with bearish FVGs adds positive score."""
        fvg_df = create_fvg_dataframe(bearish_count=4)

        result = score_fvg_alignment(fvg_df, "bearish")

        assert result == 2.0  # 4 * 0.5

    def test_bearish_bias_with_opposing_fvgs(self) -> None:
        """Bearish bias with bullish FVGs subtracts score."""
        fvg_df = create_fvg_dataframe(bullish_count=3)

        result = score_fvg_alignment(fvg_df, "bearish")

        assert result == -1.5  # 3 * -0.5

    def test_bearish_bias_with_mixed_fvgs(self) -> None:
        """Bearish bias with mixed FVGs nets the score."""
        fvg_df = create_fvg_dataframe(bullish_count=2, bearish_count=4)

        result = score_fvg_alignment(fvg_df, "bearish")

        assert result == 1.0  # (4 * 0.5) - (2 * 0.5)

    def test_filled_fvgs_ignored(self) -> None:
        """Filled FVGs are ignored in scoring."""
        fvg_df = create_fvg_dataframe(
            bullish_count=2,
            bearish_count=1,
            bullish_filled=10,
            bearish_filled=10,
        )

        result = score_fvg_alignment(fvg_df, "bullish")

        # Only unfilled count: 2 bullish (aligned) - 1 bearish (opposing)
        assert result == 0.5  # (2 * 0.5) - (1 * 0.5)

    def test_invalid_bias_raises_error(self) -> None:
        """Invalid bias value raises ValueError."""
        fvg_df = create_fvg_dataframe(bullish_count=1)

        with pytest.raises(ValueError, match="Invalid bias"):
            score_fvg_alignment(fvg_df, "invalid")

    def test_equal_opposing_and_aligned_returns_zero(self) -> None:
        """Equal aligned and opposing FVGs net to zero."""
        fvg_df = create_fvg_dataframe(bullish_count=2, bearish_count=2)

        result = score_fvg_alignment(fvg_df, "bullish")

        assert result == 0.0
