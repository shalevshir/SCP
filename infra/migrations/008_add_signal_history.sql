-- Migration 008: Signal History Table
-- Comprehensive signal audit trail for all generated signals (approved and rejected)
-- Enables post-hoc analysis, debugging, and rejection pattern discovery

-- ============================================================================
-- SIGNAL HISTORY TABLE
-- ============================================================================
-- Stores ALL signals with full diagnostic context for complete transparency
CREATE TABLE IF NOT EXISTS signal_history (
    id UUID DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    timeframe VARCHAR(5) NOT NULL,
    
    -- Signal outcome
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('long', 'short', 'neutral')),
    setup_type VARCHAR(30) NOT NULL,
    score NUMERIC(4,2) NOT NULL CHECK (score >= 0 AND score <= 10),
    confidence VARCHAR(10) NOT NULL CHECK (confidence IN ('A+', 'A', 'B', 'C', 'Watch', 'Reject')),
    was_approved BOOLEAN NOT NULL,  -- TRUE if A+ signal published to execution service
    rejection_stage VARCHAR(30),    -- e.g., "htf_validity", "confidence_filter", "session_filter", "neutral_direction", "tp_validation"
    
    -- Full context snapshots (JSONB for flexibility and queryability)
    features_snapshot JSONB NOT NULL,    -- Complete FeaturesMessage for exact reproducibility
    htf_bias_snapshot JSONB NOT NULL,    -- Complete HTFBiasMessage for exact reproducibility
    
    -- Scoring breakdown
    factor_scores JSONB NOT NULL,        -- All factor scores from scoring (structure_alignment, vwap_relation, etc.)
    diagnostics JSONB NOT NULL,          -- Full build_diagnostics() output including rejection_analysis
    
    -- Execution linkage (NULL if rejected or not executed)
    signal_message_id UUID,              -- Links to published SignalMessage ID (if approved)
    trade_id UUID REFERENCES trades(id), -- Links to resulting trade (if executed)
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Composite primary key including timestamp for hypertable compatibility
    PRIMARY KEY (timestamp, id)
);

-- Convert to hypertable for efficient time-range queries
SELECT create_hypertable('signal_history', 'timestamp', if_not_exists => TRUE);

-- ============================================================================
-- INDEXES
-- ============================================================================
-- Query performance for common analysis patterns

-- Index on id for lookups after insertion (id is part of composite PK)
CREATE INDEX idx_signal_history_id ON signal_history(id);

-- Filter by approval status (approved vs rejected signals)
CREATE INDEX idx_signal_history_approved ON signal_history(was_approved);

-- Filter by setup type (analyze specific setups)
CREATE INDEX idx_signal_history_setup ON signal_history(setup_type);

-- Filter by confidence (find near-miss signals)
CREATE INDEX idx_signal_history_confidence ON signal_history(confidence);

-- Filter by rejection stage (analyze rejection patterns)
CREATE INDEX idx_signal_history_rejection_stage ON signal_history(rejection_stage) WHERE rejection_stage IS NOT NULL;

-- Composite index for common query pattern: rejected signals by setup type
CREATE INDEX idx_signal_history_rejected_setup ON signal_history(setup_type, was_approved) WHERE was_approved = FALSE;

-- GIN index for JSONB queries on diagnostics (e.g., rejection_analysis)
CREATE INDEX idx_signal_history_diagnostics_gin ON signal_history USING gin(diagnostics jsonb_path_ops);

-- GIN index for features snapshot queries (e.g., filter by RSI range)
CREATE INDEX idx_signal_history_features_gin ON signal_history USING gin(features_snapshot jsonb_path_ops);
