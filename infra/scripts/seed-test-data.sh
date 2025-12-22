#!/bin/bash
# SCP Trading Bot - Test Data Seeding Script
# Seeds the database with sample data for testing

set -e

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-scp}"
DB_USER="${DB_USER:-scp}"

echo "==================================="
echo "Seeding Test Data"
echo "==================================="

# Wait for database to be ready
echo "Waiting for database..."
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; do
  echo "Database is unavailable - sleeping"
  sleep 1
done

echo "Database is ready!"

# Seed sample data
echo "Inserting sample candles..."
PGPASSWORD=$POSTGRES_PASSWORD psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<-EOSQL
    -- Insert sample 1m candles for GC
    INSERT INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume) VALUES
    ('2025-01-15 10:00:00+00', 'GC', '1m', 2650.0, 2652.0, 2649.0, 2651.0, 1000),
    ('2025-01-15 10:01:00+00', 'GC', '1m', 2651.0, 2653.0, 2650.0, 2652.0, 1100),
    ('2025-01-15 10:02:00+00', 'GC', '1m', 2652.0, 2654.0, 2651.0, 2653.0, 1200);

    -- Insert sample 1m candles for DXY
    INSERT INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume) VALUES
    ('2025-01-15 10:00:00+00', 'DXY', '1m', 104.5, 104.6, 104.4, 104.55, 0),
    ('2025-01-15 10:01:00+00', 'DXY', '1m', 104.55, 104.65, 104.5, 104.6, 0),
    ('2025-01-15 10:02:00+00', 'DXY', '1m', 104.6, 104.7, 104.55, 104.65, 0);

    -- Insert sample daily state
    INSERT INTO daily_state (date, loss_streak, daily_loss, trades_count, wins, losses, pdll_hits) VALUES
    ('2025-01-15', 0, 0.0, 0, 0, 0, 0);

    -- Insert sample HTF bias
    INSERT INTO htf_bias_history (timestamp, bias, score, confidence, structure_15m, structure_1h, dxy_aligned, chop_detected) VALUES
    ('2025-01-15 10:00:00+00', 'bullish', 8.5, 'A+', 'HH', 'bullish', true, false);
EOSQL

echo "✓ Test data seeding complete!"
echo "==================================="

