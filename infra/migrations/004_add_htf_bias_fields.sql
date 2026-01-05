-- ============================================================================
-- MIGRATION 004: Add seasonality and VWAP fields to htf_bias_history
-- ============================================================================
-- These fields were added to HTFBiasMessage for scoring bonuses and parity
-- with the backtester.
--
-- Fields:
--   seasonality_adjustment: Score adjustment based on seasonality (+/- points)
--   seasonality_period: Current seasonality period name (e.g., "november_december")
--   vwap_trend_confirmed: Whether VWAP trend is confirmed
-- ============================================================================

-- Add seasonality adjustment field (score modifier)
ALTER TABLE htf_bias_history 
ADD COLUMN IF NOT EXISTS seasonality_adjustment NUMERIC(5,2) DEFAULT 0.0;

-- Add seasonality period name
ALTER TABLE htf_bias_history 
ADD COLUMN IF NOT EXISTS seasonality_period VARCHAR(50) DEFAULT NULL;

-- Add VWAP trend confirmation flag
ALTER TABLE htf_bias_history 
ADD COLUMN IF NOT EXISTS vwap_trend_confirmed BOOLEAN DEFAULT FALSE;

-- Add comments
COMMENT ON COLUMN htf_bias_history.seasonality_adjustment IS 'Score adjustment based on seasonality patterns';
COMMENT ON COLUMN htf_bias_history.seasonality_period IS 'Current seasonality period (e.g., november_december)';
COMMENT ON COLUMN htf_bias_history.vwap_trend_confirmed IS 'Whether VWAP trend is confirmed';

