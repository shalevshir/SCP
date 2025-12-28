"""Unit tests for StateRepository."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from bot_core_svc.state_repository import DailyState, StateRepository


class TestDailyState:
    """Test DailyState dataclass."""
    
    def test_default_values(self) -> None:
        """DailyState has correct defaults."""
        state = DailyState(date=date(2025, 1, 15))
        
        assert state.date == date(2025, 1, 15)
        assert state.loss_streak == 0
        assert state.daily_loss == 0.0
        assert state.trades_count == 0
        assert state.wins == 0
        assert state.losses == 0
        assert state.pdll_hits == 0
    
    def test_custom_values(self) -> None:
        """DailyState accepts custom values."""
        state = DailyState(
            date=date(2025, 1, 15),
            loss_streak=2,
            daily_loss=-100.0,
            trades_count=3,
            wins=1,
            losses=2,
            pdll_hits=1,
        )
        
        assert state.loss_streak == 2
        assert state.daily_loss == -100.0
        assert state.trades_count == 3
        assert state.wins == 1
        assert state.losses == 2
        assert state.pdll_hits == 1


class TestStateRepository:
    """Test StateRepository class."""
    
    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        
        # Mock async context manager for acquire
        async_cm = AsyncMock()
        conn = AsyncMock()
        async_cm.__aenter__.return_value = conn
        async_cm.__aexit__.return_value = None
        pool.acquire.return_value = async_cm
        
        return pool
    
    def test_init_sets_timezone(self, mock_db_pool: MagicMock) -> None:
        """Repository initializes with correct timezone."""
        repo = StateRepository(mock_db_pool, trading_timezone="Europe/London")
        
        assert repo._tz == ZoneInfo("Europe/London")
    
    def test_get_trading_date_uses_timezone(self, mock_db_pool: MagicMock) -> None:
        """Trading date uses configured timezone."""
        repo = StateRepository(mock_db_pool, trading_timezone="America/New_York")
        
        # Just verify it returns a date object
        trading_date = repo._get_trading_date()
        assert isinstance(trading_date, date)
    
    @pytest.mark.asyncio
    async def test_load_today_returns_fresh_state_when_not_found(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Loading today returns fresh state when no record exists."""
        # Setup mock connection
        async_cm = AsyncMock()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)  # No record found
        async_cm.__aenter__.return_value = conn
        async_cm.__aexit__.return_value = None
        mock_db_pool.acquire.return_value = async_cm
        
        repo = StateRepository(mock_db_pool, trading_timezone="Europe/London")
        state = await repo.load_today()
        
        assert isinstance(state, DailyState)
        assert state.loss_streak == 0
        assert state.trades_count == 0
    
    @pytest.mark.asyncio
    async def test_load_returns_existing_state(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Loading existing state returns populated DailyState."""
        # Setup mock connection with existing record
        async_cm = AsyncMock()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={
            "date": date(2025, 1, 15),
            "loss_streak": 2,
            "daily_loss": -150.0,
            "trades_count": 3,
            "wins": 1,
            "losses": 2,
            "pdll_hits": 0,
        })
        async_cm.__aenter__.return_value = conn
        async_cm.__aexit__.return_value = None
        mock_db_pool.acquire.return_value = async_cm
        
        repo = StateRepository(mock_db_pool, trading_timezone="Europe/London")
        state = await repo.load(date(2025, 1, 15))
        
        assert state.loss_streak == 2
        assert state.daily_loss == -150.0
        assert state.trades_count == 3
        assert state.wins == 1
        assert state.losses == 2
    
    @pytest.mark.asyncio
    async def test_save_executes_upsert(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Save executes upsert query."""
        # Setup mock connection
        async_cm = AsyncMock()
        conn = AsyncMock()
        conn.execute = AsyncMock()
        async_cm.__aenter__.return_value = conn
        async_cm.__aexit__.return_value = None
        mock_db_pool.acquire.return_value = async_cm
        
        repo = StateRepository(mock_db_pool, trading_timezone="Europe/London")
        state = DailyState(
            date=date(2025, 1, 15),
            loss_streak=1,
            daily_loss=-50.0,
            trades_count=2,
            wins=1,
            losses=1,
            pdll_hits=0,
        )
        
        await repo.save(state)
        
        conn.execute.assert_called_once()
        call_args = conn.execute.call_args[0]
        assert "INSERT INTO daily_state" in call_args[0]
        assert "ON CONFLICT" in call_args[0]
    
    @pytest.mark.asyncio
    async def test_reset_today_returns_fresh_state(
        self, mock_db_pool: MagicMock
    ) -> None:
        """Reset today returns fresh state and saves it."""
        # Setup mock connection
        async_cm = AsyncMock()
        conn = AsyncMock()
        conn.execute = AsyncMock()
        async_cm.__aenter__.return_value = conn
        async_cm.__aexit__.return_value = None
        mock_db_pool.acquire.return_value = async_cm
        
        repo = StateRepository(mock_db_pool, trading_timezone="Europe/London")
        state = await repo.reset_today()
        
        assert isinstance(state, DailyState)
        assert state.loss_streak == 0
        assert state.trades_count == 0
        conn.execute.assert_called_once()  # Saved fresh state


class TestStateRepositoryTimezone:
    """Test timezone handling in StateRepository."""
    
    @pytest.fixture
    def mock_db_pool(self) -> MagicMock:
        """Create mock database pool."""
        pool = MagicMock()
        async_cm = AsyncMock()
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=None)
        async_cm.__aenter__.return_value = conn
        async_cm.__aexit__.return_value = None
        pool.acquire.return_value = async_cm
        return pool
    
    def test_different_timezones_supported(self, mock_db_pool: MagicMock) -> None:
        """Repository supports different trading timezones."""
        london = StateRepository(mock_db_pool, trading_timezone="Europe/London")
        ny = StateRepository(mock_db_pool, trading_timezone="America/New_York")
        tokyo = StateRepository(mock_db_pool, trading_timezone="Asia/Tokyo")
        
        assert london._tz == ZoneInfo("Europe/London")
        assert ny._tz == ZoneInfo("America/New_York")
        assert tokyo._tz == ZoneInfo("Asia/Tokyo")
    
    @patch("bot_core_svc.state_repository.datetime")
    def test_trading_date_conversion(
        self, mock_datetime: MagicMock, mock_db_pool: MagicMock
    ) -> None:
        """Trading date is correctly converted to trading timezone."""
        # Mock UTC time: 2025-01-16 01:00 UTC
        # In London (winter) this is 2025-01-16 01:00 (same day)
        # In New York this is 2025-01-15 20:00 (previous day)
        mock_utc_now = datetime(2025, 1, 16, 1, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_utc_now
        
        repo = StateRepository(mock_db_pool, trading_timezone="America/New_York")
        trading_date = repo._get_trading_date()
        
        # Should be Jan 15 in New York timezone
        assert trading_date == date(2025, 1, 15)
