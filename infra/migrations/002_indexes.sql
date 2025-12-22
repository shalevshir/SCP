-- SCP Trading Bot - Performance Indexes
-- Optimize common query patterns

-- ============================================================================
-- TRADES TABLE INDEXES
-- ============================================================================
-- Query trades by state (e.g., find all open trades)
CREATE INDEX idx_trades_state ON trades(state);

-- Query trades by opening time
CREATE INDEX idx_trades_opened_at ON trades(opened_at DESC);

-- Query trades by signal (trace signal to trade)
CREATE INDEX idx_trades_signal_id ON trades(signal_id);

-- Query trades by setup type for analytics
CREATE INDEX idx_trades_setup_type ON trades(setup_type);

-- Composite index for active trades queries
CREATE INDEX idx_trades_active ON trades(state, opened_at DESC) WHERE state = 'OPEN';

-- ============================================================================
-- CANDLES TABLE INDEXES
-- ============================================================================
-- Query candles by symbol and timeframe
CREATE INDEX idx_candles_symbol_timeframe ON candles(symbol, timeframe, timestamp DESC);

-- ============================================================================
-- FEATURES TABLE INDEXES
-- ============================================================================
-- Query features by symbol and timeframe for warmup
CREATE INDEX idx_features_symbol_timeframe ON features(symbol, timeframe, timestamp DESC);

-- ============================================================================
-- STATE MACHINE SNAPSHOTS INDEXES
-- ============================================================================
-- Query by state for finding pending confirmations
CREATE INDEX idx_state_machines_state ON state_machine_snapshots(state);

-- Query by creation time for cleanup/expiration
CREATE INDEX idx_state_machines_created_at ON state_machine_snapshots(created_at DESC);

-- ============================================================================
-- DAILY STATE INDEXES
-- ============================================================================
-- Query by date range for analytics (already has primary key, but explicit for clarity)
CREATE INDEX idx_daily_state_date ON daily_state(date DESC);

-- ============================================================================
-- HTF BIAS HISTORY INDEXES
-- ============================================================================
-- Query recent bias for context
CREATE INDEX idx_htf_bias_timestamp ON htf_bias_history(timestamp DESC);

-- Query by bias type for analytics
CREATE INDEX idx_htf_bias_bias ON htf_bias_history(bias);

-- ============================================================================
-- HYPERTABLE OPTIMIZATIONS
-- ============================================================================
-- TimescaleDB compression policy for older data (7 days+)
-- Uncomment in production after accumulating data
-- SELECT add_compression_policy('candles', INTERVAL '7 days');
-- SELECT add_compression_policy('features', INTERVAL '7 days');
-- SELECT add_compression_policy('htf_bias_history', INTERVAL '7 days');

-- Retention policy - drop data older than 1 year (optional)
-- Uncomment if storage is a concern
-- SELECT add_retention_policy('candles', INTERVAL '1 year');
-- SELECT add_retention_policy('features', INTERVAL '1 year');
-- SELECT add_retention_policy('htf_bias_history', INTERVAL '1 year');

-- ============================================================================
-- STATISTICS
-- ============================================================================
-- Update statistics for query planner
ANALYZE candles;
ANALYZE features;
ANALYZE htf_bias_history;
ANALYZE trades;
ANALYZE state_machine_snapshots;
ANALYZE daily_state;

