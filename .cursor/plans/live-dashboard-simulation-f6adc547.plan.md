<!-- f6adc547-71ce-4257-930e-7b008bb78db1 ca1e555e-6360-497c-9259-a1a189d7862f -->
# Live Dashboard with Historical Data Simulation

## Goal

Transform the batch-oriented backtesting system into a streaming architecture and build a Plotly Dash dashboard that simulates live trading conditions by processing historical data incrementally.

## Architecture Principle: Zero Code Duplication

**Critical**: The streaming implementation will **reuse existing calculation functions** from [`feature_engine/`](feature_engine/) to guarantee identical results between backtest and live modes. No indicator logic will be duplicated.

Current system: **Vectorized/Batch** ([`BacktestProcessor`](feature_engine/backtesting.py) uses [`aggregate_features()`](feature_engine/aggregator.py))

Target system: **Streaming/Incremental** (thin state wrappers + same calculation functions)

## Implementation Steps

### 1. Create Streaming Feature Processor (Function Reuse Architecture)

**New file**: `feature_engine/streaming.py`

Create `StreamingFeatureProcessor` that maintains state and **calls existing functions**:

**Strategy per indicator**:

1. **EMA** (incremental formula from [`calculate_ema()`](feature_engine/ema.py)):

   - Extract formula: `EMA = price × α + EMA_prev × (1-α)` where `α = 2/(period+1)`
   - Maintain state for each period (9, 20, 50)
   - Update incrementally per bar

2. **VWAP** (cumulative, session-aware per [`calculate_vwap()`](feature_engine/vwap.py)):

   - Maintain `pv_sum` and `v_sum` state
   - Reset at session boundary (08:20 ET)
   - Compute: `vwap = pv_sum / v_sum`

3. **RSI** (window-based, calls existing function):

   - Maintain 14-bar deque buffer
   - On update: convert buffer to DataFrame, call `calculate_rsi(df, period=14)`
   - Extract last value from result

4. **DXY Correlation** (window-based, calls existing function):

   - Maintain 50-bar deque buffers for GC and DXY
   - On update: convert to DataFrames, call `calculate_dxy_correlation(gc_df, dxy_df, window=50)`
   - Extract last value

5. **Structure Labels** (lookback-based, calls existing function):

   - Maintain swing window buffer (5 bars + lookback)
   - On update: convert to DataFrame, call `calculate_structure_labels(df, swing_window=5)`
   - Handle delayed labels correctly

6. **VWAP Deviation** (calls existing function):

   - After computing VWAP and close, call `calculate_vwap_deviation()`

**Class signature**:

```python
class StreamingFeatureProcessor:
    def __init__(self, timeframe: str, ...):
        # Initialize buffers and state
        self.ema_states = {9: None, 20: None, 50: None}
        self.rsi_buffer = deque(maxlen=14)
        self.dxy_corr_gc_buffer = deque(maxlen=50)
        self.dxy_corr_dxy_buffer = deque(maxlen=50)
        self.structure_buffer = deque(maxlen=20)  # Extra for lookback
        self.vwap_pv_sum = 0.0
        self.vwap_v_sum = 0.0
        
    def update(self, gc_bar: Candle, dxy_bar: Candle) -> pd.Series:
        # Update buffers, call existing functions, return features
        pass
```

### 2. Create Streaming HTF Bias Calculator

**New file**: `rule_engine/htf/streaming.py`

Build `StreamingHTFBiasCalculator` that:

- Maintains separate `StreamingFeatureProcessor` instances for 1H and 15M
- Detects bar boundaries (when 1M bar aligns with 15M or 1H close)
- Calls existing [`compute_htf_bias()`](rule_engine/htf/calculator.py) with current HTF features
- Returns `HTFBias` object

### 3. Build Simulation Harness

**New file**: `dashboard/simulation.py`

Create `HistoricalStreamSimulator`:

- Uses [`HistoricalDataLoader`](data_layer/loader.py) to load data
- Yields `(gc_bar, dxy_bar)` tuples one at a time
- Configurable delay (e.g., 0.1s = 10x speed)
- Handles timestamp alignment

### 4. Create Dashboard State Manager

**New file**: `dashboard/state.py`

`DashboardState` dataclass holding:

- Current features (pd.Series)
- Current HTF bias (HTFBias)
- Current signal (Signal | None)
- Current session constraints (SessionConstraints)
- Historical buffer for charting (deque of last 100 bars)

### 5. Build Plotly Dash Dashboard

**New file**: `dashboard/app.py`

Multi-panel dashboard with:

- **Indicators Panel**: Display VWAP, RSI, EMAs, DXY corr, structure
- **HTF Panel**: 1H/15M bias, overall direction
- **Constraints Panel**: Session status, allowed tiers/setups, min score
- **Signal Panel**: Direction, score, confidence, setup type
- **Price Chart**: Candlestick + VWAP overlay (Plotly)
- **Controls**: Play/pause, speed slider, timestamp

Use `dcc.Interval` for periodic state polling.

### 6. Create Dashboard Pipeline Orchestrator

**New file**: `dashboard/pipeline.py`

`LiveSimulationPipeline` that:

- Initializes streaming processor, HTF calculator, simulator
- Main loop: fetch bar → update features → compute HTF → score signal → update state
- Integrates [`ValidationEngine`](validation/engine.py) and [`score_signal()`](rule_engine/scoring.py)
- Thread-safe state updates

### 7. Create Dashboard Entry Point

**New file**: `scripts/run_dashboard.py`

CLI to launch dashboard:

```python
# Parse args (data path, timeframe, speed)
# Initialize pipeline
# Start Dash server
# Run simulation in background thread
```

### 8. Add Dashboard Dependencies

Update `pyproject.toml`:

- Add: `dash`, `dash-bootstrap-components`
- Verify: `plotly` already present

### 9. Write Validation Tests (Critical for Correctness)

**New test files**:

1. `tests/unit/feature_engine/test_streaming.py`:

   - Test each indicator: streaming result == vectorized result
   - Compare `StreamingFeatureProcessor.update()` against `BacktestProcessor._compute_features()`
   - Test session resets, warm-up period

2. `tests/unit/dashboard/test_simulation.py`:

   - Test simulator yields correct bars
   - Test timestamp alignment

3. `tests/unit/dashboard/test_pipeline.py`:

   - Test full pipeline produces same signals as backtesting

**Test strategy**: Run both streaming and batch on same historical data, assert identical results.

### 10. Documentation

**New file**: `docs/dashboard/README.md`

Document:

- Architecture (streaming = state + existing functions)
- Running the dashboard
- Interpreting panels
- Future: live data transition

## Code Reuse Summary

**No duplication** - streaming wraps existing functions:

- [`calculate_vwap()`](feature_engine/vwap.py) - formula extracted for incremental use
- [`calculate_ema()`](feature_engine/ema.py) - formula extracted for incremental use
- [`calculate_rsi()`](feature_engine/rsi.py) - **called directly** with buffer
- [`calculate_dxy_correlation()`](feature_engine/dxy_correlation.py) - **called directly** with buffer
- [`calculate_structure_labels()`](feature_engine/structure.py) - **called directly** with buffer
- [`calculate_vwap_deviation()`](feature_engine/vwap.py) - **called directly**

## Success Criteria

1. Streaming indicators **exactly match** backtesting indicators (validated by tests)
2. Dashboard displays all panels correctly
3. HTF bias updates at correct boundaries
4. Signals match what backtesting would generate
5. Play/pause controls work
6. Performance: handles 1 bar/second smoothly

## Future Extensions (Not in This Plan)

- Live data provider integration
- Trade execution interface
- Alert system
- Historical replay with scrubbing