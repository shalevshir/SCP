"""Tests for scoring parity between batch and streaming modes.

This module tests that the scoring logic produces consistent results
whether running in batch (backtester) or streaming (microservices) mode.
"""

import pandas as pd
import pytest
from datetime import datetime, timezone

from scp_shared.rule_engine.htf.types import HTFBias
from scp_shared.rule_engine.htf.dxy.alignment import compute_dxy_alignment
from scp_shared.rule_engine.htf.seasonality.scoring import apply_seasonality_adjustment
from scp_shared.rule_engine.scoring import calculate_structure_quality_penalty


class TestDXYAlignmentStreamingFallback:
    """Tests for DXY alignment computation with streaming mode fallbacks."""
    
    def test_batch_mode_requires_all_fields(self):
        """Batch mode requires all mandatory fields."""
        # Batch mode: all fields provided
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",  # Bearish structure (supports long)
            dxy_chop_5m=False,
            dxy_corr_1m=-0.4,
            dxy_corr_5m=-0.5,
            dxy_corr_15m=-0.4,
            dxy_corr_1h=-0.3,
        )
        
        assert is_aligned is True
        assert score == 0.5  # 0.25 for 15M + 0.25 for 1H
        assert "LL" in rationale
        assert "inverse" in rationale.lower()
    
    def test_streaming_mode_fallback_without_5m(self):
        """Streaming mode falls back when 5M data is missing."""
        # Streaming mode: no 5M structure or correlation
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure=None,  # No structure (streaming mode)
            dxy_chop_5m=False,
            dxy_corr_1m=-0.45,  # Strong 1M correlation
            dxy_corr_5m=None,  # No 5M correlation
            dxy_corr_15m=-0.4,
            dxy_corr_1h=-0.3,
        )
        
        assert is_aligned is True  # Passes with strong 1M correlation
        assert score == 0.5  # HTF correlation bonus
        assert "streaming mode" in rationale.lower()
    
    def test_streaming_mode_with_weak_1m_and_15m_confirmation(self):
        """Streaming mode uses 15M to confirm weak 1M correlation."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure=None,
            dxy_chop_5m=False,
            dxy_corr_1m=-0.35,  # Weak 1M (< -0.4)
            dxy_corr_5m=None,
            dxy_corr_15m=-0.4,  # Strong 15M confirms
            dxy_corr_1h=-0.3,
        )
        
        assert is_aligned is True  # Confirmed by 15M
        assert score == 0.5
        assert "confirmed" in rationale.lower()
    
    def test_streaming_mode_rejects_very_weak_correlation(self):
        """Streaming mode rejects very weak correlations."""
        is_aligned, score, rationale = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure=None,
            dxy_chop_5m=False,
            dxy_corr_1m=-0.2,  # Too weak
            dxy_corr_5m=None,
            dxy_corr_15m=-0.2,  # Also weak
            dxy_corr_1h=None,
        )
        
        assert is_aligned is False
        assert score == 0.0
        assert "weak" in rationale.lower()


class TestSeasonalityDXYBonus:
    """Tests for seasonality DXY correlation bonus."""
    
    def test_november_gets_dxy_bonus_and_trend_bonus(self):
        """November-December with strong DXY gets both bonuses."""
        base_score = 8.5
        dxy_corr = -0.65  # Exceeds -0.55 threshold
        
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=dxy_corr,
        )
        
        # Should get +0.5 (DXY bonus) + 0.3 (trend season bonus) = +0.8
        assert adjustment == 0.8
        assert adjusted_score == 9.3
    
    def test_november_without_dxy_gets_only_trend_bonus(self):
        """November-December without DXY only gets trend bonus."""
        base_score = 8.5
        dxy_corr = None  # No DXY data
        
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=dxy_corr,
        )
        
        # Should get only +0.3 (trend season bonus)
        assert adjustment == 0.3
        assert adjusted_score == 8.8
    
    def test_november_weak_dxy_gets_only_trend_bonus(self):
        """November-December with weak DXY only gets trend bonus."""
        base_score = 8.5
        dxy_corr = -0.4  # Doesn't exceed -0.55 threshold
        
        adjusted_score, adjustment = apply_seasonality_adjustment(
            base_score=base_score,
            period="november_december",
            dxy_corr=dxy_corr,
        )
        
        # Should get only +0.3 (trend season bonus)
        assert adjustment == 0.3
        assert adjusted_score == 8.8


class TestStructureQualityPenaltyWithFallback:
    """Tests for structure quality penalty with liquidity sweep fallback."""
    
    def test_no_penalty_when_1m_sweep_detected(self):
        """No penalty when 1M features show liquidity sweep."""
        features = pd.Series({
            "liquidity_sweep": True,  # 1M sweep detected
            "bos_recent": True,
            "bos_age": 5,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            structure_clarity=0.8,
            liquidity_sweep_detected=False,  # HTF doesn't have sweep yet
            bos_detected=True,
        )
        
        penalty = calculate_structure_quality_penalty(
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_RECLAIM",
        )
        
        # Should have no sweep penalty because 1M sweep detected
        assert penalty == 0.0
    
    def test_penalty_when_no_sweep_anywhere(self):
        """Penalty applied when no sweep in 1M or HTF."""
        features = pd.Series({
            "liquidity_sweep": False,  # No 1M sweep
            "bos_recent": True,
            "bos_age": 5,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            structure_clarity=0.8,
            liquidity_sweep_detected=False,  # No HTF sweep
            bos_detected=True,
        )
        
        penalty = calculate_structure_quality_penalty(
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_RECLAIM",
        )
        
        # Should have -1.5 sweep penalty
        assert penalty == -1.5
    
    def test_no_penalty_when_htf_sweep_detected(self):
        """No penalty when HTF has liquidity sweep."""
        features = pd.Series({
            "liquidity_sweep": False,  # No 1M sweep
            "bos_recent": True,
            "bos_age": 5,
        })
        
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
            structure_clarity=0.8,
            liquidity_sweep_detected=True,  # HTF sweep detected
            bos_detected=True,
        )
        
        penalty = calculate_structure_quality_penalty(
            features=features,
            htf_bias=htf_bias,
            setup_type="VWAP_RECLAIM",
        )
        
        # Should have no sweep penalty because HTF sweep detected
        assert penalty == 0.0


class TestStreamingVsBatchParity:
    """Integration tests comparing streaming vs batch scoring."""
    
    def test_november_long_signal_with_full_data(self):
        """Test that streaming and batch produce same score for November long."""
        # This simulates a scenario where:
        # - November-December period
        # - Long direction
        # - Strong DXY alignment
        # - Good structure quality
        
        # Batch mode would have all data
        batch_dxy_aligned, batch_dxy_score, _ = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure="LL",
            dxy_chop_5m=False,
            dxy_corr_1m=-0.5,
            dxy_corr_5m=-0.55,
            dxy_corr_15m=-0.6,
            dxy_corr_1h=-0.65,
        )
        
        # Streaming mode might not have 5M data
        streaming_dxy_aligned, streaming_dxy_score, _ = compute_dxy_alignment(
            trade_direction="long",
            dxy_structure=None,  # No 5M structure
            dxy_chop_5m=False,
            dxy_corr_1m=-0.5,
            dxy_corr_5m=None,  # No 5M correlation
            dxy_corr_15m=-0.6,
            dxy_corr_1h=-0.65,
        )
        
        # Both should be aligned
        assert batch_dxy_aligned is True
        assert streaming_dxy_aligned is True
        
        # Both should get HTF correlation bonus
        assert batch_dxy_score == 0.5
        assert streaming_dxy_score == 0.5
        
        # Seasonality should give same bonus
        batch_seasonality_score, batch_seasonality_adj = apply_seasonality_adjustment(
            base_score=8.5,
            period="november_december",
            dxy_corr=-0.65,
        )
        
        streaming_seasonality_score, streaming_seasonality_adj = apply_seasonality_adjustment(
            base_score=8.5,
            period="november_december",
            dxy_corr=-0.6,  # Using 1M correlation as fallback (needs to exceed -0.55)
        )
        
        # Both should get 0.8 adjustment (0.5 DXY + 0.3 trend)
        assert batch_seasonality_adj == 0.8
        # Streaming should also get 0.8 with strong enough fallback correlation
        assert streaming_seasonality_adj == 0.8
