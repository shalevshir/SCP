---
name: Backtest Tab Integration
overview: Add a backtest tab to the existing live trading dashboard with sub-tabs (Run | Results | Analysis), allowing users to run backtests, view results, and interact with them all within the same dashboard interface.
todos:
  - id: backtest-state
    content: Create BacktestState class for managing backtest results and configuration
    status: pending
  - id: run-tab
    content: Create run_tab.py with backtest configuration controls and run button
    status: pending
    dependencies:
      - backtest-state
  - id: results-tab
    content: Create results_tab.py reusing existing metrics, equity chart, and trade table components
    status: pending
    dependencies:
      - backtest-state
  - id: analysis-tab
    content: Create analysis_tab.py reusing price chart and scoring breakdown components
    status: pending
    dependencies:
      - backtest-state
  - id: modify-dashboard
    content: Modify dashboard/app.py to add tab navigation and integrate backtest tabs
    status: pending
    dependencies:
      - run-tab
      - results-tab
      - analysis-tab
  - id: add-callbacks
    content: Add Dash callbacks for running backtests, updating views, and tab switching
    status: pending
    dependencies:
      - modify-dashboard
  - id: test-integration
    content: "Test complete workflow: configure → run → view results → analyze trades"
    status: pending
---

# Backtest Tab Integration into Live Dashboard

## Overview

Integrate backtesting functionality into the existing live trading dashboard by adding a tabbed interface. Users can run backtests, view results, and analyze them without leaving the dashboard.

## Architecture

### Tab Structure

- **Main Tabs**: "Live Trading" | "Backtest"
- **Backtest Sub-tabs**: "Run" | "Results" | "Analysis"

### Components to Create/Modify

1. **Main Dashboard Layout** (`dashboard/app.py`)

   - Add tab navigation (Live Trading | Backtest)
   - Keep existing live trading view in first tab
   - Add backtest tab with sub-tabs

2. **Backtest Run Tab** (`dashboard/components/backtest/run_tab.py`)

   - Date range picker (start/end dates)
   - Auto-detect checkbox (uses all available data)
   - Buffer phase selector (startup/growth/scaling/institutional)
   - Tier active selector (Conservative/EarlyMild/Mild/Offensive)
   - Run backtest button
   - Progress indicator during execution
   - Status messages

3. **Backtest Results Tab** (`dashboard/components/backtest/results_tab.py`)

   - Reuse existing metrics panel component
   - Reuse equity chart component
   - Reuse trade table component
   - Display results from most recent backtest run

4. **Backtest Analysis Tab** (`dashboard/components/backtest/analysis_tab.py`)

   - Reuse price chart with markers component
   - Reuse scoring breakdown component
   - Interactive trade selection and analysis

5. **Backtest State Management** (`dashboard/core/backtest_state.py`)

   - Store current backtest results
   - Store backtest configuration
   - Handle loading/saving results

## Implementation Details

### 1. Modify Main Dashboard (`dashboard/app.py`)

**Changes:**

- Convert layout to use `dbc.Tabs` for main navigation
- Keep existing live trading components in "Live Trading" tab
- Add "Backtest" tab with `dbc.Tabs` for sub-navigation
- Register callbacks for backtest tab interactions

**Layout Structure:**

```python
dbc.Tabs([
    dbc.Tab(label="Live Trading", tab_id="live-tab", children=[...existing layout...]),
    dbc.Tab(label="Backtest", tab_id="backtest-tab", children=[
        dbc.Tabs([
            dbc.Tab(label="Run", tab_id="backtest-run", children=[...run controls...]),
            dbc.Tab(label="Results", tab_id="backtest-results", children=[...results view...]),
            dbc.Tab(label="Analysis", tab_id="backtest-analysis", children=[...analysis view...]),
        ])
    ])
])
```

### 2. Create Backtest Run Tab (`dashboard/components/backtest/run_tab.py`)

**Components:**

- Date range inputs (start/end datetime pickers)
- Auto-detect checkbox (when checked, disables date inputs)
- Buffer phase dropdown
- Tier active dropdown
- Run button
- Progress bar/indicator
- Status message area
- Results summary card (after completion)

**Functionality:**

- Validate inputs before running
- Show progress during blocking execution
- Display completion status and quick metrics
- Store results in dashboard state for Results/Analysis tabs

### 3. Create Backtest Results Tab (`dashboard/components/backtest/results_tab.py`)

**Components:**

- Reuse `render_metrics_panel()` from existing component
- Reuse `render_equity_chart()` from existing component
- Reuse `render_trade_table()` from existing component
- Add "Load Results" button to load from saved JSON file
- Add "Export Results" button to save current results

**Layout:**

- Metrics panel at top
- Equity chart in middle
- Trade table at bottom (scrollable)

### 4. Create Backtest Analysis Tab (`dashboard/components/backtest/analysis_tab.py`)

**Components:**

- Reuse `render_price_chart_with_markers()` from existing component
- Reuse `render_scoring_breakdown()` from existing component
- Trade selector dropdown
- Trade details panel

**Layout:**

- Left: Price chart with markers
- Right: Scoring breakdown
- Bottom: Trade details (when trade selected)

### 5. Create Backtest State Manager (`dashboard/core/backtest_state.py`)

**Purpose:**

- Store current backtest results
- Store backtest configuration
- Provide getters/setters for components

**Interface:**

```python
class BacktestState:
    results: BacktestResults | None
    config: dict | None
    is_running: bool
    progress: float
    
    def set_results(results: BacktestResults)
    def get_results() -> BacktestResults | None
    def clear_results()
```

### 6. Update Dashboard App (`dashboard/app.py`)

**Modifications:**

- Import backtest components
- Add BacktestState instance
- Modify `_build_layout()` to include tabs
- Add callbacks for:
  - Tab switching
  - Running backtest (blocking with progress)
  - Updating results/analysis views
  - Loading/saving results

## Execution Flow

1. **User navigates to Backtest → Run tab**
2. **User configures backtest:**

   - Selects date range OR checks auto-detect
   - Selects buffer phase
   - Selects tier active

3. **User clicks "Run Backtest"**
4. **Dashboard shows progress indicator**
5. **Backtest runs (blocking):**

   - Loads data
   - Runs BacktestReplayLoop
   - Saves results to state

6. **Results displayed:**

   - Quick summary in Run tab
   - Full results in Results tab
   - Analysis tools in Analysis tab

7. **User can switch tabs to explore results**

## File Changes Summary

**New Files:**

- `dashboard/components/backtest/run_tab.py` - Run backtest controls
- `dashboard/components/backtest/results_tab.py` - Results display
- `dashboard/components/backtest/analysis_tab.py` - Analysis tools
- `dashboard/core/backtest_state.py` - State management

**Modified Files:**

- `dashboard/app.py` - Add tabs, integrate backtest functionality
- `dashboard/components/backtest/__init__.py` - Export new components

## Benefits

- Unified interface: Live trading and backtesting in one place
- Seamless workflow: Run backtest → View results → Analyze trades
- Reuses existing components: No duplication of viewer code
- Consistent UI: Same design language as live dashboard