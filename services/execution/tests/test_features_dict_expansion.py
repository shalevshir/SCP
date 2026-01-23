"""Tests for TradeManager features_dict expansion."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock
import pytest

from scp_shared.database import DatabasePool
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage
from execution_svc.trade_manager import TradeManager
from execution_svc.broker import BaseBroker
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_repository import TradeRepository
from execution_svc.trade_publisher import TradePublisher
from scp_shared.execution.types import TradeRecord


@pytest.fixture
def mock_db_pool() -> DatabasePool:
    """Create mock database pool."""
    pool = MagicMock(spec=DatabasePool)
    pool.fetch = AsyncMock(return_value=[])
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def mock_broker() -> BaseBroker:
    """Create mock broker."""
    broker = MagicMock(spec=BaseBroker)
    broker.place_order = AsyncMock()
    broker.close_position = AsyncMock()
    broker.reconcile_positions = AsyncMock()
    return broker


@pytest.fixture
def mock_sm_manager() -> StateMachineManager:
    """Create mock state machine manager."""
    sm = MagicMock(spec=StateMachineManager)
    sm._bar_counter = 100
    sm.create_from_signal = AsyncMock()
    sm.check_confirmation = Mock(return_value=True)
    sm.execute = AsyncMock()
    return sm


@pytest.fixture
def mock_repo() -> TradeRepository:
    """Create mock trade repository."""
    repo = MagicMock(spec=TradeRepository)
    repo.insert_trade = AsyncMock(return_value="test-trade-id")
    repo.close_trade = AsyncMock()
    repo.update_reached_1r = AsyncMock()
    return repo


@pytest.fixture
def mock_publisher() -> TradePublisher:
    """Create mock trade publisher."""
    publisher = MagicMock(spec=TradePublisher)
    publisher.publish_opened = AsyncMock()
    publisher.publish_closed = AsyncMock()
    return publisher


@pytest.fixture
def trade_manager(
    mock_broker: BaseBroker,
    mock_sm_manager: StateMachineManager,
    mock_repo: TradeRepository,
    mock_publisher: TradePublisher,
    mock_db_pool: DatabasePool,
) -> TradeManager:
    """Create TradeManager instance with mocked dependencies."""
    return TradeManager(
        broker=mock_broker,
        state_machine_manager=mock_sm_manager,
        trade_repository=mock_repo,
        trade_publisher=mock_publisher,
        db_pool=mock_db_pool,
        max_active_trades=1,
        pdll_limit=600.0,
        max_trades_per_day=2,
    )


@pytest.fixture
def active_trade() -> TradeRecord:
    """Create an active trade for testing."""
    return TradeRecord(
        trade_id="test-trade-1",
        signal_id="signal-1",
        symbol="GC",
        direction="long",
        setup_type="VWAP_FADE",
        entry_price=2000.0,
        sl_price=1990.0,
        tp_price=2020.0,
        risk_amount=10.0,
        reward_amount=20.0,
        entry_timestamp=datetime(2024, 3, 15, 10, 0, tzinfo=timezone.utc),
        entry_bar_idx=100,
        reached_1r=False,
    )


@pytest.fixture
def candle_msg() -> CandleMessage:
    """Create a candle message."""
    return CandleMessage(
        timestamp=datetime(2024, 3, 15, 10, 1, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        open=2001.0,
        high=2005.0,
        low=1999.0,
        close=2003.0,
        volume=1000.0,
    )


@pytest.fixture
def features_msg() -> FeaturesMessage:
    """Create a features message with all fields."""
    return FeaturesMessage(
        timestamp=datetime(2024, 3, 15, 10, 1, tzinfo=timezone.utc),
        symbol="GC",
        timeframe="1m",
        open=2001.0,
        high=2005.0,
        low=1999.0,
        close=2003.0,
        volume=1000.0,
        vwap=2002.0,
        vwap_slope=0.05,  # NEW FIELD
        rsi=55.0,
        ema_9=2000.0,
        ema_20=1998.0,
        ema_50=1995.0,
        dxy_correlation=-0.4,  # NEW FIELD
        dxy_5m_corr=-0.35,  # NEW FIELD
        dxy_structure="HL",  # NEW FIELD
        structure_label="HH",
        htf_structure_label="HH",  # NEW FIELD
        vwap_deviation=0.5,
        expansion_detected=False,
        expansion_reasons=[],  # Empty list, not None
        second_confirmation_long=False,
        second_confirmation_short=False,
    )


class TestFeaturesDictExpansion:
    """Test suite for features_dict expansion in TradeManager."""

    @pytest.mark.asyncio
    async def test_features_dict_includes_vwap_slope(
        self,
        trade_manager: TradeManager,
        active_trade: TradeRecord,
        candle_msg: CandleMessage,
        features_msg: FeaturesMessage,
    ) -> None:
        """Test that features_dict includes vwap_slope for VWAP_FADE invalidation."""
        # Add active trade
        trade_manager._active_trades[active_trade.trade_id] = active_trade
        trade_manager._trade_entry_bars[active_trade.trade_id] = 90

        # Capture the features_dict passed to invalidation checker
        original_check_all = trade_manager._invalidation_checker.check_all
        captured_features = None

        def capture_features(trade, candle, bars_elapsed, features=None):
            nonlocal captured_features
            captured_features = features
            return False, None  # Don't actually exit

        trade_manager._invalidation_checker.check_all = capture_features

        # Process candle with features
        await trade_manager.on_candle(candle_msg, features_msg)

        # Verify vwap_slope was included
        assert captured_features is not None, "features_dict was not passed"
        assert (
            "vwap_slope" in captured_features
        ), "vwap_slope missing from features_dict"
        assert captured_features["vwap_slope"] == 0.05

    @pytest.mark.asyncio
    async def test_features_dict_includes_dxy_correlation(
        self,
        trade_manager: TradeManager,
        active_trade: TradeRecord,
        candle_msg: CandleMessage,
        features_msg: FeaturesMessage,
    ) -> None:
        """Test that features_dict includes dxy_corr for DXY flip detection."""
        # Add active trade
        trade_manager._active_trades[active_trade.trade_id] = active_trade
        trade_manager._trade_entry_bars[active_trade.trade_id] = 90

        # Capture the features_dict
        captured_features = None

        def capture_features(trade, candle, bars_elapsed, features=None):
            nonlocal captured_features
            captured_features = features
            return False, None

        trade_manager._invalidation_checker.check_all = capture_features

        # Process candle with features
        await trade_manager.on_candle(candle_msg, features_msg)

        # Verify dxy_corr was included
        assert captured_features is not None
        assert "dxy_corr" in captured_features, "dxy_corr missing from features_dict"
        assert captured_features["dxy_corr"] == -0.4

    @pytest.mark.asyncio
    async def test_features_dict_includes_dxy_micro_correlations(
        self,
        trade_manager: TradeManager,
        active_trade: TradeRecord,
        candle_msg: CandleMessage,
        features_msg: FeaturesMessage,
    ) -> None:
        """Test that features_dict includes dxy_corr_1m and dxy_corr_5m for DXY_CONTINUATION."""
        # Add active trade with DXY_CONTINUATION setup
        active_trade.setup_type = "DXY_CONTINUATION"
        trade_manager._active_trades[active_trade.trade_id] = active_trade
        trade_manager._trade_entry_bars[active_trade.trade_id] = 90

        # Capture the features_dict
        captured_features = None

        def capture_features(trade, candle, bars_elapsed, features=None):
            nonlocal captured_features
            captured_features = features
            return False, None

        trade_manager._invalidation_checker.check_all = capture_features

        # Process candle with features
        await trade_manager.on_candle(candle_msg, features_msg)

        # Verify DXY micro correlations were included
        assert captured_features is not None
        assert (
            "dxy_corr_1m" in captured_features
        ), "dxy_corr_1m missing from features_dict"
        assert (
            "dxy_corr_5m" in captured_features
        ), "dxy_corr_5m missing from features_dict"
        # Should use dxy_5m_corr as proxy for both
        assert captured_features["dxy_corr_1m"] == -0.35
        assert captured_features["dxy_corr_5m"] == -0.35

    @pytest.mark.asyncio
    async def test_features_dict_includes_dxy_structure(
        self,
        trade_manager: TradeManager,
        active_trade: TradeRecord,
        candle_msg: CandleMessage,
        features_msg: FeaturesMessage,
    ) -> None:
        """Test that features_dict includes dxy_structure for DXY_CONTINUATION."""
        # Add active trade
        trade_manager._active_trades[active_trade.trade_id] = active_trade
        trade_manager._trade_entry_bars[active_trade.trade_id] = 90

        # Capture the features_dict
        captured_features = None

        def capture_features(trade, candle, bars_elapsed, features=None):
            nonlocal captured_features
            captured_features = features
            return False, None

        trade_manager._invalidation_checker.check_all = capture_features

        # Process candle with features
        await trade_manager.on_candle(candle_msg, features_msg)

        # Verify dxy_structure was included
        assert captured_features is not None
        assert (
            "dxy_structure" in captured_features
        ), "dxy_structure missing from features_dict"
        assert captured_features["dxy_structure"] == "HL"

    @pytest.mark.asyncio
    async def test_features_dict_includes_htf_structure_label(
        self,
        trade_manager: TradeManager,
        active_trade: TradeRecord,
        candle_msg: CandleMessage,
        features_msg: FeaturesMessage,
    ) -> None:
        """Test that features_dict includes htf_structure_label for VWAP_RECLAIM micro confirmation."""
        # Add active trade with VWAP_RECLAIM setup
        active_trade.setup_type = "VWAP_RECLAIM"
        trade_manager._active_trades[active_trade.trade_id] = active_trade
        trade_manager._trade_entry_bars[active_trade.trade_id] = 90

        # Capture the features_dict
        captured_features = None

        def capture_features(trade, candle, bars_elapsed, features=None):
            nonlocal captured_features
            captured_features = features
            return False, None

        trade_manager._invalidation_checker.check_all = capture_features

        # Process candle with features
        await trade_manager.on_candle(candle_msg, features_msg)

        # Verify htf_structure_label was included
        assert captured_features is not None
        assert (
            "htf_structure_label" in captured_features
        ), "htf_structure_label missing from features_dict"
        assert captured_features["htf_structure_label"] == "HH"

    @pytest.mark.asyncio
    async def test_features_dict_includes_original_fields(
        self,
        trade_manager: TradeManager,
        active_trade: TradeRecord,
        candle_msg: CandleMessage,
        features_msg: FeaturesMessage,
    ) -> None:
        """Test that features_dict still includes original fields (vwap, rsi, structure_label)."""
        # Add active trade
        trade_manager._active_trades[active_trade.trade_id] = active_trade
        trade_manager._trade_entry_bars[active_trade.trade_id] = 90

        # Capture the features_dict
        captured_features = None

        def capture_features(trade, candle, bars_elapsed, features=None):
            nonlocal captured_features
            captured_features = features
            return False, None

        trade_manager._invalidation_checker.check_all = capture_features

        # Process candle with features
        await trade_manager.on_candle(candle_msg, features_msg)

        # Verify original fields are still included
        assert captured_features is not None
        assert "vwap" in captured_features
        assert captured_features["vwap"] == 2002.0
        assert "rsi" in captured_features
        assert captured_features["rsi"] == 55.0
        assert "structure_label" in captured_features
        assert captured_features["structure_label"] == "HH"
