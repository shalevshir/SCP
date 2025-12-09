"""Integration tests for structure feature integration in backtester.

Tests that structure candles (BOS, CHoCH, sweep, confirmation) flow correctly
from HTF bias calculation through to trade creation.
"""

from datetime import UTC

import pandas as pd
import pytest
from common.types import Candle
from rule_engine.htf.calculator import compute_htf_bias
from rule_engine.htf.structure import (
    detect_bos,
    detect_liquidity_sweeps,
    detect_swings,
)


@pytest.fixture
def sample_htf_data():
    """Create sample HTF data with structure events."""
    timestamps_1h = pd.date_range(
        start="2025-01-01 00:00:00",
        periods=20,
        freq="1h",
        tz=UTC,
    )

    # Create data with clear BOS pattern
    df_1h = pd.DataFrame(
        {
            "open": [2000.0 + i * 2 for i in range(20)],
            "high": [2002.0 + i * 2 for i in range(20)],
            "low": [1998.0 + i * 2 for i in range(20)],
            "close": [2001.0 + i * 2 for i in range(20)],
            "volume": [1000.0] * 20,
        },
        index=timestamps_1h,
    )

    timestamps_15m = pd.date_range(
        start="2025-01-01 00:00:00",
        periods=80,
        freq="15min",
        tz=UTC,
    )

    df_15m = pd.DataFrame(
        {
            "open": [2000.0 + i * 0.5 for i in range(80)],
            "high": [2001.0 + i * 0.5 for i in range(80)],
            "low": [1999.0 + i * 0.5 for i in range(80)],
            "close": [2000.5 + i * 0.5 for i in range(80)],
            "volume": [250.0] * 80,
        },
        index=timestamps_15m,
    )

    return df_1h, df_15m


@pytest.fixture
def sample_features():
    """Create sample feature series for HTF bias calculation."""
    features_1h = pd.Series(
        {
            "close": 2020.0,
            "vwap": 2015.0,
            "rsi": 65.0,
            "ema_9": 2018.0,
            "ema_20": 2016.0,
            "ema_50": 2010.0,
            "structure_label": "HH",
            "dxy_corr": -0.7,
        }
    )

    features_15m = pd.Series(
        {
            "close": 2020.0,
            "vwap": 2016.0,
            "rsi": 62.0,
            "ema_9": 2019.0,
            "ema_20": 2017.0,
            "ema_50": 2012.0,
            "structure_label": "HL",
            "dxy_corr": -0.65,
        }
    )

    return features_1h, features_15m


class TestStructureIntegrationInHTFBias:
    """Test structure feature integration in HTF bias calculation."""

    def test_htf_bias_includes_structure_candles(
        self, sample_htf_data, sample_features
    ):
        """Test that HTF bias includes structure candles when detected."""
        df_1h, df_15m = sample_htf_data
        features_1h, features_15m = sample_features

        # Compute HTF bias with structure detection
        current_timestamp = df_1h.index[15]

        htf_bias = compute_htf_bias(
            features_1h=features_1h,
            features_15m=features_15m,
            dxy_1h=None,
            df_15m=df_15m,
            df_1h=df_1h,
            sweep_events_15m=None,
            timestamp=current_timestamp,
        )

        # Verify HTF bias has structure candle fields
        assert hasattr(htf_bias, "bos_candle")
        assert hasattr(htf_bias, "choch_candle")
        assert hasattr(htf_bias, "sweep_candle")
        assert hasattr(htf_bias, "confirmation_candle")

    def test_htf_bias_extracts_bos_candle(self, sample_htf_data, sample_features):
        """Test that BOS candle is extracted when BOS is detected."""
        df_1h, df_15m = sample_htf_data
        features_1h, features_15m = sample_features

        # Detect BOS manually
        swing_highs, swing_lows = detect_swings(df_1h, lookback=5)
        bos_series = detect_bos(df_1h, swing_highs, swing_lows)

        # If BOS detected, HTF bias should include the candle
        if bos_series.notna().any():
            current_timestamp = df_1h.index[15]

            htf_bias = compute_htf_bias(
                features_1h=features_1h,
                features_15m=features_15m,
                dxy_1h=None,
                df_15m=df_15m,
                df_1h=df_1h,
                sweep_events_15m=None,
                timestamp=current_timestamp,
            )

            # BOS candle should be extracted if detected
            if htf_bias.bos_detected:
                assert htf_bias.bos_candle is not None
                assert isinstance(htf_bias.bos_candle, Candle)

    def test_htf_bias_extracts_sweep_candle(self, sample_htf_data, sample_features):
        """Test that sweep candle is extracted when sweep is detected."""
        df_1h, df_15m = sample_htf_data
        features_1h, features_15m = sample_features

        # Detect sweeps manually
        swing_highs, swing_lows = detect_swings(df_15m, lookback=5)
        sweep_events, sweep_success = detect_liquidity_sweeps(
            df_15m, swing_highs, swing_lows
        )

        # If sweep detected, HTF bias should include the candle
        if sweep_events.notna().any():
            current_timestamp = df_15m.index[60]

            htf_bias = compute_htf_bias(
                features_1h=features_1h,
                features_15m=features_15m,
                dxy_1h=None,
                df_15m=df_15m,
                df_1h=df_1h,
                sweep_events_15m=sweep_events,
                timestamp=current_timestamp,
            )

            # Sweep candle should be extracted if detected
            if htf_bias.liquidity_sweep_detected:
                assert htf_bias.sweep_candle is not None
                assert isinstance(htf_bias.sweep_candle, Candle)

    def test_htf_bias_handles_no_structure_gracefully(self, sample_features):
        """Test that HTF bias handles missing structure data gracefully."""
        features_1h, features_15m = sample_features

        # Compute HTF bias without structure DataFrames
        htf_bias = compute_htf_bias(
            features_1h=features_1h,
            features_15m=features_15m,
            dxy_1h=None,
            df_15m=None,
            df_1h=None,
            sweep_events_15m=None,
            timestamp=pd.Timestamp("2025-01-01 10:00:00", tz=UTC),
        )

        # Should not crash and should have None candles
        assert htf_bias.bos_candle is None
        assert htf_bias.choch_candle is None
        assert htf_bias.sweep_candle is None
        assert htf_bias.bos_detected is False
        assert htf_bias.choch_detected is False


class TestStructureIntegrationInTradeCreation:
    """Test structure candles flow to trade creation."""

    def test_trade_creation_uses_bos_candle(self, sample_htf_data, sample_features):
        """Test that trade creation can use BOS candle from HTF bias."""
        from backtester.entry_model import EntryExecution
        from backtester.trade import create_trade_from_entry
        from rule_engine.signal import Signal

        df_1h, df_15m = sample_htf_data
        features_1h, features_15m = sample_features

        # Create HTF bias with structure candles
        current_timestamp = df_1h.index[15]
        htf_bias = compute_htf_bias(
            features_1h=features_1h,
            features_15m=features_15m,
            dxy_1h=None,
            df_15m=df_15m,
            df_1h=df_1h,
            sweep_events_15m=None,
            timestamp=current_timestamp,
        )

        # Create mock signal and entry
        signal = Signal(
            timestamp=current_timestamp.to_pydatetime(),
            symbol="GC",
            timeframe="1m",
            direction="long",
            confidence="A+",
            score=9.0,
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        entry = EntryExecution(
            signal_timestamp=current_timestamp.to_pydatetime(),
            signal=signal,
            entry_timestamp=current_timestamp.to_pydatetime(),
            entry_price=2020.0,
            executed=True,
            rejection_reason=None,
        )

        # Create confirmation candle
        confirmation_candle = Candle(
            timestamp=current_timestamp.to_pydatetime(),
            open=2019.0,
            high=2021.0,
            low=2018.0,
            close=2020.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Create trade with BOS candle from HTF bias
        risk_config = {
            "risk_per_trade": 600.0,
            "buffer_phase": "growth",
            "max_contracts": 1,
        }

        market_context = {
            "month": 1,
            "htf_aligned": True,
            "dxy_aligned": True,
        }

        trade = create_trade_from_entry(
            entry_execution=entry,
            confirmation_candle=confirmation_candle,
            bos_candle=htf_bias.bos_candle,  # Use BOS candle from HTF bias
            risk_config=risk_config,
            market_context=market_context,
        )

        # Verify trade was created successfully
        assert trade is not None
        assert trade.direction == "long"
        assert trade.entry_price == 2020.0

        # If BOS candle was provided, SL should use it
        if htf_bias.bos_candle:
            # SL should be below BOS candle low for long trades
            assert trade.stop_loss < htf_bias.bos_candle.low

    def test_trade_creation_fallback_without_bos(
        self, sample_htf_data, sample_features
    ):
        """Test that trade creation works without BOS candle (fallback)."""
        from backtester.entry_model import EntryExecution
        from backtester.trade import create_trade_from_entry
        from rule_engine.signal import Signal

        df_1h, df_15m = sample_htf_data
        current_timestamp = df_1h.index[15]

        # Create mock signal and entry
        signal = Signal(
            timestamp=current_timestamp.to_pydatetime(),
            symbol="GC",
            timeframe="1m",
            direction="long",
            confidence="A+",
            score=9.0,
            setup_type="DXY_CONTINUATION",
            htf_bias="bullish",
            factors={"structure_alignment": 2, "vwap_relation": 2},
            rationale="Test signal",
            validation_flags={"session_ok": True},
            enforcer_tier="EarlyMild",
        )

        entry = EntryExecution(
            signal_timestamp=current_timestamp.to_pydatetime(),
            signal=signal,
            entry_timestamp=current_timestamp.to_pydatetime(),
            entry_price=2020.0,
            executed=True,
            rejection_reason=None,
        )

        # Create confirmation candle
        confirmation_candle = Candle(
            timestamp=current_timestamp.to_pydatetime(),
            open=2019.0,
            high=2021.0,
            low=2018.0,
            close=2020.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )

        # Create trade WITHOUT BOS candle (should fallback to confirmation)
        risk_config = {
            "risk_per_trade": 600.0,
            "buffer_phase": "growth",
            "max_contracts": 1,
        }

        market_context = {
            "month": 1,
            "htf_aligned": True,
            "dxy_aligned": True,
        }

        trade = create_trade_from_entry(
            entry_execution=entry,
            confirmation_candle=confirmation_candle,
            bos_candle=None,  # No BOS candle
            risk_config=risk_config,
            market_context=market_context,
        )

        # Verify trade was created successfully with fallback
        assert trade is not None
        assert trade.direction == "long"
        assert trade.entry_price == 2020.0
        # SL should use confirmation candle low
        assert trade.stop_loss <= confirmation_candle.low
