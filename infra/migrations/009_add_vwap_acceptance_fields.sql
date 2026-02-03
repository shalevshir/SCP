-- Migration: Add VWAP acceptance tracking fields to features table
-- Created: 2026-02-02
-- Description: Adds bars_near_vwap and bars_since_last_vwap_touch columns for
--              VWAP_RECLAIM min_vwap_acceptance and reclaim_timing_gate constraints

BEGIN;

-- Add bars_near_vwap column (consecutive bars within ±0.2 ATR of VWAP)
ALTER TABLE features
ADD COLUMN IF NOT EXISTS bars_near_vwap INTEGER;

COMMENT ON COLUMN features.bars_near_vwap IS
    'Consecutive bars within VWAP proximity band (±0.2 ATR); NULL when ATR unavailable';

-- Add bars_since_last_vwap_touch column (bars since last VWAP interaction)
ALTER TABLE features
ADD COLUMN IF NOT EXISTS bars_since_last_vwap_touch INTEGER;

COMMENT ON COLUMN features.bars_since_last_vwap_touch IS
    'Bars since last VWAP touch/interaction; NULL when no touch has occurred';

-- Create index for constraint validation queries
-- Bot-core queries these fields frequently when validating VWAP_RECLAIM setups
CREATE INDEX IF NOT EXISTS idx_features_vwap_acceptance
    ON features(symbol, timestamp, bars_near_vwap, bars_since_last_vwap_touch)
    WHERE bars_near_vwap IS NOT NULL;

COMMIT;
