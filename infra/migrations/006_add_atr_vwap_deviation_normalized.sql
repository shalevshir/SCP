-- Add ATR and Normalized VWAP Deviation fields to features table
-- Migration: 006_add_atr_vwap_deviation_normalized

ALTER TABLE features 
ADD COLUMN IF NOT EXISTS atr NUMERIC(12,4),
ADD COLUMN IF NOT EXISTS vwap_deviation_normalized NUMERIC(8,4);

-- Add indexes for querying
CREATE INDEX IF NOT EXISTS idx_features_vwap_deviation_normalized 
ON features(timestamp, symbol, timeframe, vwap_deviation_normalized)
WHERE vwap_deviation_normalized IS NOT NULL;

COMMENT ON COLUMN features.atr IS 'Average True Range (14-period) - volatility measure';
COMMENT ON COLUMN features.vwap_deviation_normalized IS 'Normalized VWAP deviation: (Price - VWAP) / ATR - dimensionless, regime-aware deviation metric';
