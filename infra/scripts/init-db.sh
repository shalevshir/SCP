#!/bin/bash
# SCP Trading Bot - Database Initialization Script
# This script is automatically run by Docker when the postgres container starts for the first time

set -e

echo "==================================="
echo "SCP Database Initialization"
echo "==================================="

# Check if TimescaleDB extension is available
echo "Verifying TimescaleDB extension..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';
EOSQL

echo "✓ Database initialization complete!"
echo "  Database: $POSTGRES_DB"
echo "  User: $POSTGRES_USER"
echo "==================================="

