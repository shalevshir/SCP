# Microservices vs Legacy Backtester: Comprehensive Comparison

**Document Purpose**: Identify and explain all logical differences between the new microservice implementation (`services/`) and the legacy backtester (`backtester/replay_loop.py`) that could affect trading outcomes, signal generation, state transitions, or timing.

**Last Updated**: 2025-01-XX

---

## Executive Summary

The microservices architecture introduces several architectural and behavioral changes that can lead to different trading outcomes even with identical input data. Key differences include:

1. **HTF Bias Timing**: Legacy computes HTF bias on every bar; microservices only at HTF boundaries
2. **Signal Buffering**: Microservices buffer signals for next-bar execution; legacy executes immediately
3. **State Machine Lifecycle**: Different confirmation and execution timing
4. **Invalidation Rules**: Microservices use simplified invalidation (missing micro structure, DXY flip, etc.)
5. **Bar Counter Logic**: Global vs per-trade counters
6. **Session Reset Timing**: Different placement in processing pipeline
7. **Message Synchronization**: Async message-based vs synchronous DataFrame iteration

---

## 1. Architecture & Data Flow

### Legacy Implementation (`backtester/replay_loop.py`)

**Flow**:
```
For each candle (synchronous iteration):
  1. Update active trades (check exits)
  2. Compute HTF bias (every bar)
  3. Check guardrails
  4. Generate signal (if guardrails pass)
  5. Execute entry immediately (if signal is A+)
  6. Create trade (if entry executed)
  7. Update state
```

**Characteristics**:
- Single-threaded, synchronous processing
- Direct DataFrame iteration (`processor.iterate_with_entry_context()`)
- All components in same process
- No message queuing or async delays
- Deterministic ordering guaranteed by DataFrame index

### Microservices Implementation (`services/`)

**Flow**:
```
Data Adapter → Redis Streams → Feature Engine → Redis Streams → HTF Bias → Redis Streams
                                                                                    ↓
Bot Core ← Redis Streams ← HTF Bias                                          Execution
                                                                                    ↓
                                                                              Redis Streams
```

**Characteristics**:
- Distributed, asynchronous processing
- Message-based communication (Redis Streams)
- Services can process messages out of order (within tolerance windows)
- Message synchronization required (CandleFeatureSynchronizer)
- Potential timing differences due to async I/O

**Key Difference**: Legacy processes everything in strict chronological order within a single loop. Microservices introduce message queuing, async processing, and potential reordering within synchronization windows.

---

## 2. HTF Bias Computation

### Legacy: Computed Every Bar

```python
# backtester/replay_loop.py:451
htf_bias = self._htf_bias_func(features, validation_context)
```

**Behavior**:
- HTF bias computed on **every single bar** (even when not at HTF boundary)
- Used immediately for signal generation
- Ensures HTF bias is always "current" for the exact bar being processed
- Structure detection warmup happens naturally through repeated calls

**Implications**:
- HTF bias reflects the most recent structure state
- No stale bias risk
- Higher computational cost (but acceptable for backtesting)

### Microservices: Computed Only at HTF Boundaries

```python
# services/htf-bias/src/htf_bias_svc/processor.py:87
htf_bias = self.calculator.update(gc_candle, dxy_candle)
# Returns None if not at boundary
if htf_bias is None:
    return None
```

**Behavior**:
- HTF bias computed **only when HTF boundary is crossed** (15m/1h)
- Bias cached and reused until next boundary
- Bot Core uses cached bias via timestamp-aware lookup

**Implications**:
- **CRITICAL**: Between HTF boundaries, signals use stale bias (from last boundary)
- Bot Core must use `bias_cache.get_for_timestamp_or_default()` to ensure correct historical bias
- If cache lookup fails, default bias may be used (could affect signal generation)
- Structure warmup happens only at boundaries

**Example Scenario**:
- Legacy: Bar at 10:05 uses HTF bias computed from 10:00-10:05 data
- Microservices: Bar at 10:05 uses HTF bias from 10:00 boundary (stale for 5 minutes)

**Impact**: Signals generated between HTF boundaries may use different HTF bias values, leading to different scores and confidence levels.

---

## 3. Signal Generation & Execution Timing

### Legacy: Immediate Execution Check

```python
# backtester/replay_loop.py:497-530
signal = process_features_with_validation(...)
execution = execute_entry_at_next_open(signal, next_candle)
if execution.executed:
    trade = create_trade_from_entry(...)
```

**Behavior**:
- Signal generated and execution checked **in the same loop iteration**
- `execute_entry_at_next_open()` checks if `next_candle` exists
- If executed, trade created immediately
- Entry price = `next_candle.open` (already known)

**Timing**:
- Signal timestamp: `current_candle.timestamp`
- Entry timestamp: `next_candle.timestamp`
- Entry price: `next_candle.open` (known at signal time)

### Microservices: Buffered Execution

```python
# services/bot-core/src/bot_core_svc/main.py:166
signal_msg = signal_engine.generate(features, bias, context)
if signal_msg is not None:
    await signal_publisher.publish(signal_msg)

# services/execution/src/execution_svc/trade_manager.py:88
async def on_signal(self, signal: SignalMessage) -> None:
    self._pending_signals.append(signal)
    await self._sm_manager.create_from_signal(signal)

# services/execution/src/execution_svc/main.py:215
await trade_manager.execute_pending_signals(candle_msg.open)
```

**Behavior**:
- Signal generated and **buffered** in `_pending_signals`
- Execution happens **on next candle arrival**
- State machine created immediately, but execution deferred
- Entry price = `candle_msg.open` (from the candle that triggers execution)

**Timing**:
- Signal timestamp: `features.timestamp` (from Feature Engine)
- Entry timestamp: `candle_msg.timestamp` (from next candle)
- Entry price: `candle_msg.open` (from next candle)

**Key Difference**: Legacy checks execution eligibility immediately. Microservices defer execution until the next candle arrives, introducing a one-candle delay between signal generation and execution decision.

**Impact**: If a signal is generated but the next candle has a gap or missing data, microservices may handle it differently than legacy (which already has `next_candle` available).

---

## 4. State Machine Lifecycle (VWAP_RECLAIM)

### Legacy: Embedded in Feature Processor

```python
# backtester/replay_loop.py:541-565
if execution.executed and signal.setup_type == "VWAP_RECLAIM":
    state_machine = self._processor._streaming.structure_tracker.vwap_reclaim_sm
    if not state_machine.can_execute():
        execution = execution.__class__(..., executed=False, ...)
```

**Behavior**:
- State machine embedded in `BacktestProcessor._streaming.structure_tracker`
- Single state machine instance (shared across all signals)
- Execution check happens **before trade creation**
- State machine notified **after trade creation** (line 728)

**Confirmation Logic**:
- Uses `second_confirmation_satisfied` from signal diagnostics
- Checked in `execute_entry_at_next_open()` (backtester/entry_model.py:117-150)
- If no confirmation, entry rejected immediately

### Microservices: Separate State Machine Manager

```python
# services/execution/src/execution_svc/state_machine_manager.py:71-100
def check_confirmation(self, signal_id: str, bar_idx: int | None = None) -> bool:
    # Auto-confirm on next bar (simplified for Phase 6)
    if sm.current_state == VWAPReclaimState.PENDING_ACCEPTANCE:
        if bar_idx > sm.detection_bar_idx:
            sm.on_confirmation(bar_idx=bar_idx, confirmation_type="auto_confirm")
    return sm.can_execute()
```

**Behavior**:
- Separate `StateMachineManager` with per-signal state machines
- State machines persisted to database
- **Auto-confirmation** on next bar (Phase 6 simplification)
- Confirmation check happens **during execution** (not before signal generation)

**Key Differences**:
1. **Confirmation Timing**: Legacy checks confirmation before execution; microservices auto-confirm on next bar
2. **State Machine Scope**: Legacy uses single shared instance; microservices use per-signal instances
3. **Persistence**: Microservices persist state machines to DB; legacy is in-memory only

**Impact**: VWAP_RECLAIM signals may execute at different times:
- Legacy: Requires `second_confirmation_satisfied=True` in signal diagnostics
- Microservices: Auto-confirms after 1 bar (simplified logic)

---

## 5. Entry Execution Model

### Legacy: Next Bar Open (Immediate Check)

```python
# backtester/entry_model.py:55-197
def execute_entry_at_next_open(signal: Signal, next_candle: Candle | None) -> EntryExecution:
    if next_candle is None:
        return EntryExecution(..., executed=False, rejection_reason="No next candle available")
    return EntryExecution(..., entry_price=next_candle.open, executed=True)
```

**Behavior**:
- `next_candle` provided by `processor.iterate_with_entry_context()`
- Execution check happens **immediately** after signal generation
- If `next_candle` is None (end of data), entry rejected
- Entry price = `next_candle.open` (known at check time)

### Microservices: Next Bar Open (Deferred Execution)

```python
# services/execution/src/execution_svc/trade_manager.py:168-201
async def execute_pending_signals(self, next_bar_open: float) -> None:
    for signal in self._pending_signals:
        can_trade, reason = self._daily_tracker.can_trade()
        if not can_trade:
            continue
        await self.execute_entry(signal, next_bar_open)
    self._pending_signals.clear()
```

**Behavior**:
- Signals buffered in `_pending_signals`
- Execution happens **when next candle arrives**
- Entry price = `next_bar_open` (from incoming candle)
- Daily limits checked **at execution time** (not signal generation time)

**Key Difference**: Legacy checks daily limits before signal generation. Microservices check daily limits **at execution time**, meaning a signal generated when limits allow may be rejected if limits are exceeded before the next candle arrives.

**Impact**: 
- If PDLL is hit between signal generation and execution, microservices will reject the signal
- Legacy would have already blocked signal generation before PDLL was hit

---

## 6. Invalidation Rules

### Legacy: Comprehensive Invalidation Suite

```python
# backtester/invalidations.py:808-879
def check_all(self, trade, candle, bars_elapsed, features):
    # 1. +1R time limit
    # 2. VWAP invalidation
    # 3. Micro structure invalidation (1m structure break)
    # 4. HTF structure invalidation (15m/1h)
    # 5. DXY flip (with 3-bar persistence for VWAP_RECLAIM)
    # 6. Session end (disabled per FIX #6)
    # 7. Setup window expiration
    # 8. Daily risk breach
```

**Invalidation Checks**:
1. ✅ +1R time limit (with September time-stop protection)
2. ✅ VWAP invalidation (2-bar confirmation for FADE)
3. ✅ Micro structure break (1m HH/LL)
4. ✅ HTF structure break (15m/1h)
5. ✅ DXY flip (3-bar persistence for VWAP_RECLAIM)
6. ✅ Session end (disabled)
7. ✅ Setup window expiration
8. ✅ Daily risk breach (PDLL, loss streak)

### Microservices: Simplified Invalidation

```python
# services/shared/src/scp_shared/execution/invalidation.py:291-332
def check_all(self, trade, candle, bars_elapsed, features):
    # 1. SL/TP hit (immediate exit)
    # 2. +1R time limit
    # 3. VWAP invalidation (2-bar confirmation for FADE)
```

**Invalidation Checks**:
1. ✅ SL/TP hit (immediate exit)
2. ✅ +1R time limit
3. ✅ VWAP invalidation (2-bar confirmation for FADE)
4. ❌ **Micro structure break** (NOT IMPLEMENTED)
5. ❌ **HTF structure break** (NOT IMPLEMENTED)
6. ❌ **DXY flip** (NOT IMPLEMENTED)
7. ❌ **Session end** (NOT IMPLEMENTED)
8. ❌ **Setup window expiration** (NOT IMPLEMENTED)
9. ❌ **Daily risk breach** (NOT IMPLEMENTED)

**Critical Missing Rules**:
- **Micro structure invalidation**: Legacy exits on 1m structure break (HH/LL); microservices do not
- **HTF structure invalidation**: Legacy exits on 15m/1h structure break; microservices do not
- **DXY flip**: Legacy exits on DXY correlation flip (3-bar persistence for VWAP_RECLAIM); microservices do not
- **September time-stop protection**: Legacy has early exit for deep red losses in September; microservices do not

**Impact**: Microservices will hold trades longer than legacy, potentially:
- Not exiting on structure breaks
- Not exiting on DXY flips
- Not exiting on deep red losses in September (time-stop protection)

---

## 7. Bar Counter Logic

### Legacy: Per-Trade Bar Counters

```python
# backtester/replay_loop.py:237-239
self._trade_bar_counts: dict[str, int] = {}  # External bar tracking

# backtester/replay_loop.py:944-947
if trade_id not in self._trade_bar_counts:
    self._trade_bar_counts[trade_id] = 0
self._trade_bar_counts[trade_id] += 1
bars_elapsed = self._trade_bar_counts[trade_id]
```

**Behavior**:
- Each trade has its own bar counter
- Counter increments only for **valid candles** (skips NaN/Inf)
- Counter starts at 0, increments on each valid candle after entry
- Used for timeout calculations (+1R time limit)

**Invalid Candle Handling**:
```python
# backtester/replay_loop.py:936-941
if not is_valid_candle(current_candle):
    logger.debug("Skipping invalid candle ... (bar counter not incremented)")
    continue
```

### Microservices: Global Bar Counter

```python
# services/execution/src/execution_svc/main.py:212
sm_manager.increment_bar_counter()

# services/execution/src/execution_svc/trade_manager.py:217-219
entry_bar = self._trade_entry_bars.get(trade.trade_id, 0)
current_bar = self._sm_manager._bar_counter
bars_elapsed = current_bar - entry_bar
```

**Behavior**:
- Single global bar counter (`_bar_counter`)
- Increments on **every candle** (no invalid candle check)
- Trades calculate `bars_elapsed = current_bar - entry_bar`
- Used for timeout calculations and state machine expiration

**Key Differences**:
1. **Invalid Candle Handling**: Legacy skips invalid candles; microservices count them
2. **Counter Scope**: Legacy uses per-trade counters; microservices use global counter
3. **Counter Initialization**: Legacy starts at 0 per trade; microservices use absolute bar index

**Impact**: 
- If invalid candles exist, legacy will have shorter `bars_elapsed` than microservices
- This affects timeout calculations (+1R time limit)
- Trades may exit at different times due to different bar counts

---

## 8. Session Reset Timing

### Legacy: Reset Before Guardrails Check

```python
# backtester/replay_loop.py:420-423
current_date = current_timestamp.date()
if self._session_date is None or current_date != self._session_date:
    self._reset_session(current_timestamp)

# backtester/replay_loop.py:482-490
guardrails_allowed, blocking_reasons = self._check_guardrails(...)
```

**Behavior**:
- Session reset happens **at the start of `_process_candle()`**
- Before guardrails check
- Before signal generation
- Daily limits (PDLL, max trades) reset before any processing

### Microservices: Reset Before Signal Execution

```python
# services/execution/src/execution_svc/main.py:205-207
trade_manager.check_session_reset(candle_msg.timestamp)
sm_manager.increment_bar_counter()
await trade_manager.execute_pending_signals(candle_msg.open)
```

**Behavior**:
- Session reset happens **before `execute_pending_signals()`**
- After candle processing starts
- Daily limits reset before signal execution (not before signal generation)

**Key Difference**: 
- Legacy resets session **before signal generation**
- Microservices reset session **before signal execution**

**Impact**: 
- If a signal is generated on the last bar of day N, but executed on first bar of day N+1:
  - Legacy: Signal would use day N limits (already checked)
  - Microservices: Signal execution uses day N+1 limits (fresh reset)
- This could cause signals to be rejected at execution time that would have executed in legacy

---

## 9. Daily State Tracking

### Legacy: In-Loop State Updates

```python
# backtester/replay_loop.py:992-1090
def _update_state(self, closed_trade: Trade) -> None:
    self._daily_pnl += closed_trade.pnl
    # Update behavior tracker
    self._processor.record_trade_outcome(won)
    # Update invalidation checker
    self._invalidation_checker.record_trade_outcome(closed_trade, won=won)
```

**Behavior**:
- State updated **immediately** after trade closes
- Daily PnL, loss streak updated in same loop iteration
- Guardrails check uses updated state on next iteration

### Microservices: Separate Daily Tracker

```python
# services/execution/src/execution_svc/daily_state.py
class DailyStateTracker:
    def record_trade_closed(self, pnl_points: float) -> None:
        self.state.daily_pnl += pnl_points
        # Update consecutive losses, etc.
```

**Behavior**:
- State updated **after trade closure**
- Daily tracker separate from invalidation checker
- State restored from database on service restart

**Key Difference**: Legacy updates state immediately in the same loop. Microservices update state asynchronously, but the timing should be equivalent since state is updated before the next candle is processed.

**Impact**: Minimal, but state restoration on restart could lead to different initial states if trades were in-flight during restart.

---

## 10. Message Synchronization

### Legacy: No Synchronization Needed

**Behavior**:
- DataFrames are pre-aligned by `MultiTimeframeSyncLayer`
- GC and DXY candles guaranteed to have matching timestamps
- Features computed synchronously from aligned DataFrames
- No message ordering issues

### Microservices: Explicit Synchronization

```python
# services/execution/src/execution_svc/main.py:119
synchronizer = CandleFeatureSynchronizer(timeout_seconds=300)

# services/execution/src/execution_svc/main.py:148-162
all_messages: list[tuple[str, CandleMessage | FeaturesMessage]] = []
for c in candles_list:
    all_messages.append(("candle", c))
for f in features_list:
    all_messages.append(("features", f))
all_messages.sort(key=lambda x: x[1].timestamp)

for msg_type, msg in all_messages:
    if msg_type == "candle":
        pair = synchronizer.add_candle(msg)
    else:
        pair = synchronizer.add_features(msg)
    if pair:
        await _process_candle_with_features(pair, ...)
```

**Behavior**:
- Candles and features arrive as separate messages
- Must be synchronized by timestamp before processing
- 300-second timeout window (5 minutes of data-time)
- Messages sorted by timestamp before adding to synchronizer

**Key Differences**:
1. **Ordering**: Microservices must handle out-of-order messages
2. **Timeout**: Messages older than 300 seconds are dropped
3. **Pairing**: Must wait for both candle and features before processing

**Impact**: 
- If messages arrive out of order, microservices may process them in different order than legacy
- If synchronization timeout expires, messages may be dropped (legacy never drops data)
- During high-speed replay, synchronization buffer may grow, causing memory pressure

---

## 11. Warmup & State Recovery

### Legacy: No Warmup Needed

**Behavior**:
- Full dataset available from start
- All features computed from beginning
- No state recovery needed
- HTF bias computed from full historical context

### Microservices: Database Warmup

```python
# services/feature-engine/src/feature_engine_svc/main.py:192-198
await warmup_processor(processor_1m, repository, "1m")
await warmup_processor(processor_15m, repository, "15m")
await warmup_processor(processor_1h, repository, "1h")
await warmup_htf_aggregator(htf_aggregator_gc, repository, symbol="GC")
```

**Behavior**:
- Processors warmed up from database (last N candles)
- HTF aggregators warmed up with recent candles
- State machines restored from database on restart
- Active trades restored from database

**Key Differences**:
1. **Warmup Period**: Microservices need warmup to initialize buffers (RSI, DXY correlation, etc.)
2. **State Recovery**: Microservices restore state from database; legacy starts fresh
3. **Historical Context**: Legacy has full historical context; microservices only have warmup window

**Impact**: 
- If warmup is insufficient, features may be inaccurate initially
- If state recovery fails, microservices may miss trades or have incorrect state
- Legacy always has correct historical context; microservices depend on warmup quality

---

## 12. VWAP Reclaim State Machine Differences

### Legacy: Single Shared State Machine

```python
# backtester/replay_loop.py:549-550
state_machine = self._processor._streaming.structure_tracker.vwap_reclaim_sm
```

**Behavior**:
- Single state machine instance shared across all signals
- State machine lives in feature processor
- Execution count tracked per reclaim context (not per signal)
- State machine notified on execution and stop-out

### Microservices: Per-Signal State Machines

```python
# services/execution/src/execution_svc/state_machine_manager.py:38
self._state_machines: dict[str, VWAPReclaimStateMachine] = {}
```

**Behavior**:
- Separate state machine per signal
- State machines persisted to database
- Execution count tracked per signal (not per reclaim context)
- State machines cleaned up after execution or expiration

**Key Differences**:
1. **Scope**: Legacy uses single shared instance; microservices use per-signal instances
2. **Re-entry Protection**: Legacy tracks executions per reclaim context; microservices track per signal
3. **Persistence**: Legacy is in-memory only; microservices persist to database

**Impact**: 
- Re-entry protection may work differently:
  - Legacy: Prevents multiple executions for the same reclaim context
  - Microservices: Prevents multiple executions for the same signal (but new signals can execute for same reclaim)
- If multiple signals are generated for the same reclaim, microservices may allow more executions than legacy

---

## 13. Implicit Assumptions & Defaults

### Legacy Assumptions

1. **Data Completeness**: Assumes all candles are valid (NaN/Inf filtered separately)
2. **Synchronous Processing**: No async delays or message queuing
3. **Single Process**: All state in memory, no persistence needed
4. **Deterministic Ordering**: DataFrame index guarantees order
5. **Full Historical Context**: All historical data available from start

### Microservices Assumptions

1. **Message Ordering**: Assumes messages arrive in reasonable order (within 300s window)
2. **Synchronization**: Assumes candles and features can be paired by timestamp
3. **Database Consistency**: Assumes database state is consistent with Redis streams
4. **Warmup Sufficiency**: Assumes warmup period is sufficient for accurate features
5. **State Recovery**: Assumes state can be restored correctly from database
6. **Auto-Confirmation**: Assumes VWAP_RECLAIM signals auto-confirm after 1 bar (Phase 6 simplification)

---

## 14. Behavioral Changes Summary

### Changes That Could Alter Trading Outcomes

| Change | Impact | Severity |
|--------|--------|----------|
| HTF bias computed only at boundaries | Signals use stale bias between boundaries | **HIGH** |
| Simplified invalidation (missing micro/HTF/DXY) | Trades held longer, different exit timing | **HIGH** |
| Daily limits checked at execution (not generation) | Signals rejected that would execute in legacy | **MEDIUM** |
| Global bar counter (no invalid candle skip) | Different timeout calculations | **MEDIUM** |
| Auto-confirmation for VWAP_RECLAIM | Different execution timing | **MEDIUM** |
| Message synchronization timeout | Messages may be dropped | **MEDIUM** |
| Per-signal state machines (vs shared) | Different re-entry protection | **LOW** |
| Session reset timing | Different daily limit enforcement | **LOW** |

### Changes That Should Not Affect Outcomes (But Verify)

| Change | Expected Impact |
|--------|----------------|
| Async message processing | Should process in same order (with synchronization) |
| Database warmup | Should match legacy after warmup period |
| State machine persistence | Should not affect execution logic |
| Separate daily tracker | Should update equivalently |

---

## 15. Recommendations

### Critical Fixes Needed

1. **Implement Missing Invalidation Rules**:
   - Add micro structure invalidation
   - Add HTF structure invalidation
   - Add DXY flip detection (with 3-bar persistence)
   - Add September time-stop protection

2. **Fix HTF Bias Staleness**:
   - Ensure `bias_cache.get_for_timestamp_or_default()` uses correct historical bias
   - Consider computing HTF bias on every bar (like legacy) or document staleness as acceptable

3. **Fix Bar Counter Logic**:
   - Skip invalid candles in bar counter (match legacy behavior)
   - Or document that invalid candles are counted differently

4. **Fix Daily Limits Timing**:
   - Check daily limits at signal generation time (not execution time)
   - Or document that signals may be rejected at execution that would execute in legacy

### Verification Tests

1. **Replay Test**: Run same dataset through both systems and compare:
   - Signal generation timestamps
   - Entry execution timestamps
   - Trade exit timestamps and reasons
   - Final PnL and trade counts

2. **State Machine Test**: Verify VWAP_RECLAIM confirmation logic matches legacy

3. **Invalidation Test**: Verify all invalidation rules produce same exits as legacy

4. **HTF Bias Test**: Compare HTF bias values at signal generation time

---

## 16. Conclusion

The microservices implementation introduces significant architectural changes that can lead to different trading outcomes. The most critical differences are:

1. **HTF bias staleness** between boundaries
2. **Missing invalidation rules** (micro structure, HTF structure, DXY flip)
3. **Different timing** for daily limits and session resets
4. **Simplified state machine logic** (auto-confirmation vs explicit confirmation)

These differences should be addressed before considering the microservices implementation equivalent to the legacy backtester for production use.

---

## Appendix: Code References

### Legacy Key Files
- `backtester/replay_loop.py`: Main replay loop
- `backtester/entry_model.py`: Entry execution logic
- `backtester/invalidations.py`: Invalidation rules
- `backtester/trade.py`: Trade creation and management

### Microservices Key Files
- `services/execution/src/execution_svc/main.py`: Execution service main loop
- `services/execution/src/execution_svc/trade_manager.py`: Trade lifecycle management
- `services/bot-core/src/bot_core_svc/main.py`: Signal generation loop
- `services/htf-bias/src/htf_bias_svc/main.py`: HTF bias computation
- `services/shared/src/scp_shared/execution/invalidation.py`: Simplified invalidation rules

