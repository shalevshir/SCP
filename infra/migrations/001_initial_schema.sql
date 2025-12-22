-- SCP Trading Bot - Initial Database Schema
-- TimescaleDB extension for time-series data

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- CANDLES TABLE
-- ============================================================================
-- Hypertable for efficient time-range queries on OHLCV data
CREATE TABLE candles (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    open NUMERIC(12,4) NOT NULL,
    high NUMERIC(12,4) NOT NULL,
    low NUMERIC(12,4) NOT NULL,
    close NUMERIC(12,4) NOT NULL,
    volume NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (timestamp, symbol, timeframe)
);

-- Convert to hypertable (partitioned by time)
SELECT create_hypertable('candles', 'timestamp');

-- ============================================================================
-- FEATURES TABLE
-- ============================================================================
-- Computed features for warmup recovery after service restarts
CREATE TABLE features (
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    close NUMERIC(12,4),
    vwap NUMERIC(12,4),
    rsi NUMERIC(6,2),
    ema_9 NUMERIC(12,4),
    ema_20 NUMERIC(12,4),
    ema_50 NUMERIC(12,4),
    dxy_correlation NUMERIC(5,3),
    structure_label VARCHAR(20),
    vwap_deviation NUMERIC(8,4),
    PRIMARY KEY (timestamp, symbol, timeframe)
);

-- Convert to hypertable
SELECT create_hypertable('features', 'timestamp');

-- ============================================================================
-- HTF BIAS HISTORY TABLE
-- ============================================================================
-- Higher-timeframe bias audit trail
CREATE TABLE htf_bias_history (
    timestamp TIMESTAMPTZ NOT NULL,
    bias VARCHAR(10) NOT NULL CHECK (bias IN ('bullish', 'bearish', 'neutral')),
    score NUMERIC(4,2) NOT NULL CHECK (score >= 0 AND score <= 10),
    confidence VARCHAR(10) NOT NULL CHECK (confidence IN ('A+', 'A', 'B', 'C')),
    structure_15m VARCHAR(20),
    structure_1h VARCHAR(20),
    dxy_aligned BOOLEAN,
    chop_detected BOOLEAN,
    PRIMARY KEY (timestamp)
);

-- Convert to hypertable
SELECT create_hypertable('htf_bias_history', 'timestamp');

-- ============================================================================
-- TRADES TABLE
-- ============================================================================
-- Full trade lifecycle with audit trail
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id UUID NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('long', 'short')),
    setup_type VARCHAR(30) NOT NULL,
    entry_price NUMERIC(12,4) NOT NULL,
    sl_price NUMERIC(12,4) NOT NULL,
    tp_price NUMERIC(12,4) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    exit_price NUMERIC(12,4),
    exit_reason VARCHAR(30),
    pnl_points NUMERIC(8,2),
    pnl_dollars NUMERIC(12,2),
    r_multiple NUMERIC(4,2),
    state VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (state IN ('OPEN', 'CLOSED', 'INVALIDATED')),
    confirmations JSONB,
    transition_history JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- STATE MACHINE SNAPSHOTS TABLE
-- ============================================================================
-- For execution service recovery - tracks active VWAP reclaim state machines
CREATE TABLE state_machine_snapshots (
    signal_id UUID PRIMARY KEY,
    state VARCHAR(20) NOT NULL,
    detection_bar_idx INTEGER,
    reclaim_direction VARCHAR(10) CHECK (reclaim_direction IN ('long', 'short')),
    confirmations JSONB,
    execution_count INTEGER DEFAULT 0,
    transition_history JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- DAILY STATE TABLE
-- ============================================================================
-- For Bot Core recovery - daily counters and guardrails
CREATE TABLE daily_state (
    date DATE PRIMARY KEY,
    loss_streak INTEGER DEFAULT 0 CHECK (loss_streak >= 0),
    daily_loss NUMERIC(12,2) DEFAULT 0,
    trades_count INTEGER DEFAULT 0 CHECK (trades_count >= 0),
    wins INTEGER DEFAULT 0 CHECK (wins >= 0),
    losses INTEGER DEFAULT 0 CHECK (losses >= 0),
    pdll_hits INTEGER DEFAULT 0 CHECK (pdll_hits >= 0),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- TRIGGERS
-- ============================================================================
-- Update updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_state_machines_updated_at
    BEFORE UPDATE ON state_machine_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_daily_state_updated_at
    BEFORE UPDATE ON daily_state
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON TABLE candles IS 'Raw OHLCV candle data from data adapter service';
COMMENT ON TABLE features IS 'Computed features for warmup and historical analysis';
COMMENT ON TABLE htf_bias_history IS 'Higher-timeframe bias decisions over time';
COMMENT ON TABLE trades IS 'Complete trade lifecycle with P&L tracking';
COMMENT ON TABLE state_machine_snapshots IS 'Active state machines for recovery';
COMMENT ON TABLE daily_state IS 'Daily trading statistics and guardrails';

