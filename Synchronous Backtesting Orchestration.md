# Technical Specification: Synchronous Backtesting Orchestration Protocol (SBOP)

**Version:** 1.0  
**Status:** Draft  
**Context:** Algorithmic Trading Backtesting Engine  

## 1. Executive Summary

The current backtesting system utilizes an asynchronous, multi-service architecture designed for high-throughput stream processing. While effective for real-time trading, this architecture introduces race conditions during high-speed backtesting, resulting in "Look-ahead Bias" and "Missing Data" errors (e.g., higher timeframe data arriving after the lower timeframe candle has been processed).

**The goal of this spec is to define a "Tick-Lock" orchestration pattern.** This ensures that for every simulation timestamp $T$, all independent calculation services (Features, HTF) complete their processing and synchronization *before* the Strategy Validator attempts to execute decision logic for $T$, and *before* the system advances to $T+1$.

## 2. System Architecture

### 2.1 The "Barrier" Pattern

The system will transition from a "Fire-and-Forget" model to a **"Publish-Wait-Advance"** model.

* **Asynchronous (Live Mode):** Data Source dumps data → Workers race to process → Validator processes what is available.
* **Synchronous (Backtest Mode):** Data Source (Orchestrator) emits one Tick → Workers process → Workers Signal Completion → Orchestrator verifies 100% completion → Orchestrator emits next Tick.



### 2.2 Core Components

1.  **The Orchestrator (Data Source):** The master clock. It controls the flow of time. It is responsible for injecting raw market data (Candles) and enforcing the synchronization barrier.
2.  **Worker Services (Subscribers):**
    * **Feature Engine:** Calculates volatility, momentum, and microstructure indicators.
    * **HTF (Higher Time Frame) Engine:** Calculates bias, structure, and trend based on aggregated data.
3.  **The Sync Manager (The Barrier):** A conceptual component (implemented via shared state/cache) that tracks the processing status of all workers for the current tick.
4.  **Strategy Validator (Consumer):** The final decision maker. It executes *only* when the Sync Manager confirms the "Global State" for Tick $T$ is valid and complete.

## 3. Functional Requirements

### 3.1 The Orchestration Loop

The Orchestrator must implement the following loop for every historical data point:

1.  **Emission:** Publish `Candle(T)` to the Message Bus.
2.  **State Initialization:** Set a "Pending Expectation" in the Sync Manager (e.g., "Waiting for: [Feature_Service, HTF_Service]").
3.  **Blocking Wait:** Enter a blocked state, listening for completion signals.
4.  **Verification:** Upon receiving signals, remove services from the "Pending" list.
5.  **Execution Trigger:** Once "Pending" is empty:
    * Trigger the `Strategy Validator` for Tick $T$.
    * Wait for Validator completion signal.
6.  **Advance:** Publish `Candle(T+1)`.

### 3.2 Worker Service Behavior (Stateless & Stateful)

All workers must adhere to the **Input-Process-Output-Ack** contract:

* **Input:** Listen for `Candle(T)`.
* **Process:** Perform specific calculations.
    * *Note for HTF Service:* Even if the Higher Time Frame bar (e.g., 15m) has not closed, the service **MUST** process the 1m update and return the *current known state* or *latest closed state*. It cannot remain silent.
* **Output:** Write calculated features/bias to the Data Store (State/Stream).
* **Ack (Crucial):** Send a `Signal(Service_ID, Timestamp, Status=DONE)` to the Sync Manager.

### 3.3 Strategy Validator

* **Trigger:** Must not run on the raw data stream. Must run only when triggered by the completion of the synchronization phase.
* **Data Access:** Reads from a unified "State Snapshot" guaranteed to be populated with data for Time $T$.

## 4. Data Interfaces & Contracts

### 4.1 Raw Data Message (Event)

* **Topic:** `market.data.feed`
* **Payload:**
    ```json
    {
      "timestamp": 1706976000,
      "symbol": "BTCUSD",
      "open": 42000.0,
      "high": 42100.0,
      "low": 41950.0,
      "close": 42050.0,
      "volume": 150.5
    }
    ```

### 4.2 Worker Completion Signal (Control Message)

* **Topic:** `system.sync.signals`
* **Payload:**
    ```json
    {
      "service_id": "htf_engine_v1",
      "processed_timestamp": 1706976000,
      "status": "OK" 
    }
    ```

### 4.3 Unified State Snapshot (Read Model)

When the Validator runs, it queries the State Store. The structure must be flattened for performance.

* **Key:** `state:{symbol}:latest`
* **Structure:**
    * `price_open`: `42000.0`
    * `feature_rsi`: `55.4`
    * `feature_vwap`: `41980.0`
    * `htf_trend_bias`: `"BULLISH"`
    * `htf_last_structure`: `"BOS_UP"`
    * `_data_timestamp`: `1706976000` (Must match current Tick)

## 5. Non-Functional Requirements

### 5.1 Performance

* **Latency:** The synchronization overhead must be minimal. Use pipelining for acknowledging signals.
* **Throughput:** The system should optimize for "Burst Processing" (processing batch history) rather than low-latency single events.

### 5.2 Determinism (Strict Requirement)

* The system must produce the **exact same results** regardless of how fast or slow the underlying hardware runs.
* The Orchestrator must **never** skip a wait step. A timeout constitutes a system failure, not a "skip".

### 5.3 Error Handling

* **Worker Failure:** If a worker fails to Ack within a configured timeout (e.g., 5 seconds), the Orchestrator must halt the backtest and raise a `SynchronizationTimeoutError`. Do not proceed with partial data.

## 6. Implementation Guidelines (Abstract)

* **Communication:** Use a high-performance message broker (e.g., Redis Streams, ZeroMQ, RabbitMQ).
* **State Management:** Use an in-memory key-value store (e.g., Redis, Memcached) for the "Sync Manager" logic. Atomic counters (Increment/Decrement) are recommended for tracking pending workers.
* **Environment Flag:** Implement a generic `mode` switch:
    * `mode=LIVE`: Async, non-blocking (current behavior).
    * `mode=BACKTEST`: Synchronous, blocking barrier (new behavior).