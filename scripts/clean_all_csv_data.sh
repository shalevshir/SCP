#!/usr/bin/env bash
#
# Convenience script to clean all CSV data files for GC and DX instruments.
#
# This script processes raw OHLCV data to:
# 1. Remove spread instruments
# 2. Filter only GC or DX instruments
# 3. Select highest volume contract per minute
# 4. Remove duplicate timestamps
#
# Usage:
#   ./scripts/clean_all_csv_data.sh

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Shir Capital CSV Data Cleaner ==="
echo ""

# Process Gold (GC) data
if [ -f "$PROJECT_ROOT/data/gc_dx_ohlcv/glbx_ohlcv_1m.csv" ]; then
    echo "Processing Gold (GC) data..."
    poetry run python "$SCRIPT_DIR/clean_csv_data.py" \
        --input "$PROJECT_ROOT/data/gc_dx_ohlcv/glbx_ohlcv_1m.csv" \
        --output "$PROJECT_ROOT/data/gc_dx_ohlcv/GC_ohlcv-1m.csv" \
        --prefix GC
    echo "✓ Gold (GC) data cleaned successfully"
    echo ""
else
    echo "⚠ Warning: glbx_ohlcv_1m.csv not found, skipping GC processing"
    echo ""
fi

# Process Dollar Index (DX) data
if [ -f "$PROJECT_ROOT/data/gc_dx_ohlcv/dxy_ohlcv_1m.csv" ]; then
    echo "Processing Dollar Index (DX) data..."
    poetry run python "$SCRIPT_DIR/clean_csv_data.py" \
        --input "$PROJECT_ROOT/data/gc_dx_ohlcv/dxy_ohlcv_1m.csv.csv" \
        --output "$PROJECT_ROOT/data/gc_dx_ohlcv/DX_ohlcv-1m.csv" \
        --prefix DX
    echo "✓ Dollar Index (DX) data cleaned successfully"
    echo ""
else
    echo "⚠ Warning: dxy_ohlcv_1m.csv.csv not found, skipping DX processing"
    echo ""
fi

# Also check for alternative DX filename (without double .csv)
if [ -f "$PROJECT_ROOT/data/gc_dx_ohlcv/dxy_ohlcv_1m.csv" ]; then
    echo "Processing Dollar Index (DX) data (alternative filename)..."
    poetry run python "$SCRIPT_DIR/clean_csv_data.py" \
        --input "$PROJECT_ROOT/data/gc_dx_ohlcv/dxy_ohlcv_1m.csv" \
        --output "$PROJECT_ROOT/data/gc_dx_ohlcv/DX_ohlcv-1m.csv" \
        --prefix DX
    echo "✓ Dollar Index (DX) data cleaned successfully"
    echo ""
fi

echo "=== Data cleaning complete ==="
echo ""
echo "Output files:"
echo "  - $PROJECT_ROOT/data/gc_dx_ohlcv/GC_ohlcv-1m.csv"
echo "  - $PROJECT_ROOT/data/gc_dx_ohlcv/DX_ohlcv-1m.csv"


