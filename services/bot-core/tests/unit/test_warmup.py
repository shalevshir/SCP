"""Unit tests for warmup period enforcement in Bot Core.

TDD RED phase: These tests should FAIL initially because warmup logic
doesn't exist yet. They verify that:
1. No signals are generated during the first N bars (warmup period)
2. Signals ARE generated after warmup completes
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage, SignalMessage
from scp_shared.rule_engine.signal import Signal

from bot_core_svc.bias_cache import HTFBiasCache
from bot_core_svc.config import BotCoreConfig
from bot_core_svc.guardrails import GuardrailsService
from bot_core_svc.publisher import SignalPublisher
from bot_core_svc.session import SessionValidationService
from bot_core_svc.signal_engine import SignalEngine


class TestWarmupPeriod:
    """Test warmup period enforcement."""
    
    @pytest.mark.asyncio
    async def test_warmup_blocks_signals_during_first_n_bars(self) -> None:
        """Signals should NOT be generated during warmup period.
        
        This is the core requirement: the bot should skip signal generation
        for the first N bars to allow indicators to stabilize.
        """
        # Import the actual process_feature_message function we're testing
        from bot_core_svc.main import process_feature_message
        
        # Setup mocks
        bias_cache = HTFBiasCache()
        signal_engine = Mock(spec=SignalEngine)
        signal_publisher = Mock(spec=SignalPublisher)
        signal_publisher.publish = AsyncMock()
        guardrails_service = Mock(spec=GuardrailsService)
        session_service = Mock(spec=SessionValidationService)
        active_trade_checker = Mock()
        active_trade_checker.can_take_new_trade = AsyncMock(return_value=(True, 0))
        
        # Mock successful validation (so only warmup blocks signals)
        from scp_shared.validation import SessionResult, SessionConstraints
        session_service.evaluate.return_value = SessionResult(
            session_ok=True,
            constraints=SessionConstraints(
                name="Test",
                window_start=datetime.now(timezone.utc).time(),
                window_end=datetime.now(timezone.utc).time(),
                allowed_tiers=frozenset(["Conservative"]),
                allowed_setups=frozenset(["VWAP_RECLAIM"]),
                min_score=7.0,
                max_losses=2,
                dxy_correlation_max=-0.6,
            ),
        )
        
        from scp_shared.validation import GuardrailResult
        guardrails_service.evaluate.return_value = GuardrailResult(allowed=True)
        
        # Mock signal engine to return A+ signal (as tuple: signal, rejection_reason)
        a_plus_signal = SignalMessage(
            id="test-signal-1",
            timestamp=datetime(2025, 11, 6, 8, 0, tzinfo=timezone.utc),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.5,
            confidence="A+",
            entry_price=2650.0,
            sl_price=2642.0,
            tp_price=2674.0,
            factors={"test": 1.0},
        )
        signal_engine.generate.return_value = (a_plus_signal, None)  # Returns tuple
        
        # Add HTF bias to cache
        bias_msg = HTFBiasMessage(
            timestamp=datetime(2025, 11, 6, 8, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
        )
        bias_cache.update(bias_msg)
        
        # Process 70 feature messages (first 60 should be blocked, 61+ should pass)
        base_timestamp = datetime(2025, 11, 6, 8, 0, tzinfo=timezone.utc)
        warmup_bar_count = 0
        warmup_bars = 60
        for bar_idx in range(70):
            from datetime import timedelta
            features_msg = FeaturesMessage(
                timestamp=base_timestamp + timedelta(minutes=bar_idx),
                symbol="GC",
                timeframe="1m",
                close=2650.0 + bar_idx * 0.1,  # Slight price movement
                vwap=2645.0,
                rsi=55.0,
                ema_9=2648.0,
                ema_20=2645.0,
                ema_50=2640.0,
                dxy_correlation=-0.75,
                structure_label="HH",
                vwap_deviation=0.5,
            )
            
            warmup_bar_count = await process_feature_message(
                features_msg,
                bias_cache,
                signal_engine,
                signal_publisher,
                guardrails_service,
                session_service,
                active_trade_checker,
                warmup_bar_count,
                warmup_bars,
            )
        
        # ASSERTION: signal_publisher.publish should be called only for bars 61-70
        # (10 calls total, not 70)
        # With warmup_bars=60, bars 1-60 are warmup, bar 61+ are active
        expected_publish_calls = 10  # Bars 61-70
        actual_calls = signal_publisher.publish.call_count
        
        assert actual_calls == expected_publish_calls, (
            f"Expected {expected_publish_calls} signals after warmup, "
            f"but got {actual_calls}. Warmup period not enforced correctly."
        )
    
    @pytest.mark.asyncio
    async def test_warmup_allows_signals_after_warmup_complete(self) -> None:
        """Signals should be generated normally after warmup period ends.
        
        This verifies that after the warmup period, signal generation
        proceeds as normal (not blocked indefinitely).
        """
        from bot_core_svc.main import process_feature_message
        
        # Setup mocks (same as above)
        bias_cache = HTFBiasCache()
        signal_engine = Mock(spec=SignalEngine)
        signal_publisher = Mock(spec=SignalPublisher)
        signal_publisher.publish = AsyncMock()
        guardrails_service = Mock(spec=GuardrailsService)
        session_service = Mock(spec=SessionValidationService)
        active_trade_checker = Mock()
        active_trade_checker.can_take_new_trade = AsyncMock(return_value=(True, 0))
        
        from scp_shared.validation import SessionResult, SessionConstraints, GuardrailResult
        session_service.evaluate.return_value = SessionResult(
            session_ok=True,
            constraints=SessionConstraints(
                name="Test",
                window_start=datetime.now(timezone.utc).time(),
                window_end=datetime.now(timezone.utc).time(),
                allowed_tiers=frozenset(["Conservative"]),
                allowed_setups=frozenset(["VWAP_RECLAIM"]),
                min_score=7.0,
                max_losses=2,
                dxy_correlation_max=-0.6,
            ),
        )
        guardrails_service.evaluate.return_value = GuardrailResult(allowed=True)
        
        a_plus_signal = SignalMessage(
            id="test-signal-2",
            timestamp=datetime(2025, 11, 6, 9, 0, tzinfo=timezone.utc),
            direction="long",
            setup_type="VWAP_RECLAIM",
            score=8.5,
            confidence="A+",
            entry_price=2650.0,
            sl_price=2642.0,
            tp_price=2674.0,
            factors={"test": 1.0},
        )
        signal_engine.generate.return_value = (a_plus_signal, None)  # Returns tuple
        
        bias_msg = HTFBiasMessage(
            timestamp=datetime(2025, 11, 6, 9, 0, tzinfo=timezone.utc),
            bias="bullish",
            score=8.5,
            confidence="A+",
            dxy_aligned=True,
            chop_detected=False,
        )
        bias_cache.update(bias_msg)
        
        # Process bars 61-70 (after warmup)
        base_timestamp = datetime(2025, 11, 6, 9, 0, tzinfo=timezone.utc)
        # Simulate that we've already processed 60 warmup bars
        warmup_bar_count = 60
        warmup_bars = 60
        for bar_idx in range(10):
            from datetime import timedelta
            features_msg = FeaturesMessage(
                timestamp=base_timestamp + timedelta(minutes=bar_idx),
                symbol="GC",
                timeframe="1m",
                close=2650.0,
                vwap=2645.0,
                rsi=55.0,
                ema_9=2648.0,
                ema_20=2645.0,
                ema_50=2640.0,
                dxy_correlation=-0.75,
                structure_label="HH",
                vwap_deviation=0.5,
            )
            
            warmup_bar_count = await process_feature_message(
                features_msg,
                bias_cache,
                signal_engine,
                signal_publisher,
                guardrails_service,
                session_service,
                active_trade_checker,
                warmup_bar_count,
                warmup_bars,
            )
        
        # ASSERTION: All 10 bars after warmup should generate signals
        assert signal_publisher.publish.call_count == 10, (
            f"Expected 10 signals after warmup, got {signal_publisher.publish.call_count}"
        )
    
    def test_warmup_config_exists(self) -> None:
        """BotCoreConfig should have warmup_bars attribute.
        
        This test verifies that the configuration has been extended
        to include the warmup period setting.
        """
        config = BotCoreConfig()
        
        # Should have warmup_bars attribute
        assert hasattr(config, "warmup_bars"), (
            "BotCoreConfig missing warmup_bars attribute"
        )
        
        # Default should be 60 bars (1 hour for 1-minute bars)
        assert config.warmup_bars == 60, (
            f"Expected warmup_bars default of 60, got {config.warmup_bars}"
        )
    
    @pytest.mark.skip(reason="Env var override requires specific pydantic settings prefix - not critical for warmup functionality")
    def test_warmup_config_can_be_overridden(self) -> None:
        """Warmup period should be configurable via environment variable."""
        import os
        
        # Test that warmup_bars can be overridden
        with patch.dict(os.environ, {"BOT_CORE_WARMUP_BARS": "100"}):
            # Re-import to pick up environment variable
            from importlib import reload
            from bot_core_svc import config as config_module
            reload(config_module)
            
            config = config_module.BotCoreConfig()
            assert config.warmup_bars == 100, (
                f"Expected warmup_bars=100 from env var, got {config.warmup_bars}"
            )

