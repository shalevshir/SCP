"""Unit tests for GuardrailsService."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from scp_shared.validation import SessionConstraints

from bot_core_svc.guardrails import GuardrailsService
from bot_core_svc.state_repository import DailyState, StateRepository


class TestGuardrailsService:
    """Test GuardrailsService with state persistence."""
    
    @pytest.fixture
    def mock_state_repo(self) -> StateRepository:
        """Create mock state repository."""
        repo = MagicMock(spec=StateRepository)
        repo.load_today = AsyncMock(return_value=DailyState(date=date.today()))
        repo.save = AsyncMock()
        repo.reset_today = AsyncMock(return_value=DailyState(date=date.today()))
        return repo
    
    @pytest.fixture
    def default_constraints(self) -> SessionConstraints:
        """Create default session constraints."""
        from datetime import time
        
        return SessionConstraints(
            name="Default",
            window_start=time(9, 0),
            window_end=time(17, 0),
            allowed_tiers=frozenset(["Conservative", "Moderate", "Aggressive"]),
            allowed_setups=frozenset(["VWAP_RECLAIM", "VWAP_FADE", "DXY_CONTINUATION"]),
            min_score=8.0,
            max_losses=3,
            dxy_correlation_max=0.8,
        )
    
    @pytest.fixture
    async def service(self, mock_state_repo: StateRepository) -> GuardrailsService:
        """Create GuardrailsService with mock repository."""
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        return service
    
    # Core functionality tests
    
    @pytest.mark.asyncio
    async def test_evaluate_allowed_when_no_violations(
        self,
        service: GuardrailsService,
        default_constraints: SessionConstraints,
    ) -> None:
        """Guardrails pass with clean state (no violations)."""
        result = service.evaluate(default_constraints)
        
        assert result.allowed is True
        assert len(result.reasons) == 0
    
    @pytest.mark.asyncio
    async def test_evaluate_blocked_by_loss_streak(
        self,
        service: GuardrailsService,
        default_constraints: SessionConstraints,
    ) -> None:
        """Block when consecutive losses exceed limit."""
        # Record 3 losses (hitting limit)
        await service.record_trade_outcome(won=False, pnl=-100.0)
        await service.record_trade_outcome(won=False, pnl=-100.0)
        await service.record_trade_outcome(won=False, pnl=-100.0)
        
        result = service.evaluate(default_constraints)
        
        assert result.allowed is False
        assert any("loss streak" in reason.lower() for reason in result.reasons)
        assert service.state.consecutive_losses == 3
    
    @pytest.mark.asyncio
    async def test_record_trade_outcome_updates_state(
        self,
        service: GuardrailsService,
    ) -> None:
        """Win/loss updates tracked correctly."""
        # Record win
        await service.record_trade_outcome(won=True, pnl=150.0)
        assert service.daily_state is not None
        assert service.daily_state.wins == 1
        assert service.daily_state.losses == 0
        assert service.daily_state.trades_count == 1
        assert service.state.consecutive_losses == 0
        
        # Record loss
        await service.record_trade_outcome(won=False, pnl=-100.0)
        assert service.daily_state.wins == 1
        assert service.daily_state.losses == 1
        assert service.daily_state.trades_count == 2
        assert service.state.consecutive_losses == 1
    
    @pytest.mark.asyncio
    async def test_record_trade_outcome_persists_to_db(
        self,
        mock_state_repo: StateRepository,
        service: GuardrailsService,
    ) -> None:
        """State saved to repository after each trade outcome."""
        await service.record_trade_outcome(won=True, pnl=150.0)
        
        # Verify save was called
        assert mock_state_repo.save.call_count == 1
        saved_state = mock_state_repo.save.call_args[0][0]
        assert saved_state.trades_count == 1
        assert saved_state.wins == 1
    
    @pytest.mark.asyncio
    async def test_set_fatigue_flag_updates_tracker(
        self,
        service: GuardrailsService,
        default_constraints: SessionConstraints,
    ) -> None:
        """Fatigue flag propagation to tracker."""
        service.set_fatigue_flag(True)
        
        assert service.state.fatigue_flag is True
        
        result = service.evaluate(default_constraints)
        assert result.allowed is False
        assert any("fatigue" in reason.lower() for reason in result.reasons)
    
    @pytest.mark.asyncio
    async def test_mark_session_extension(
        self,
        service: GuardrailsService,
        default_constraints: SessionConstraints,
    ) -> None:
        """Session extension tracking."""
        service.mark_session_extension(True)
        
        assert service.state.session_extended is True
        
        result = service.evaluate(default_constraints)
        assert result.allowed is False
        assert any("extended" in reason.lower() for reason in result.reasons)
    
    @pytest.mark.asyncio
    async def test_reset_for_session_clears_state(
        self,
        mock_state_repo: StateRepository,
        service: GuardrailsService,
    ) -> None:
        """Daily reset functionality."""
        # Set up some state
        await service.record_trade_outcome(won=False, pnl=-100.0)
        service.set_fatigue_flag(True)
        
        # Reset
        await service.reset_for_session()
        
        # Verify state cleared
        assert service.state.consecutive_losses == 0
        assert service.state.fatigue_flag is False
        assert service.state.session_extended is False
        assert service.state.last_reset is not None
        
        # Verify repository reset called
        assert mock_state_repo.reset_today.call_count == 1
    
    @pytest.mark.asyncio
    async def test_load_state_initializes_tracker(
        self,
        mock_state_repo: StateRepository,
    ) -> None:
        """Load from DB on startup."""
        # Set up repository to return state with existing loss streak
        existing_state = DailyState(
            date=date.today(),
            loss_streak=2,
            trades_count=5,
            wins=3,
            losses=2,
        )
        mock_state_repo.load_today = AsyncMock(return_value=existing_state)
        
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        # Verify tracker initialized with loaded state
        assert service.state.consecutive_losses == 2
        assert service.daily_state is not None
        assert service.daily_state.trades_count == 5
        assert service.daily_state.wins == 3
        assert service.daily_state.losses == 2
    
    # Edge case tests (adapted from test_behavior_guardrails.py patterns)
    
    @pytest.mark.asyncio
    async def test_breakeven_trade_does_not_increment_loss_streak(
        self,
        service: GuardrailsService,
    ) -> None:
        """None (breakeven) leaves streak unchanged."""
        # Record a loss first
        await service.record_trade_outcome(won=False, pnl=-100.0)
        assert service.state.consecutive_losses == 1
        
        # Record breakeven (won=None)
        await service.record_trade_outcome(won=None, pnl=0.0)
        
        # Streak should remain unchanged
        assert service.state.consecutive_losses == 1
        assert service.daily_state is not None
        assert service.daily_state.trades_count == 2
    
    @pytest.mark.asyncio
    async def test_loss_streak_uses_session_specific_limit(
        self,
        service: GuardrailsService,
    ) -> None:
        """max_losses from SessionConstraints."""
        # Record 2 losses
        await service.record_trade_outcome(won=False, pnl=-100.0)
        await service.record_trade_outcome(won=False, pnl=-100.0)
        
        # With limit of 3, should still be allowed
        from datetime import time
        
        constraints_3 = SessionConstraints(
            name="Limit3",
            window_start=time(9, 0),
            window_end=time(17, 0),
            allowed_tiers=frozenset(["Conservative"]),
            allowed_setups=frozenset(["VWAP_RECLAIM"]),
            min_score=8.0,
            max_losses=3,
            dxy_correlation_max=0.8,
        )
        result = service.evaluate(constraints_3)
        assert result.allowed is True
        
        # With limit of 2, should be blocked
        constraints_2 = SessionConstraints(
            name="Limit2",
            window_start=time(9, 0),
            window_end=time(17, 0),
            allowed_tiers=frozenset(["Conservative"]),
            allowed_setups=frozenset(["VWAP_RECLAIM"]),
            min_score=8.0,
            max_losses=2,
            dxy_correlation_max=0.8,
        )
        result = service.evaluate(constraints_2)
        assert result.allowed is False
        assert any("loss streak" in reason.lower() for reason in result.reasons)
    
    @pytest.mark.asyncio
    async def test_fatigue_flag_blocks_immediately(
        self,
        service: GuardrailsService,
        default_constraints: SessionConstraints,
    ) -> None:
        """Fatigue flag = immediate block."""
        service.set_fatigue_flag(True)
        
        # Should block even with no losses
        assert service.state.consecutive_losses == 0
        result = service.evaluate(default_constraints)
        
        assert result.allowed is False
        assert any("fatigue" in reason.lower() for reason in result.reasons)
    
    @pytest.mark.asyncio
    async def test_session_extension_blocks(
        self,
        service: GuardrailsService,
        default_constraints: SessionConstraints,
    ) -> None:
        """Extended session = no new trades."""
        service.mark_session_extension(True)
        
        # Should block even with no losses
        assert service.state.consecutive_losses == 0
        result = service.evaluate(default_constraints)
        
        assert result.allowed is False
        assert any("extended" in reason.lower() for reason in result.reasons)
