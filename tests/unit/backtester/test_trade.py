"""Unit tests for Trade dataclass - complete trade lifecycle with SOP-compliant SL/TP.

Following TDD principles: tests written first to define behavior.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from backtester.entry_model import EntryExecution
from backtester.trade import (
    Trade,
    calculate_stop_loss,
    calculate_take_profit,
    close_trade,
    create_trade_from_entry,
    from_dict,
    to_dict,
)
from common.types import Candle
from rule_engine.signal import Signal


class TestTradeDataclass:
    """Tests for Trade dataclass structure and immutability."""

    @pytest.fixture
    def sample_entry_execution(self):
        """Create a sample EntryExecution for testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0, "vwap_relation": 2.0},
            rationale="HTF HH/HL intact, VWAP reclaim confirmed",
            validation_flags={"session_ok": True, "tier_ok": True},
            enforcer_tier="EarlyMild",
        )

        return EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

    @pytest.fixture
    def sample_trade(self, sample_entry_execution):
        """Create a sample Trade for testing."""
        return Trade(
            trade_id="test-trade-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Below confirmation candle low (structure-based)",
            tp_rationale="3R continuation setup (Jan-Aug baseline)",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

    def test_trade_has_required_attributes(self, sample_trade):
        """Test that Trade has all required attributes."""
        # Identity
        assert hasattr(sample_trade, "trade_id")
        assert hasattr(sample_trade, "symbol")
        assert hasattr(sample_trade, "timeframe")

        # Entry details
        assert hasattr(sample_trade, "entry_execution")
        assert hasattr(sample_trade, "entry_timestamp")
        assert hasattr(sample_trade, "entry_price")
        assert hasattr(sample_trade, "direction")
        assert hasattr(sample_trade, "setup_type")

        # SL/TP
        assert hasattr(sample_trade, "stop_loss")
        assert hasattr(sample_trade, "take_profit")
        assert hasattr(sample_trade, "sl_rationale")
        assert hasattr(sample_trade, "tp_rationale")

        # Risk/Reward
        assert hasattr(sample_trade, "risk_amount")
        assert hasattr(sample_trade, "reward_amount")
        assert hasattr(sample_trade, "r_multiple")
        assert hasattr(sample_trade, "contracts")

        # Exit details
        assert hasattr(sample_trade, "exit_timestamp")
        assert hasattr(sample_trade, "exit_price")
        assert hasattr(sample_trade, "exit_reason")

        # PnL
        assert hasattr(sample_trade, "pnl")
        assert hasattr(sample_trade, "pnl_percent")
        assert hasattr(sample_trade, "r_realized")

        # Metadata
        assert hasattr(sample_trade, "status")
        assert hasattr(sample_trade, "duration_bars")
        assert hasattr(sample_trade, "invalidation_triggered")

    def test_trade_is_immutable(self, sample_trade):
        """Test that Trade is immutable (frozen dataclass)."""
        with pytest.raises(AttributeError):
            sample_trade.entry_price = 2700.0

        with pytest.raises(AttributeError):
            sample_trade.pnl = 100.0

    def test_trade_validates_attributes(self, sample_entry_execution):
        """Test that Trade validates attribute types."""
        trade = Trade(
            trade_id="test-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=sample_entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        assert trade.direction in ["long", "short"]
        assert trade.status in ["OPEN", "CLOSED_WIN", "CLOSED_LOSS", "STOPPED_OUT"]
        assert trade.r_multiple >= 0


class TestCalculateStopLoss:
    """Tests for SL calculation based on SOP rules."""

    @pytest.fixture
    def long_entry_execution(self):
        """Create a long entry execution.
        
        Uses DXY_CONTINUATION to test min(confirmation, bos) SL logic.
        VWAP_RECLAIM has different SL behavior (VWAP-zone SL).
        """
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="DXY_CONTINUATION",  # Changed from VWAP_RECLAIM
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        return EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

    @pytest.fixture
    def confirmation_candle(self):
        """Create a confirmation candle."""
        return Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open=2648.0,
            high=2652.0,
            low=2645.0,
            close=2650.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

    @pytest.fixture
    def bos_candle(self):
        """Create a BOS (break of structure) candle."""
        return Candle(
            timestamp=datetime(2025, 1, 1, 9, 59, tzinfo=UTC),
            open=2640.0,
            high=2646.0,
            low=2638.0,
            close=2644.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

    def test_calculate_sl_long_continuation_uses_min_of_confirmation_and_bos(
        self, long_entry_execution, confirmation_candle, bos_candle
    ):
        """Test SL for long continuation: min(confirmation_low, bos_low)."""
        sl, rationale, _ = calculate_stop_loss(
            long_entry_execution, "long", confirmation_candle, bos_candle
        )

        # SL should be below the lower of the two lows
        expected_sl = min(confirmation_candle.low, bos_candle.low)
        assert sl == expected_sl
        assert "confirmation" in rationale.lower() or "bos" in rationale.lower()

    def test_calculate_sl_long_continuation_without_bos_uses_confirmation(
        self, long_entry_execution, confirmation_candle
    ):
        """Test SL for long continuation without BOS: uses confirmation low."""
        sl, rationale, _ = calculate_stop_loss(
            long_entry_execution, "long", confirmation_candle, bos_candle=None
        )

        assert sl == confirmation_candle.low
        assert "confirmation" in rationale.lower()

    def test_calculate_sl_short_continuation_uses_max_of_confirmation_and_bos(
        self, bos_candle
    ):
        """Test SL for short continuation: max(confirmation_high, bos_high).
        
        Note: DXY_CONTINUATION has 25-tick minimum, so we use candles with 
        high >= 25 ticks from entry to test the max logic without padding.
        """
        # Create confirmation candle with high at 2655.0 (50 ticks from entry)
        confirmation_candle_high = Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open=2648.0,
            high=2655.0,  # 50 ticks above entry (sufficient)
            low=2645.0,
            close=2650.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="DXY_CONTINUATION",
            htf_bias="bearish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        short_entry = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        sl, rationale, _ = calculate_stop_loss(
            short_entry, "short", confirmation_candle_high, bos_candle
        )

        # max(2655, 2646) = 2655, which is 50 ticks > 25-tick minimum, so no padding
        expected_sl = max(confirmation_candle_high.high, bos_candle.high)
        assert sl == expected_sl
        assert "confirmation" in rationale.lower() or "bos" in rationale.lower()

    def test_calculate_sl_fade_setup_uses_sweep_wick(self, confirmation_candle):
        """Test SL for fade setup: beyond sweep candle wick."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"vwap_deviation": 3.0},
            rationale="Test fade",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        fade_entry = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # For fade, confirmation_candle is the sweep candle
        sl, rationale, _ = calculate_stop_loss(
            fade_entry, "long", confirmation_candle, bos_candle=None
        )

        # SL should be below the sweep candle low
        assert sl == confirmation_candle.low
        assert "sweep" in rationale.lower() or "fade" in rationale.lower()

    def test_calculate_sl_short_fade_setup(self, confirmation_candle):
        """Test SL for short fade setup: above sweep candle high."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=9.0,
            confidence="A+",
            factors={"vwap_deviation": 3.0},
            rationale="Test fade",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        fade_entry = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        sl, rationale, _ = calculate_stop_loss(
            fade_entry, "short", confirmation_candle, bos_candle=None
        )

        # SL should be above the sweep candle high
        assert sl == confirmation_candle.high
        assert "sweep" in rationale.lower() or "fade" in rationale.lower()

    def test_calculate_sl_short_continuation_without_bos(self, confirmation_candle):
        """Test SL for short continuation without BOS candle."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_RECLAIM",
            htf_bias="bearish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        short_entry = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        sl, rationale, _ = calculate_stop_loss(
            short_entry, "short", confirmation_candle, bos_candle=None
        )

        assert sl == confirmation_candle.high
        assert "confirmation" in rationale.lower()

    def test_calculate_sl_long_when_confirmation_lower_than_bos(
        self, long_entry_execution
    ):
        """Test SL for long when confirmation low is lower than BOS low."""
        confirmation_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open=2648.0,
            high=2652.0,
            low=2640.0,  # Lower than BOS
            close=2650.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        bos_candle = Candle(
            timestamp=datetime(2025, 1, 1, 9, 59, tzinfo=UTC),
            open=2644.0,
            high=2646.0,
            low=2642.0,  # Higher than confirmation but valid candle
            close=2644.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        sl, rationale, _ = calculate_stop_loss(
            long_entry_execution, "long", confirmation_candle, bos_candle
        )

        # Should select confirmation low since it's lower
        assert sl == confirmation_candle.low
        assert "confirmation" in rationale.lower()

    def test_calculate_sl_short_when_confirmation_higher_than_bos(self):
        """Test SL for short when confirmation high is higher than BOS high."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_RECLAIM",
            htf_bias="bearish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        short_entry = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        confirmation_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open=2648.0,
            high=2660.0,  # Higher than BOS
            low=2645.0,
            close=2650.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        bos_candle = Candle(
            timestamp=datetime(2025, 1, 1, 9, 59, tzinfo=UTC),
            open=2640.0,
            high=2655.0,  # Lower than confirmation
            low=2638.0,
            close=2644.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        sl, rationale, _ = calculate_stop_loss(
            short_entry, "short", confirmation_candle, bos_candle
        )

        # Should select confirmation high since it's higher
        assert sl == confirmation_candle.high
        assert "confirmation" in rationale.lower()

    def test_calculate_sl_short_when_bos_higher_than_confirmation(self):
        """Test SL for short when BOS high is higher than confirmation high."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="DXY_CONTINUATION",  # Changed from VWAP_RECLAIM
            htf_bias="bearish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        short_entry = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        confirmation_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open=2648.0,
            high=2655.0,  # Lower than BOS
            low=2645.0,
            close=2650.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        bos_candle = Candle(
            timestamp=datetime(2025, 1, 1, 9, 59, tzinfo=UTC),
            open=2658.0,
            high=2660.0,  # Higher than confirmation
            low=2638.0,
            close=2644.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        sl, rationale, _ = calculate_stop_loss(
            short_entry, "short", confirmation_candle, bos_candle
        )

        # Should select BOS high since it's higher
        assert sl == bos_candle.high
        assert "bos" in rationale.lower()


class TestCalculateTakeProfit:
    """Tests for TP calculation based on SOP rules."""

    def test_calculate_tp_long_continuation_default_3r(self):
        """Test TP for long continuation: default 3R."""
        entry_price = 2650.0
        stop_loss = 2645.0
        direction = "long"
        setup_type = "VWAP_RECLAIM"
        r_multiple = 3.0
        month = 1  # January
        htf_aligned = True
        dxy_aligned = True

        tp, rationale = calculate_take_profit(
            entry_price,
            stop_loss,
            direction,
            setup_type,
            r_multiple,
            month,
            htf_aligned,
            dxy_aligned,
        )

        risk_distance = entry_price - stop_loss
        expected_tp = entry_price + (risk_distance * r_multiple)
        assert tp == pytest.approx(expected_tp)
        assert "3R" in rationale or "3.0R" in rationale

    def test_calculate_tp_short_continuation_default_3r(self):
        """Test TP for short continuation: default 3R."""
        entry_price = 2650.0
        stop_loss = 2655.0
        direction = "short"
        setup_type = "VWAP_RECLAIM"
        r_multiple = 3.0
        month = 1
        htf_aligned = True
        dxy_aligned = True

        tp, rationale = calculate_take_profit(
            entry_price,
            stop_loss,
            direction,
            setup_type,
            r_multiple,
            month,
            htf_aligned,
            dxy_aligned,
        )

        risk_distance = stop_loss - entry_price
        expected_tp = entry_price - (risk_distance * r_multiple)
        assert tp == pytest.approx(expected_tp)
        assert "3R" in rationale or "3.0R" in rationale

    def test_calculate_tp_continuation_september_max_2r(self):
        """Test TP for continuation in September: max 2R."""
        entry_price = 2650.0
        stop_loss = 2645.0
        direction = "long"
        setup_type = "VWAP_RECLAIM"
        r_multiple = 2.0  # September limit
        month = 9  # September
        htf_aligned = True
        dxy_aligned = True

        tp, rationale = calculate_take_profit(
            entry_price,
            stop_loss,
            direction,
            setup_type,
            r_multiple,
            month,
            htf_aligned,
            dxy_aligned,
        )

        risk_distance = entry_price - stop_loss
        expected_tp = entry_price + (risk_distance * 2.0)
        assert tp == pytest.approx(expected_tp)
        assert "2R" in rationale or "september" in rationale.lower()

    def test_calculate_tp_fade_default_2r(self):
        """Test TP for fade setup: default 2R."""
        entry_price = 2650.0
        stop_loss = 2645.0
        direction = "long"
        setup_type = "VWAP_FADE"
        r_multiple = 2.0
        month = 1
        htf_aligned = False
        dxy_aligned = False

        tp, rationale = calculate_take_profit(
            entry_price,
            stop_loss,
            direction,
            setup_type,
            r_multiple,
            month,
            htf_aligned,
            dxy_aligned,
        )

        risk_distance = entry_price - stop_loss
        expected_tp = entry_price + (risk_distance * 2.0)
        assert tp == pytest.approx(expected_tp)
        assert "2R" in rationale or "fade" in rationale.lower()

    def test_calculate_tp_fade_upgrade_to_3r_when_aligned(self):
        """Test TP for fade setup: upgrade to 3R when HTF/DXY aligned."""
        entry_price = 2650.0
        stop_loss = 2645.0
        direction = "long"
        setup_type = "VWAP_FADE"
        r_multiple = 3.0  # Upgraded
        month = 11  # November (trend window)
        htf_aligned = True
        dxy_aligned = True

        tp, rationale = calculate_take_profit(
            entry_price,
            stop_loss,
            direction,
            setup_type,
            r_multiple,
            month,
            htf_aligned,
            dxy_aligned,
        )

        risk_distance = entry_price - stop_loss
        expected_tp = entry_price + (risk_distance * 3.0)
        assert tp == pytest.approx(expected_tp)
        assert "3R" in rationale or "upgrade" in rationale.lower()

    def test_calculate_tp_continuation_november_december(self):
        """Test TP for continuation in Nov-Dec: 3R trend window."""
        entry_price = 2650.0
        stop_loss = 2645.0
        direction = "long"
        setup_type = "VWAP_RECLAIM"
        r_multiple = 3.0
        month = 12  # December
        htf_aligned = True
        dxy_aligned = True

        tp, rationale = calculate_take_profit(
            entry_price,
            stop_loss,
            direction,
            setup_type,
            r_multiple,
            month,
            htf_aligned,
            dxy_aligned,
        )

        risk_distance = entry_price - stop_loss
        expected_tp = entry_price + (risk_distance * 3.0)
        assert tp == pytest.approx(expected_tp)
        assert "3R" in rationale and (
            "nov-dec" in rationale.lower() or "trend" in rationale.lower()
        )


class TestCreateTradeFromEntry:
    """Tests for create_trade_from_entry helper function."""

    @pytest.fixture
    def entry_execution(self):
        """Create an entry execution for testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        return EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

    @pytest.fixture
    def confirmation_candle(self):
        """Create confirmation candle."""
        return Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            open=2648.0,
            high=2652.0,
            low=2645.0,
            close=2650.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

    @pytest.fixture
    def risk_config(self):
        """Create risk configuration."""
        return {
            "risk_per_trade": 350.0,
            "buffer_phase": "startup",
            "max_contracts": 1,
        }

    @pytest.fixture
    def market_context(self):
        """Create market context."""
        return {
            "month": 1,
            "htf_aligned": True,
            "dxy_aligned": True,
            "seasonality": "default",
        }

    def test_create_trade_from_entry_generates_valid_trade(
        self, entry_execution, confirmation_candle, risk_config, market_context
    ):
        """Test that create_trade_from_entry generates a valid Trade object."""
        trade = create_trade_from_entry(
            entry_execution, confirmation_candle, None, risk_config, market_context
        )

        assert isinstance(trade, Trade)
        assert trade.symbol == "GC"
        assert trade.direction == "long"
        assert trade.entry_price == 2650.0
        assert trade.stop_loss < trade.entry_price  # Long trade SL below entry
        assert trade.take_profit > trade.entry_price  # Long trade TP above entry
        assert trade.r_multiple > 0
        assert trade.status == "OPEN"

    def test_create_trade_from_entry_generates_unique_trade_id(
        self, entry_execution, confirmation_candle, risk_config, market_context
    ):
        """Test that each trade gets a unique trade ID."""
        trade1 = create_trade_from_entry(
            entry_execution, confirmation_candle, None, risk_config, market_context
        )
        trade2 = create_trade_from_entry(
            entry_execution, confirmation_candle, None, risk_config, market_context
        )

        assert trade1.trade_id != trade2.trade_id
        # Should be valid UUID format
        assert UUID(trade1.trade_id)
        assert UUID(trade2.trade_id)

    def test_create_trade_from_entry_calculates_risk_reward_correctly(
        self, entry_execution, confirmation_candle, risk_config, market_context
    ):
        """Test risk/reward amounts are calculated correctly."""
        trade = create_trade_from_entry(
            entry_execution, confirmation_candle, None, risk_config, market_context
        )

        risk_distance = abs(trade.entry_price - trade.stop_loss)
        reward_distance = abs(trade.take_profit - trade.entry_price)

        # Calculate expected amounts (in points, not dollars)
        expected_risk = risk_distance
        expected_reward = reward_distance

        assert trade.risk_amount == pytest.approx(expected_risk)
        assert trade.reward_amount == pytest.approx(expected_reward)
        assert trade.reward_amount / trade.risk_amount == pytest.approx(
            trade.r_multiple
        )

    def test_create_trade_from_entry_fade_without_full_alignment(
        self, confirmation_candle, risk_config
    ):
        """Test fade setup gets 2R when not fully aligned."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"vwap_deviation": 3.0},
            rationale="Test fade",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        fade_entry = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        market_context = {
            "month": 10,  # Not Nov-Dec
            "htf_aligned": True,
            "dxy_aligned": False,  # Not aligned
        }

        trade = create_trade_from_entry(
            fade_entry, confirmation_candle, None, risk_config, market_context
        )

        # Fade without full alignment should get 2R
        assert trade.r_multiple == 2.0

    def test_create_trade_from_entry_fade_with_full_alignment_november(
        self, confirmation_candle, risk_config
    ):
        """Test fade setup gets 3R in Nov-Dec with full alignment."""
        signal = Signal(
            timestamp=datetime(2025, 11, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_FADE",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"vwap_deviation": 3.0},
            rationale="Test fade",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        fade_entry = EntryExecution(
            signal_timestamp=datetime(2025, 11, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        market_context = {
            "month": 11,  # November
            "htf_aligned": True,
            "dxy_aligned": True,  # Fully aligned
        }

        trade = create_trade_from_entry(
            fade_entry, confirmation_candle, None, risk_config, market_context
        )

        # Fade with full alignment in Nov-Dec should get 3R
        assert trade.r_multiple == 3.0

    def test_create_trade_from_entry_continuation_september(
        self, confirmation_candle, risk_config
    ):
        """Test continuation setup gets 2R in September."""
        signal = Signal(
            timestamp=datetime(2025, 9, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        sept_entry = EntryExecution(
            signal_timestamp=datetime(2025, 9, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 9, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        market_context = {
            "month": 9,  # September
            "htf_aligned": True,
            "dxy_aligned": True,
        }

        trade = create_trade_from_entry(
            sept_entry, confirmation_candle, None, risk_config, market_context
        )

        # September continuation should get 2R (defensive)
        assert trade.r_multiple == 2.0


class TestCloseTrade:
    """Tests for closing trades and exit logic."""

    @pytest.fixture
    def open_trade(self):
        """Create an open trade for testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        return Trade(
            trade_id="test-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Test",
            tp_rationale="Test 3R",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

    @pytest.fixture
    def exit_candle_win(self):
        """Create an exit candle at TP (win)."""
        return Candle(
            timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            open=2664.0,
            high=2666.0,
            low=2663.0,
            close=2665.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

    @pytest.fixture
    def exit_candle_loss(self):
        """Create an exit candle at SL (loss)."""
        return Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2646.0,
            high=2647.0,
            low=2644.0,
            close=2645.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

    def test_close_trade_at_take_profit(self, open_trade, exit_candle_win):
        """Test closing trade at take profit (winning trade)."""
        closed_trade = close_trade(open_trade, exit_candle_win, "TP")

        assert closed_trade.exit_timestamp == exit_candle_win.timestamp
        assert closed_trade.exit_price == open_trade.take_profit
        assert closed_trade.exit_reason == "TP"
        assert closed_trade.status == "CLOSED_WIN"
        assert closed_trade.pnl > 0
        assert closed_trade.r_realized == pytest.approx(3.0)

    def test_close_trade_at_stop_loss(self, open_trade, exit_candle_loss):
        """Test closing trade at stop loss (losing trade)."""
        closed_trade = close_trade(open_trade, exit_candle_loss, "SL")

        assert closed_trade.exit_timestamp == exit_candle_loss.timestamp
        assert closed_trade.exit_price == open_trade.stop_loss
        assert closed_trade.exit_reason == "SL"
        assert closed_trade.status == "STOPPED_OUT"
        assert closed_trade.pnl < 0
        assert closed_trade.r_realized == pytest.approx(-1.0)

    def test_close_trade_on_invalidation(self, open_trade):
        """Test closing trade due to invalidation (DXY flip, structure break, etc)."""
        invalidation_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 3, tzinfo=UTC),
            open=2652.0,
            high=2653.0,
            low=2650.0,
            close=2651.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        closed_trade = close_trade(open_trade, invalidation_candle, "INVALIDATION")

        assert closed_trade.exit_reason == "INVALIDATION"
        assert closed_trade.invalidation_triggered is True
        assert closed_trade.status in ["CLOSED_WIN", "CLOSED_LOSS"]
        # PnL should be calculated at current price
        assert closed_trade.exit_price == invalidation_candle.close

    def test_close_trade_calculates_duration(self, open_trade, exit_candle_win):
        """Test that trade duration is calculated in bars."""
        closed_trade = close_trade(open_trade, exit_candle_win, "TP")

        # Exit is 9 minutes after entry (9 bars for 1m timeframe)
        expected_duration = 9
        assert closed_trade.duration_bars == expected_duration

    def test_close_trade_returns_new_instance(self, open_trade, exit_candle_win):
        """Test that close_trade returns a new Trade instance (immutability)."""
        closed_trade = close_trade(open_trade, exit_candle_win, "TP")

        # Original trade should remain unchanged
        assert open_trade.status == "OPEN"
        assert open_trade.exit_timestamp is None

        # Closed trade should have exit details
        assert closed_trade.status == "CLOSED_WIN"
        assert closed_trade.exit_timestamp is not None
        assert id(open_trade) != id(closed_trade)

    def test_close_trade_on_time_limit(self, open_trade):
        """Test closing trade due to time limit (max bars exceeded)."""
        time_exit_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 25, tzinfo=UTC),  # 24 bars later
            open=2652.0,
            high=2654.0,
            low=2651.0,
            close=2653.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        closed_trade = close_trade(open_trade, time_exit_candle, "TIME")

        assert closed_trade.exit_reason == "TIME"
        assert closed_trade.exit_price == time_exit_candle.close
        # Trade closed at profit (2653 > 2650 entry)
        assert closed_trade.status == "CLOSED_WIN"
        assert closed_trade.pnl > 0
        assert closed_trade.duration_bars == 24

    def test_close_trade_time_exit_at_loss(self, open_trade):
        """Test closing trade on time limit when at a loss."""
        time_exit_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 25, tzinfo=UTC),
            open=2647.0,
            high=2648.0,
            low=2646.0,
            close=2647.0,  # Below entry
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        closed_trade = close_trade(open_trade, time_exit_candle, "TIME")

        assert closed_trade.exit_reason == "TIME"
        assert closed_trade.status == "CLOSED_LOSS"
        assert closed_trade.pnl < 0

    def test_close_trade_with_5m_timeframe(self):
        """Test closing trade with 5m timeframe calculates duration correctly."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="5m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        trade_5m = Trade(
            trade_id="test-001",
            symbol="GC",
            timeframe="5m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Test",
            tp_rationale="Test 3R",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        exit_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 35, tzinfo=UTC),  # 30 minutes later
            open=2664.0,
            high=2666.0,
            low=2663.0,
            close=2665.0,
            volume=1000.0,
            symbol="GC",
            timeframe="5m",
            source="TEST",
        )

        closed_trade = close_trade(trade_5m, exit_candle, "TP")

        # 30 minutes / 5 minutes per bar = 6 bars
        assert closed_trade.duration_bars == 6

    def test_close_trade_with_config_calculates_dollar_pnl(self, open_trade):
        """Test close_trade calculates dollar-based PnL when config provided."""
        config = {
            "assets": {
                "tick_values": {"GC": 10.0},
                "tick_sizes": {"GC": 0.1},
            },
            "backtest": {
                "slippage_points": 0.5,
                "commission_per_trade": 5.0,
            },
        }

        exit_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            open=2664.0,
            high=2666.0,
            low=2663.0,
            close=2665.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        closed_trade = close_trade(open_trade, exit_candle, "TP", config)

        # Verify dollar-based PnL was calculated
        assert closed_trade.pnl_dollars is not None
        assert closed_trade.pnl_net is not None
        assert closed_trade.slippage_cost is not None
        assert closed_trade.commission_cost is not None

        # Verify values match expected calculations
        # Gross: 15 points × $10/point = $1,500
        assert closed_trade.pnl_dollars == pytest.approx(1500.0)
        # PATCH PART 5: Slippage now dynamic - default 2 ticks (no ATR provided) × $10 = -$20 (was -$50)
        assert closed_trade.slippage_cost == pytest.approx(-20.0)
        # Commission: $5 × 2 (entry+exit) × 1 contract = -$10
        assert closed_trade.commission_cost == pytest.approx(-10.0)
        # Net: $1,500 - $20 - $10 = $1,470
        assert closed_trade.pnl_net == pytest.approx(1470.0)

    def test_close_trade_without_config_has_none_dollar_pnl(self, open_trade):
        """Test close_trade without config leaves dollar PnL as None."""
        exit_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            open=2664.0,
            high=2666.0,
            low=2663.0,
            close=2665.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        closed_trade = close_trade(open_trade, exit_candle, "TP")  # No config

        # Dollar-based PnL should be None
        assert closed_trade.pnl_dollars is None
        assert closed_trade.pnl_net is None
        assert closed_trade.slippage_cost is None
        assert closed_trade.commission_cost is None

        # Point-based PnL should still be calculated
        assert closed_trade.pnl is not None
        assert closed_trade.r_realized is not None

    def test_close_trade_with_zero_risk_amount(self):
        """Test close_trade handles zero risk_amount without ZeroDivisionError.

        This edge case occurs when entry_price equals stop_loss (which should
        never happen in production, but we must handle it gracefully in tests).
        """
        # Create trade with zero risk (entry_price == stop_loss)
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=8.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test signal",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Create trade where entry_price == stop_loss (zero risk)
        trade = Trade(
            trade_id="test-zero-risk",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2650.0,  # Same as entry_price!
            take_profit=2665.0,
            sl_rationale="Test SL",
            tp_rationale="Test TP",
            risk_amount=0.0,  # Zero risk
            reward_amount=15.0,
            r_multiple=0.0,  # Cannot calculate R when risk is zero
            contracts=1,
            status="OPEN",
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            duration_bars=None,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
        )

        # Create exit candle
        exit_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 5, tzinfo=UTC),
            open=2655.0,
            high=2656.0,
            low=2654.0,
            close=2655.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # This should NOT raise ZeroDivisionError
        closed_trade = close_trade(trade, exit_candle, "TP")

        # Verify calculations handled zero risk gracefully
        assert closed_trade.pnl_percent == 0  # Should be 0, not error
        assert closed_trade.r_realized == 0  # Should be 0, not error
        assert closed_trade.status == "CLOSED_WIN"  # Did make money in absolute terms
        assert closed_trade.pnl == 15.0  # 15 points profit (TP at 2665 - entry 2650)

    def test_close_trade_pnl_percent_consistent_with_r_realized_multiple_contracts(
        self,
    ):
        """Test pnl_percent is consistent with r_realized for multiple contracts.

        Regression test for bug where pnl_percent was calculated as
        (total_pnl / per_contract_risk) * 100, causing it to be inconsistent
        with r_realized when contracts > 1.

        For a 3R trade with 3 contracts:
        - r_realized should equal 3.0
        - pnl_percent should equal 300% (not 900%)
        """
        # Create signal
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Create trade with 3 contracts, risk=5.0 points, r_multiple=3.0
        trade = Trade(
            trade_id="test-multi-contracts",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,  # 5 points risk
            take_profit=2665.0,  # 15 points reward (3R)
            sl_rationale="Continuation SL",
            tp_rationale="3R target",
            risk_amount=5.0,  # Per-contract risk
            reward_amount=15.0,  # Per-contract reward
            r_multiple=3.0,
            contracts=3,  # Multiple contracts
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        # Exit at +3R (take profit)
        exit_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 15, tzinfo=UTC),
            open=2665.0,
            high=2665.0,
            low=2665.0,
            close=2665.0,
            volume=100.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        closed_trade = close_trade(trade, exit_candle, "TP")

        # Verify PnL calculations
        # Total PnL = 15 points × 3 contracts = 45 points
        assert closed_trade.pnl == pytest.approx(45.0)

        # r_realized = per-contract PnL / per-contract risk = 15 / 5 = 3.0
        assert closed_trade.r_realized == pytest.approx(3.0)

        # pnl_percent should be consistent with r_realized
        # Expected: 3.0R × 100 = 300%
        # Bug would give: 45 / 5 × 100 = 900%
        expected_pnl_percent = closed_trade.r_realized * 100
        assert closed_trade.pnl_percent == pytest.approx(expected_pnl_percent)
        assert closed_trade.pnl_percent == pytest.approx(300.0)

    def test_close_trade_pnl_percent_consistent_with_r_realized_short_multiple_contracts(
        self,
    ):
        """Test pnl_percent consistency for short trades with multiple contracts."""
        # Create signal for short trade
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="short",
            setup_type="VWAP_FADE",
            htf_bias="bearish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test short",
            validation_flags={},
            enforcer_tier="Mild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        # Short trade with 2 contracts, 2R target
        trade = Trade(
            trade_id="test-short-multi",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="short",
            setup_type="VWAP_FADE",
            stop_loss=2655.0,  # 5 points risk (above entry for short)
            take_profit=2640.0,  # 10 points reward (2R)
            sl_rationale="Fade SL",
            tp_rationale="2R target",
            risk_amount=5.0,
            reward_amount=10.0,
            r_multiple=2.0,
            contracts=2,  # Multiple contracts
            exit_timestamp=None,
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        # Exit at +2R (take profit)
        exit_candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            open=2640.0,
            high=2640.0,
            low=2640.0,
            close=2640.0,
            volume=100.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        closed_trade = close_trade(trade, exit_candle, "TP")

        # Total PnL = 10 points × 2 contracts = 20 points
        assert closed_trade.pnl == pytest.approx(20.0)

        # r_realized = 10 / 5 = 2.0
        assert closed_trade.r_realized == pytest.approx(2.0)

        # pnl_percent should be 200%, not 400%
        assert closed_trade.pnl_percent == pytest.approx(200.0)
        assert closed_trade.pnl_percent == pytest.approx(closed_trade.r_realized * 100)


class TestJSONSerialization:
    """Tests for JSON serialization (to_dict/from_dict)."""

    @pytest.fixture
    def sample_trade(self):
        """Create a complete closed trade for serialization testing."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={"structure_alignment": 2.0},
            rationale="Test",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        return Trade(
            trade_id="test-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Test SL",
            tp_rationale="Test TP",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=datetime(2025, 1, 1, 10, 10, tzinfo=UTC),
            exit_price=2665.0,
            exit_reason="TP",
            pnl=15.0,
            pnl_percent=300.0,
            r_realized=3.0,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="CLOSED_WIN",
            duration_bars=9,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

    def test_to_dict_returns_serializable_dict(self, sample_trade):
        """Test that to_dict returns a JSON-serializable dictionary."""
        import json

        trade_dict = to_dict(sample_trade)

        assert isinstance(trade_dict, dict)
        # Should be JSON-serializable
        json_str = json.dumps(trade_dict)
        assert isinstance(json_str, str)

    def test_to_dict_includes_all_attributes(self, sample_trade):
        """Test that to_dict includes all Trade attributes."""
        trade_dict = to_dict(sample_trade)

        assert "trade_id" in trade_dict
        assert "symbol" in trade_dict
        assert "entry_price" in trade_dict
        assert "stop_loss" in trade_dict
        assert "take_profit" in trade_dict
        assert "pnl" in trade_dict
        assert "status" in trade_dict
        assert "entry_execution" in trade_dict

    def test_from_dict_reconstructs_trade(self, sample_trade):
        """Test that from_dict reconstructs Trade from dict."""
        trade_dict = to_dict(sample_trade)
        reconstructed_trade = from_dict(trade_dict)

        assert isinstance(reconstructed_trade, Trade)
        assert reconstructed_trade.trade_id == sample_trade.trade_id
        assert reconstructed_trade.symbol == sample_trade.symbol
        assert reconstructed_trade.entry_price == sample_trade.entry_price
        assert reconstructed_trade.pnl == sample_trade.pnl

    def test_roundtrip_serialization(self, sample_trade):
        """Test that Trade survives to_dict → from_dict roundtrip."""
        trade_dict = to_dict(sample_trade)
        reconstructed = from_dict(trade_dict)

        # All attributes should match
        assert reconstructed.trade_id == sample_trade.trade_id
        assert reconstructed.symbol == sample_trade.symbol
        assert reconstructed.timeframe == sample_trade.timeframe
        assert reconstructed.entry_price == sample_trade.entry_price
        assert reconstructed.stop_loss == sample_trade.stop_loss
        assert reconstructed.take_profit == sample_trade.take_profit
        assert reconstructed.pnl == sample_trade.pnl
        assert reconstructed.status == sample_trade.status
        assert reconstructed.direction == sample_trade.direction

    def test_to_dict_handles_none_values(self):
        """Test that to_dict handles None values for optional fields."""
        signal = Signal(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            symbol="GC",
            timeframe="1m",
            direction="long",
            setup_type="VWAP_RECLAIM",
            htf_bias="bullish",
            score=9.0,
            confidence="A+",
            factors={},
            rationale="Test",
            validation_flags={},
            enforcer_tier="EarlyMild",
        )

        entry_execution = EntryExecution(
            signal_timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            signal=signal,
            executed=True,
            rejection_reason=None,
        )

        open_trade = Trade(
            trade_id="test-001",
            symbol="GC",
            timeframe="1m",
            entry_execution=entry_execution,
            entry_timestamp=datetime(2025, 1, 1, 10, 1, tzinfo=UTC),
            entry_price=2650.0,
            direction="long",
            setup_type="VWAP_RECLAIM",
            stop_loss=2645.0,
            take_profit=2665.0,
            sl_rationale="Test",
            tp_rationale="Test",
            risk_amount=5.0,
            reward_amount=15.0,
            r_multiple=3.0,
            contracts=1,
            exit_timestamp=None,  # Not closed yet
            exit_price=None,
            exit_reason=None,
            pnl=None,
            pnl_percent=None,
            r_realized=None,
            pnl_dollars=None,
            pnl_net=None,
            slippage_cost=None,
            commission_cost=None,
            status="OPEN",
            duration_bars=None,
            invalidation_triggered=False,
            ignore_first_retest_bar=False,
        )

        trade_dict = to_dict(open_trade)
        assert trade_dict["exit_timestamp"] is None
        assert trade_dict["exit_price"] is None
        assert trade_dict["pnl"] is None
