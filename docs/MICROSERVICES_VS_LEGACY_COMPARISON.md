# Comparison Document: Microservices Architecture vs. Legacy Backtester

This document provides a comprehensive comparison between the new distributed microservice implementation (under `services/`) and the legacy monolithic implementation in `backtester/replay_loop.py`. It identifies logical, behavioral, and architectural differences that may lead to divergent results when processing the same input data.

---

## 1. Architectural Paradigms

### Legacy Backtester (`replay_loop.py`)
- **Monolithic & Synchronous**: A single linear loop processes candles one by one. Each step (feature computation, signal generation, execution, simulation) happens sequentially within the same process.
- **Pre-Synchronized Data**: Relies on `MultiTimeframeSyncLayer` to pre-align GC and DXY data into a unified DataFrame. There is no risk of data "desynchronization" during the run.
- **In-Memory State**: All trading state (PnL, loss streaks, active trades) is stored in volatile memory. Results are generated at the end of the run.

### Microservices (`services/`)
- **Distributed & Asynchronous**: Logic is split across multiple independent services (Data Adapter, Feature Engine, HTF Bias, Bot Core, Execution). Communication happens via **Redis Streams**.
- **Runtime Synchronization**: Services must synchronize disparate streams (e.g., GC candles with DXY candles, or Candles with Features) in real-time using pairing logic (`CandleSynchronizer`, `CandleFeatureSynchronizer`).
- **Persistent State**: State is transactionally stored in **PostgreSQL** (via `state_machine_snapshots`, `trades`, `daily_state`) and cached in memory.

---

## 2. Logical & Behavioral Differences

### 2.1 Signal Execution & Timing
- **Legacy**: Uses `iterate_with_entry_context` to provide the `next_candle` immediately. The signal is generated at bar $N$, and the entry is simulated precisely at the `open` of bar $N+1$.
- **Microservices**: `Bot Core` publishes a signal message. `Execution Service` receives it, buffers it, and waits for the *next* `CandleMessage` to arrive from the stream to trigger the entry.
- **Risk**: Any network latency or stream delay in a live/replay environment can shift the "wall-clock" timing of execution, though "data-time" should remain consistent if streams are processed in order.

### 2.2 VWAP Reclaim State Management
- **Legacy**: The `VWAPReclaimStateMachine` is integrated into the `BacktestProcessor`. Its state transitions are tightly coupled with the loop iteration.
- **Microservices**: `Execution Service` manages state machines via `StateMachineManager`. 
- **Auto-Confirmation**: In Phase 6 microservices, signals are **auto-confirmed** on the first bar after detection (`bar_idx > detection_bar_idx`). Legacy logic may have slightly different criteria for "acceptance" based on how `process_features_with_validation` is invoked.
- **Re-entry Protection**: Microservices persist `execution_count` to the database, ensuring re-entry protection survives service restarts. Legacy resets this count if the backtest is restarted.

### 2.3 Bar Counting & Expiration
- **Legacy**: Uses the global DataFrame index as a stable reference for bar counts.
- **Microservices**: Each service maintains an internal `_bar_counter` (e.g., `StateMachineManager._bar_counter`).
- **Drift Risk**: If a service restarts and restores state, the `_bar_counter` starts at 0 while the restored `entry_bar_idx` might be a large historical number. This can cause immediate expiration or incorrect "bars elapsed" logic if not reconciled (e.g., `current_bar - entry_bar` becoming negative or excessively large).

---

## 3. Implicit Assumptions & Time Handling

### 3.1 Data Stream Synchronization
- **Legacy**: Assumes GC and DXY bars are perfectly aligned by the loader.
- **Microservices**: Uses `CandleSynchronizer` with a `timeout_seconds` (default: 300s of data-time).
- **Difference**: In the microservices, if DXY data is missing for a specific timestamp, the GC candle will be dropped after the timeout. The legacy backtester might "forward-fill" or "align" differently depending on the `MultiTimeframeSyncLayer` configuration.

### 3.2 Feature-to-Candle Pairing
- **Microservices (Execution Service)**: Employs `CandleFeatureSynchronizer` to ensure that when a candle is checked for SL/TP, the *exact matching* feature set (for VWAP or RSI invalidation) is used.
- **Legacy**: Features and candles are rows in the same synchronized DataFrame, making pairing implicit and infallible.

### 3.3 Warmup Logic
- **Legacy**: `BacktestProcessor` typically needs a warmup period (e.g., 60 bars) to stabilize indicators like EMA and RSI.
- **Microservices**: `Feature Engine` performs a `warmup_processor` step by loading the last `N` candles from the database.
- **Discrepancy**: If the database doesn't have enough history, or if the history differs from the backtest CSV, the indicators will differ until the buffer is filled.

---

## 4. State Management & Resets

### 4.1 Daily Session Resets
- **Legacy**: `_reset_session` triggers when the date part of the timestamp changes.
- **Microservices**: `TradeManager.check_session_reset` does the same.
- **Discrepancy**: The microservices use a `DailyStateTracker` that restores today's PnL from the database on startup. If you run a backtest twice in legacy, it always starts at $0 PnL. In microservices, if you don't clear the database (`/admin/reset`), the second run will "inherit" the PnL of the first, potentially hitting PDLL immediately.

### 4.2 Trade Lifecycle
- **Legacy**: Trades are simulated objects. SL/TP is checked using `simulate_trade_outcome`.
- **Microservices**: Trades are `TradeRecord` entries in PostgreSQL. SL/TP and invalidations are checked bar-by-bar in `Execution Service` using `InvalidationChecker`. The microservices also involve a `Broker` (e.g., `PaperBroker`) which maintains its own internal position state.

---

## 5. Critical Differences Summary (Outcome-Altering)

| Difference | Impact on Outcome |
| :--- | :--- |
| **Stream Timeouts** | May drop bars if GC/DXY or Candle/Feature messages are too far apart in the stream, causing missed trades. |
| **State Persistence** | PDLL and Daily Trade Limits persist across restarts in microservices but reset in legacy backtests. |
| **Auto-Confirmation** | Microservices' auto-confirm logic (Phase 6) might be more or less aggressive than the legacy Rule Engine scoring. |
| **Database Sync** | If the database state (e.g., `state_machine_snapshots`) gets out of sync with the logic, signals may be blocked incorrectly. |
| **Floating Point** | JSON serialization of prices for Redis/Postgres may cause minute differences in SL/TP triggers compared to in-memory float64. |

---

## Conclusion

While the core logic (SOP, Scoring, Indicators) is shared via `scp_shared`, the **orchestration** of that logic differs significantly. The legacy system is a deterministic simulator, while the microservice system is a stateful, event-driven engine. To achieve parity in results, it is essential to ensure that the microservices start from a clean database state and that the stream synchronization timeouts are large enough to handle any data gaps.

