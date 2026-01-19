-- Add vwap_slope to features table for DXY participation context
-- Migration: 007_add_vwap_slope

ALTER TABLE features
ADD COLUMN IF NOT EXISTS vwap_slope NUMERIC(12,8);

-- Add index for DXY vwap_slope dashboard queries
CREATE INDEX IF NOT EXISTS idx_features_vwap_slope
ON features(timestamp, symbol, vwap_slope)
WHERE symbol = 'DXY' AND vwap_slope IS NOT NULL;

COMMENT ON COLUMN features.vwap_slope IS 'VWAP slope (first derivative) - indicates intent and participation strength';
