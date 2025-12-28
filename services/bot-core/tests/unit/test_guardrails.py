"""Unit tests for GuardrailsService."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scp_shared.validation import (
    BehaviorState,
    GuardrailResult,
    SessionConstraints,
)

from bot_core_svc.guardrails import GuardrailsService
from bot_core_svc.state_repository import DailyState


def _make_session_constraints(max_losses: int = 2) -> SessionConstraints:
    """Create session constraints for testing."""
    from datetime import time
    return SessionConstraints(
        name="Test",
        window_start=time(10, 0),
        window_end=time(13, 0),
        allowed_tiers=frozenset({"Conservative"}),
        allowed_setups=frozenset({"continuation"}),
        min_score=8.0,
        max_losses=max_losses,
        dxy_correlation_max=-0.6,
    )


class TestGuardrailsService:
    """Test GuardrailsService class."""
    
    @pytest.fixture
    def mock_state_repo(self) -> MagicMock:
        """Create mock state repository."""
        repo = MagicMock()
        repo.load_today = AsyncMock(return_value=DailyState(
            date=date(2025, 1, 15),
            loss_streak=0,
            daily_loss=0.0,
            trades_count=0,
            wins=0,
            losses=0,
            pdll_hits=0,
        ))
        repo.save = AsyncMock()
        repo.reset_today = AsyncMock(return_value=DailyState(
            date=date(2025, 1, 15),
            loss_streak=0,
            daily_loss=0.0,
            trades_count=0,
            wins=0,
            losses=0,
            pdll_hits=0,
        ))
        return repo
    
    @pytest.mark.asyncio
    async def test_load_state_initializes_tracker(self, mock_state_repo: MagicMock) -> None:
        """Loading state initializes behavior tracker with persisted values."""
        mock_state_repo.load_today = AsyncMock(return_value=DailyState(
            date=date(2025, 1, 15),
            loss_streak=2,  # Pre-existing loss streak
            daily_loss=-100.0,
            trades_count=3,
            wins=1,
            losses=2,
            pdll_hits=0,
        ))
        
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        assert service.state.consecutive_losses == 2
        assert service.daily_state is not None
        assert service.daily_state.trades_count == 3
        mock_state_repo.load_today.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_evaluate_allows_when_no_guardrails_triggered(
        self, mock_state_repo: MagicMock
    ) -> None:
        """Evaluate allows trading when no guardrails are triggered."""
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        constraints = _make_session_constraints(max_losses=2)
        result = service.evaluate(constraints)
        
        assert isinstance(result, GuardrailResult)
        assert result.allowed is True
        assert result.reasons == []
    
    @pytest.mark.asyncio
    async def test_evaluate_blocks_at_loss_streak_threshold(
        self, mock_state_repo: MagicMock
    ) -> None:
        """Evaluate blocks trading when loss streak reaches threshold."""
        mock_state_repo.load_today = AsyncMock(return_value=DailyState(
            date=date(2025, 1, 15),
            loss_streak=2,  # At threshold
            daily_loss=-100.0,
            trades_count=2,
            wins=0,
            losses=2,
            pdll_hits=0,
        ))
        
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        constraints = _make_session_constraints(max_losses=2)
        result = service.evaluate(constraints)
        
        assert result.allowed is False
        assert any("loss streak" in reason.lower() for reason in result.reasons)
    
    @pytest.mark.asyncio
    async def test_record_trade_outcome_updates_state(
        self, mock_state_repo: MagicMock
    ) -> None:
        """Recording trade outcome updates both tracker and daily state."""
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        # Record a losing trade
        await service.record_trade_outcome(won=False, pnl=-50.0)
        
        assert service.state.consecutive_losses == 1
        assert service.daily_state is not None
        assert service.daily_state.losses == 1
        assert service.daily_state.trades_count == 1
        assert service.daily_state.daily_loss == -50.0
        mock_state_repo.save.assert_called()
    
    @pytest.mark.asyncio
    async def test_record_trade_outcome_win_resets_streak(
        self, mock_state_repo: MagicMock
    ) -> None:
        """Recording a winning trade resets loss streak."""
        mock_state_repo.load_today = AsyncMock(return_value=DailyState(
            date=date(2025, 1, 15),
            loss_streak=1,
            daily_loss=-50.0,
            trades_count=1,
            wins=0,
            losses=1,
            pdll_hits=0,
        ))
        
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        # Record a winning trade
        await service.record_trade_outcome(won=True, pnl=100.0)
        
        assert service.state.consecutive_losses == 0
        assert service.daily_state is not None
        assert service.daily_state.wins == 1
        assert service.daily_state.trades_count == 2
    
    @pytest.mark.asyncio
    async def test_record_trade_outcome_breakeven(
        self, mock_state_repo: MagicMock
    ) -> None:
        """Recording a breakeven trade doesn't change loss streak."""
        mock_state_repo.load_today = AsyncMock(return_value=DailyState(
            date=date(2025, 1, 15),
            loss_streak=1,
            daily_loss=-50.0,
            trades_count=1,
            wins=0,
            losses=1,
            pdll_hits=0,
        ))
        
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        # Record a breakeven trade
        await service.record_trade_outcome(won=None, pnl=0.0)
        
        # Streak should not change
        assert service.state.consecutive_losses == 1
        assert service.daily_state is not None
        assert service.daily_state.trades_count == 2
    
    @pytest.mark.asyncio
    async def test_set_fatigue_flag(self, mock_state_repo: MagicMock) -> None:
        """Setting fatigue flag updates tracker state."""
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        service.set_fatigue_flag(True)
        
        assert service.state.fatigue_flag is True
    
    @pytest.mark.asyncio
    async def test_fatigue_flag_blocks_trading(
        self, mock_state_repo: MagicMock
    ) -> None:
        """Fatigue flag blocks trading."""
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        service.set_fatigue_flag(True)
        
        constraints = _make_session_constraints(max_losses=2)
        result = service.evaluate(constraints)
        
        assert result.allowed is False
        assert any("fatigue" in reason.lower() for reason in result.reasons)
    
    @pytest.mark.asyncio
    async def test_mark_session_extension(self, mock_state_repo: MagicMock) -> None:
        """Marking session extension updates tracker state."""
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        service.mark_session_extension(True)
        
        assert service.state.session_extended is True
    
    @pytest.mark.asyncio
    async def test_session_extension_blocks_trading(
        self, mock_state_repo: MagicMock
    ) -> None:
        """Session extension blocks trading."""
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        service.mark_session_extension(True)
        
        constraints = _make_session_constraints(max_losses=2)
        result = service.evaluate(constraints)
        
        assert result.allowed is False
        assert any("session" in reason.lower() for reason in result.reasons)
    
    @pytest.mark.asyncio
    async def test_reset_for_session(self, mock_state_repo: MagicMock) -> None:
        """Resetting for session clears all state."""
        mock_state_repo.load_today = AsyncMock(return_value=DailyState(
            date=date(2025, 1, 15),
            loss_streak=2,
            daily_loss=-100.0,
            trades_count=3,
            wins=1,
            losses=2,
            pdll_hits=0,
        ))
        
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        service.set_fatigue_flag(True)
        service.mark_session_extension(True)
        
        await service.reset_for_session()
        
        assert service.state.consecutive_losses == 0
        assert service.state.fatigue_flag is False
        assert service.state.session_extended is False
        mock_state_repo.reset_today.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multiple_losses_increment_streak(
        self, mock_state_repo: MagicMock
    ) -> None:
        """Multiple consecutive losses increment loss streak."""
        service = GuardrailsService(mock_state_repo)
        await service.load_state()
        
        await service.record_trade_outcome(won=False, pnl=-50.0)
        assert service.state.consecutive_losses == 1
        
        await service.record_trade_outcome(won=False, pnl=-50.0)
        assert service.state.consecutive_losses == 2
        
        await service.record_trade_outcome(won=False, pnl=-50.0)
        assert service.state.consecutive_losses == 3
    
    @pytest.mark.asyncio
    async def test_daily_state_property(self, mock_state_repo: MagicMock) -> None:
        """daily_state property returns loaded state."""
        service = GuardrailsService(mock_state_repo)
        
        # Before loading
        assert service.daily_state is None
        
        await service.load_state()
        
        # After loading
        assert service.daily_state is not None
        assert isinstance(service.daily_state, DailyState)
