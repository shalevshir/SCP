-- Migration: Add rolling VWAP acceptance tracking field
-- This field counts bars near VWAP in the last 20 bars (rolling window)
-- More useful than consecutive streak for detecting acceptance zones

ALTER TABLE features ADD COLUMN IF NOT EXISTS near_vwap_count_last_20 INTEGER;

-- Add comment for documentation
COMMENT ON COLUMN features.near_vwap_count_last_20 IS 'Count of bars within VWAP proximity (±0.5 ATR) in last 20 bars; NULL when ATR unavailable';
