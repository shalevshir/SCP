# Scripts Directory

This directory contains utility scripts for data fetching, analysis, and system maintenance.

## Available Scripts

### `fetch_gc_dx_ohlcv_to_csv.py` - Fetch Historical Data

Fetches historical OHLCV (Open, High, Low, Close, Volume) data for Gold futures (GC) and DXY index from Databento and saves to CSV files.

**Requirements:**
- Databento API key
- Internet connection

**Usage:**

```bash
# Set your Databento API key
export DATABENTO_API_KEY="your-databento-api-key"

# Run the script
python scripts/fetch_gc_dx_ohlcv_to_csv.py
```

**Features:**
- Fetches data for Gold (GC) and DXY index
- Multiple timeframes: 1-second, 1-minute, 1-hour (Databento doesn't offer 15-minute bars)
- Defaults to last 7 days of data
- Saves to `data/gc_dx_ohlcv/` directory
- Full error handling and logging
- Progress tracking
- Automatic handling of data availability delay (4-hour buffer)

**Data Sources:**
- Gold (GC): CME Globex (`GLBX.MDP3`)
- DXY: ICE Futures US (`IFUS.IMPACT`)

**Output Files:**
- `GC_ohlcv-1s.csv` - Gold 1-second bars
- `GC_ohlcv-1m.csv` - Gold 1-minute bars
- `GC_ohlcv-1h.csv` - Gold 1-hour bars
- `DX_ohlcv-1s.csv` - DXY 1-second bars
- `DX_ohlcv-1m.csv` - DXY 1-minute bars
- `DX_ohlcv-1h.csv` - DXY 1-hour bars

**Note:** Databento does not offer 15-minute OHLCV bars. Available timeframes are: 1s, 1m, 1h, 1d, and end-of-day.

---

### `resample_ohlcv_to_15m.py` - Create 15-Minute Bars

Resamples 1-minute OHLCV data to 15-minute bars using proper aggregation rules.

**Requirements:**
- 1-minute CSV files (from `fetch_gc_dx_ohlcv_to_csv.py`)

**Usage:**

```bash
# Run after fetching 1-minute data
python scripts/resample_ohlcv_to_15m.py
```

**Features:**
- Automatically finds all `*_ohlcv-1m.csv` files
- Applies proper OHLCV aggregation:
  - `open`: first value in 15-min period
  - `high`: maximum value
  - `low`: minimum value
  - `close`: last value
  - `volume`: sum of volume
- Drops periods with no data (NaN handling)
- Full error handling and logging

**Output Files:**
- `GC_ohlcv-15m.csv` - Gold 15-minute bars
- `DX_ohlcv-15m.csv` - DXY 15-minute bars

**Customization:**

You can modify the resampling frequency in the script:
```python
# In resample_ohlcv_to_15m.py
RESAMPLE_FREQUENCY = "15min"  # Change to "5min", "30min", "1H", etc.
```

Supported frequencies: `5min`, `15min`, `30min`, `1H`, `4H`, `1D` - any pandas frequency string.

---

## Data Management

### Committed Data

To keep the repository size manageable, **only 1-minute OHLCV files are committed**:
- `data/gc_dx_ohlcv/GC_ohlcv-1m.csv` (~2.0 MB)
- `data/gc_dx_ohlcv/DX_ohlcv-1m.csv` (~428 KB)

These files are sufficient for running tests and serve as the base for generating other timeframes.

### Excluded Data (Regenerate as Needed)

The following files are **excluded from git** (see `.gitignore`) to avoid repo bloat:
- `*-1s.csv` files (1-second data, ~18 MB total)
- `*-15m.csv` files (15-minute data)
- `*-1h.csv` files (1-hour data)

### Regenerating Excluded Timeframes

If you need other timeframes, regenerate them locally:

**Option 1: Fetch from Databento (requires API key)**
```bash
export DATABENTO_API_KEY="your-key"
python scripts/fetch_gc_dx_ohlcv_to_csv.py
```

**Option 2: Resample from 1-minute data (no API key needed)**
```bash
# Generate 15-minute bars from committed 1m data
python scripts/resample_ohlcv_to_15m.py

# For other timeframes, modify the RESAMPLE_FREQUENCY in the script
```

This approach keeps the repo lean while maintaining test data availability.

---

## Environment Variables

**For `fetch_gc_dx_ohlcv_to_csv.py`:**
- `DATABENTO_API_KEY` (required): Your Databento API key
- `DATABENTO_FREE_TIER` (optional): Set to "true" to fetch older data (free tier compatible)
- `SCP_LOG_LEVEL` (optional): Override logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

**For `resample_ohlcv_to_15m.py`:**
- `SCP_LOG_LEVEL` (optional): Override logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

**Important Notes:**

- **Subscription Requirements**: 
  - Recent data (last ~30 days) requires a **paid Databento subscription** + **CME market data license**
  - Free tier users can access historical data older than ~30 days
  - See: https://databento.com/pricing#cme
  
- **Free Tier Usage**:
  ```bash
  export DATABENTO_FREE_TIER="true"
  python scripts/fetch_gc_dx_ohlcv_to_csv.py
  ```
  This will fetch data from ~60 days ago (no subscription required)

- **Data Availability Delay**: Historical market data typically has a 2-4 hour delay. The script automatically requests data ending 4 hours ago to avoid availability errors.
- **Time Range**: By default, fetches the last 7 days of data (ending 4 hours ago, or from 60 days ago if using free tier)

**Troubleshooting:**

If you encounter authentication errors:
```bash
# Verify your API key is set
echo $DATABENTO_API_KEY
```

If you encounter import errors:
```bash
# Ensure you're running from project root
cd /path/to/SCP
python scripts/fetch_gc_dx_ohlcv_to_csv.py
```

If you see `data_end_after_available_end` errors:
- This means the requested end time is after available data
- The script now handles this automatically with a 4-hour buffer
- If the error persists, data availability may be delayed further (market holidays, weekends, etc.)

If you see `dataset_unavailable_range` or subscription errors:
- You're trying to access recent data that requires a paid subscription
- **Solution**: Use free tier mode to fetch older historical data:
  ```bash
  export DATABENTO_FREE_TIER="true"
  python scripts/fetch_gc_dx_ohlcv_to_csv.py
  ```
- **Or**: Upgrade to a paid Databento subscription at https://databento.com/pricing

## Security Note

⚠️ **Never commit API keys or secrets to the repository.** Always use environment variables for sensitive credentials.

