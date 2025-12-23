-- Add trade state fields for service restart recovery
-- These fields enable correct SOP validation across restarts

-- Add entry_bar_idx to track when trade was opened (for bars_elapsed calculation)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'entry_bar_idx') THEN
        ALTER TABLE trades ADD COLUMN entry_bar_idx INTEGER;
    END IF;
END $$;

-- Add reached_1r to track if trade achieved +1R protection
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'reached_1r') THEN
        ALTER TABLE trades ADD COLUMN reached_1r BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Add comments for documentation
COMMENT ON COLUMN trades.entry_bar_idx IS 'Bar index when trade was entered (for calculating bars_elapsed)';
COMMENT ON COLUMN trades.reached_1r IS 'Whether trade has reached +1R (grants protection from time-based invalidation)';

-- Create index for querying trades by entry_bar_idx (useful for debugging)
CREATE INDEX IF NOT EXISTS idx_trades_entry_bar_idx ON trades(entry_bar_idx) WHERE entry_bar_idx IS NOT NULL;


