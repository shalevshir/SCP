-- Migration: Add VWAP deviation history tracking fields
-- Created: 2026-02-02
-- Description: Adds max/min deviation lookback for VWAP_RECLAIM excursion detection
--
-- Background: The vwap_reclaim_distance constraint requires price to have been
-- stretched away from VWAP (0.5+ ATR) before reclaiming it. Previously, this
-- constraint checked the current bar's distance, which conflicts with the
-- min_vwap_acceptance constraint (requires 3+ bars near VWAP).
--
-- This migration adds historical tracking of max/min deviation over the last 20
-- bars, allowing the system to detect prior excursion even when price is currently
-- consolidating near VWAP.

BEGIN;

-- Add max_abs_deviation_last_20 (highest deviation in last 20 bars)
ALTER TABLE features
ADD COLUMN IF NOT EXISTS max_abs_deviation_last_20 NUMERIC(8,4);

COMMENT ON COLUMN features.max_abs_deviation_last_20 IS
    'Maximum absolute VWAP deviation (ATR-normalized) in last 20 bars; NULL when ATR unavailable';

-- Add min_abs_deviation_last_20 (lowest deviation in last 20 bars)
ALTER TABLE features
ADD COLUMN IF NOT EXISTS min_abs_deviation_last_20 NUMERIC(8,4);

COMMENT ON COLUMN features.min_abs_deviation_last_20 IS
    'Minimum absolute VWAP deviation (ATR-normalized) in last 20 bars; NULL when ATR unavailable';

-- Create index for constraint validation queries
-- Bot-core frequently queries max_abs_deviation_last_20 when validating VWAP_RECLAIM setups
CREATE INDEX IF NOT EXISTS idx_features_max_deviation
    ON features(symbol, timestamp, max_abs_deviation_last_20)
    WHERE max_abs_deviation_last_20 IS NOT NULL;

COMMIT;
