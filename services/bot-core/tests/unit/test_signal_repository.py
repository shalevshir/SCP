"""Unit tests for SignalRepository."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from bot_core_svc.signal_repository import SignalRepository
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage
from scp_shared.rule_engine import Signal


@pytest.fixture
def sample_features() -> FeaturesMessage:
    """Sample features message for testing."""
    return FeaturesMessage(
        timestamp=datetime(2025, 11, 3, 10, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        close=2650.0,
        open=2649.0,
        high=2652.0,
        low=2648.0,
        volume=1000.0,
        vwap=2649.5,
        rsi=55.0,
        ema_9=2650.0,
        ema_20=2648.0,
        ema_50=2645.0,
        dxy_correlation=-0.75,
        dxy_corr=-0.75,
        structure_label="HH",
        bos_direction="long",
        bos_recent=True,
        bos_age=5,
        structure_clarity=0.8,
        liquidity_sweep=True,
    )


@pytest.fixture
def sample_htf_bias() -> HTFBiasMessage:
    """Sample HTF bias message for testing."""
    return HTFBiasMessage(
        timestamp=datetime(2025, 11, 3, 10, 0, tzinfo=UTC),
        bias="bullish",
        score=8.5,
        confidence="A+",
        structure_15m="HH",
        structure_1h="HH",
        dxy_aligned=True,
        chop_detected=False,
        seasonality_adjustment=0.8,
        seasonality_period="november_december",
        vwap_trend_confirmed=True,
        bos_detected=True,
        bars_since_bos=5,
        structure_clarity=0.8,
        liquidity_sweep_detected=True,
        conflict_detected=False,
        dxy_chop_detected=False,
    )


@pytest.fixture
def sample_signal() -> Signal:
    """Sample signal for testing."""
    return Signal(
        timestamp=datetime(2025, 11, 3, 10, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=9.0,
        confidence="A+",
        factors={
            "structure_alignment": 2.0,
            "vwap_relation": 2.0,
            "rsi_state": 1.0,
            "ema_stack": 1.5,
            "dxy_corr": 1.5,
        },
        rationale=(
            "VWAP_RECLAIM setup, HTF bullish "
            "(high confidence, score=8.5), above VWAP"
        ),
        validation_flags={
            "session_ok": True,
            "tier_ok": True,
            "dxy_alignment_ok": True,
            "htf_bias_ok": True,
            "htf_valid": True,
        },
        enforcer_tier="Early Mild",
        diagnostics={
            "structure_label": "HH",
            "structure_clarity": 0.8,
            "bos_detected": True,
            "bos_age": 5,
            "rsi": 55.0,
            "vwap": 2649.5,
            "close": 2650.0,
            "dxy_corr_1m": -0.75,
            "htf_direction": "long",
            "htf_bias": "bullish",
            "htf_score": 8.5,
            "rejection_analysis": {
                "passed": True,
            },
        },
    )


@pytest.mark.asyncio
class TestSignalRepository:
    """Test suite for SignalRepository."""
    
    async def test_save_approved_signal(
        self,
        db_pool,
        clean_database,
        sample_signal,
        sample_features,
        sample_htf_bias,
    ):
        """Test saving an approved signal to database."""
        repo = SignalRepository(db_pool)
        signal_message_id = str(uuid4())
        
        # Save signal
        signal_id = await repo.save_signal(
            signal=sample_signal,
            features=sample_features,
            htf_bias=sample_htf_bias,
            was_approved=True,
            rejection_stage=None,
            signal_message_id=signal_message_id,
        )
        
        # Verify signal was saved
        assert signal_id is not None
        
        # Query database to verify
        row = await db_pool.fetchrow(
            "SELECT * FROM signal_history WHERE id = $1",
            signal_id,
        )
        
        assert row is not None
        assert row["was_approved"] is True
        assert row["rejection_stage"] is None
        assert str(row["signal_message_id"]) == signal_message_id
        assert row["score"] == 9.0
        assert row["confidence"] == "A+"
        assert row["setup_type"] == "VWAP_RECLAIM"
        assert row["direction"] == "long"
        
        # Verify snapshots are valid JSON
        features_snapshot = json.loads(row["features_snapshot"])
        htf_bias_snapshot = json.loads(row["htf_bias_snapshot"])
        factor_scores = json.loads(row["factor_scores"])
        diagnostics = json.loads(row["diagnostics"])
        
        assert features_snapshot["close"] == 2650.0
        assert htf_bias_snapshot["bias"] == "bullish"
        assert factor_scores["structure_alignment"] == 2.0
        assert diagnostics["rejection_analysis"]["passed"] is True
    
    async def test_save_rejected_signal(
        self,
        db_pool,
        clean_database,
        sample_signal,
        sample_features,
        sample_htf_bias,
    ):
        """Test saving a rejected signal to database."""
        # Modify signal to be rejected
        rejected_signal = Signal(
            timestamp=sample_signal.timestamp,
            symbol=sample_signal.symbol,
            timeframe=sample_signal.timeframe,
            direction=sample_signal.direction,
            setup_type=sample_signal.setup_type,
            htf_bias=sample_signal.htf_bias,
            score=7.2,  # Below A+ threshold
            confidence="Watch",
            factors=sample_signal.factors,
            rationale=sample_signal.rationale,
            validation_flags=sample_signal.validation_flags,
            enforcer_tier=sample_signal.enforcer_tier,
            diagnostics={
                **sample_signal.diagnostics,
                "rejection_analysis": {
                    "passed": False,
                    "primary_rejection_reason": "late_reclaim_penalty",
                    "primary_penalty": -0.8,
                    "score_gap": 0.8,
                    "would_pass_if": ["late_reclaim_penalty_relaxed"],
                },
            },
        )
        
        repo = SignalRepository(db_pool)
        
        # Save rejected signal
        signal_id = await repo.save_signal(
            signal=rejected_signal,
            features=sample_features,
            htf_bias=sample_htf_bias,
            was_approved=False,
            rejection_stage="confidence_filter",
            signal_message_id=None,
        )
        
        # Verify signal was saved
        assert signal_id is not None
        
        # Query database to verify
        row = await db_pool.fetchrow(
            "SELECT * FROM signal_history WHERE id = $1",
            signal_id,
        )
        
        assert row is not None
        assert row["was_approved"] is False
        assert row["rejection_stage"] == "confidence_filter"
        assert row["signal_message_id"] is None
        assert row["score"] == 7.2
        assert row["confidence"] == "Watch"
        
        # Verify rejection analysis
        diagnostics = json.loads(row["diagnostics"])
        rejection_analysis = diagnostics["rejection_analysis"]
        assert rejection_analysis["passed"] is False
        assert rejection_analysis["primary_rejection_reason"] == "late_reclaim_penalty"
        assert rejection_analysis["score_gap"] == 0.8
    
    async def test_link_trade(
        self,
        db_pool,
        clean_database,
        sample_signal,
        sample_features,
        sample_htf_bias,
    ):
        """Test linking a signal to a trade."""
        repo = SignalRepository(db_pool)
        signal_message_id = str(uuid4())
        trade_id = str(uuid4())
        
        # Save approved signal
        signal_id = await repo.save_signal(
            signal=sample_signal,
            features=sample_features,
            htf_bias=sample_htf_bias,
            was_approved=True,
            signal_message_id=signal_message_id,
        )
        
        # Link to trade
        await repo.link_trade(signal_message_id, trade_id)
        
        # Verify link
        row = await db_pool.fetchrow(
            "SELECT trade_id FROM signal_history WHERE id = $1",
            signal_id,
        )
        
        assert str(row["trade_id"]) == trade_id
    
    async def test_get_signals_for_period(
        self,
        db_pool,
        clean_database,
        sample_signal,
        sample_features,
        sample_htf_bias,
    ):
        """Test querying signals for a time period."""
        repo = SignalRepository(db_pool)
        
        # Save multiple signals
        start = datetime(2025, 11, 3, 10, 0, tzinfo=UTC)
        
        for i in range(5):
            signal = Signal(
                timestamp=datetime(2025, 11, 3, 10, i, tzinfo=UTC),
                symbol=sample_signal.symbol,
                timeframe=sample_signal.timeframe,
                direction=sample_signal.direction,
                setup_type=sample_signal.setup_type,
                htf_bias=sample_signal.htf_bias,
                score=8.0 + i * 0.2,
                confidence="A+" if i >= 2 else "Watch",
                factors=sample_signal.factors,
                rationale=sample_signal.rationale,
                validation_flags=sample_signal.validation_flags,
                enforcer_tier=sample_signal.enforcer_tier,
                diagnostics=sample_signal.diagnostics,
            )
            
            await repo.save_signal(
                signal=signal,
                features=sample_features,
                htf_bias=sample_htf_bias,
                was_approved=(i >= 2),
                rejection_stage="confidence_filter" if i < 2 else None,
                signal_message_id=str(uuid4()) if i >= 2 else None,
            )
        
        # Query all signals
        end = datetime(2025, 11, 3, 11, 0, tzinfo=UTC)
        signals = await repo.get_signals_for_period(start, end)
        
        assert len(signals) == 5
        
        # Query only approved
        approved = await repo.get_signals_for_period(start, end, was_approved=True)
        assert len(approved) == 3
        
        # Query only rejected
        rejected = await repo.get_signals_for_period(start, end, was_approved=False)
        assert len(rejected) == 2
    
    async def test_get_rejection_summary(
        self,
        db_pool,
        clean_database,
        sample_signal,
        sample_features,
        sample_htf_bias,
    ):
        """Test rejection summary aggregation."""
        repo = SignalRepository(db_pool)
        start = datetime(2025, 11, 3, 10, 0, tzinfo=UTC)
        
        # Save signals with different rejection stages
        rejection_stages = [
            "confidence_filter",
            "confidence_filter",
            "htf_validity",
            "tp_validation",
            "neutral_direction",
        ]
        
        for i, stage in enumerate(rejection_stages):
            signal = Signal(
                timestamp=datetime(2025, 11, 3, 10, i, tzinfo=UTC),
                symbol=sample_signal.symbol,
                timeframe=sample_signal.timeframe,
                direction=sample_signal.direction,
                setup_type=sample_signal.setup_type,
                htf_bias=sample_signal.htf_bias,
                score=7.0,
                confidence="Watch",
                factors=sample_signal.factors,
                rationale=sample_signal.rationale,
                validation_flags=sample_signal.validation_flags,
                enforcer_tier=sample_signal.enforcer_tier,
                diagnostics=sample_signal.diagnostics,
            )
            
            await repo.save_signal(
                signal=signal,
                features=sample_features,
                htf_bias=sample_htf_bias,
                was_approved=False,
                rejection_stage=stage,
            )
        
        # Get rejection summary
        end = datetime(2025, 11, 3, 11, 0, tzinfo=UTC)
        summary = await repo.get_rejection_summary(start, end)
        
        assert summary["confidence_filter"] == 2
        assert summary["htf_validity"] == 1
        assert summary["tp_validation"] == 1
        assert summary["neutral_direction"] == 1
    
    async def test_features_snapshot_preserves_none_values(
        self,
        db_pool,
        clean_database,
        sample_signal,
        sample_htf_bias,
    ):
        """Test that None values in features are preserved in snapshot."""
        # Create features with None values
        features = FeaturesMessage(
            timestamp=datetime(2025, 11, 3, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            close=2650.0,
            # Most other fields are None
            vwap=None,
            rsi=None,
            ema_9=None,
        )
        
        repo = SignalRepository(db_pool)
        
        signal_id = await repo.save_signal(
            signal=sample_signal,
            features=features,
            htf_bias=sample_htf_bias,
            was_approved=True,
            signal_message_id=str(uuid4()),
        )
        
        # Verify None values are preserved
        row = await db_pool.fetchrow(
            "SELECT features_snapshot FROM signal_history WHERE id = $1",
            signal_id,
        )
        
        features_snapshot = json.loads(row["features_snapshot"])
        assert features_snapshot["vwap"] is None
        assert features_snapshot["rsi"] is None
        assert features_snapshot["ema_9"] is None
        assert features_snapshot["close"] == 2650.0
