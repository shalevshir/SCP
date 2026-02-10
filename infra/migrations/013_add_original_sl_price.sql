-- Migration: Add original_sl_price column to trades table
-- Purpose: Preserve original stop loss for R-multiple calculation
--
-- Problem: update_breakeven() overwrites sl_price with BE price,
-- corrupting R-multiple calculations when trades close.
--
-- Solution: Add original_sl_price that never changes after trade creation.

DO $$
BEGIN
    -- Add original_sl_price column if it doesn't exist
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'trades'
        AND column_name = 'original_sl_price'
    ) THEN
        -- Add column as nullable first
        ALTER TABLE trades ADD COLUMN original_sl_price NUMERIC(12,4);

        -- Backfill existing trades: copy sl_price to original_sl_price
        -- For trades that already have BE set, this will copy the BE price,
        -- but that's acceptable since we can't recover the original SL.
        -- New trades will have both columns set correctly.
        UPDATE trades
        SET original_sl_price = sl_price
        WHERE original_sl_price IS NULL;

        -- Make it NOT NULL after backfill
        ALTER TABLE trades ALTER COLUMN original_sl_price SET NOT NULL;

        RAISE NOTICE 'Added original_sl_price column to trades table';
    ELSE
        RAISE NOTICE 'original_sl_price column already exists, skipping';
    END IF;
END $$;

-- Add comments for clarity
COMMENT ON COLUMN trades.original_sl_price IS
    'Original stop loss price (never changes after creation) - used for R-multiple calculation';

COMMENT ON COLUMN trades.sl_price IS
    'Current stop loss price (may change to breakeven) - used for trade management';
