# Microservice Implementation vs Legacy Backtester Comparison

## Executive Summary

This document provides a comprehensive comparison between the new microservice implementation (under `services/`) and the legacy monolith implementation (`backtester/replay_loop.py`). The analysis identifies critical differences that could affect trading outcomes, signal generation, and backtest results.

**Key Finding**: While both implementations aim to follow the same SOP (Standard Operating Procedures), the distributed nature of the microservice architecture introduces several behavioral differences that could lead to different results from identical input data.

## 1. Architecture Overview

### Legacy Implementation (`backtester/replay_loop.py`)
- **Architecture**: Single-threaded, synchronous monolith
- **Processing**: Candle-by-candle iteration through pre-loaded DataFrames
- **State Management**: All state maintained in-memory within single process
- **Execution**: Deterministic, synchronous execution with immediate feedback

### Microservice Implementation (`services/`)
- **Architecture**: Distributed, event-driven services communicating via Redis Streams
- **Processing**: Asynchronous message consumption with potential out-of-order processing
- **State Management**: Distributed state across multiple services with database persistence
- **Execution**: Event-driven with buffering and potential delays

## 2. Processing Flow Differences

### Legacy: Synchronous Candle-by-Candle Processing
```python
# Legacy: Deterministic, sequential processing
for features, validation_context, next_candle in processor.iterate_with_entry_context():
    # Step 1: Update active trades (immediate)
    _update_active_trades(current_candle, features)

    # Step 2: Compute HTF bias (always, for streaming warmup)
    htf_bias = _htf_bias_func(features, validation_context)

    # Step 3: Check guardrails (immediate decision)
    if not guardrails_pass:
        continue

    # Step 4: Generate signal (immediate)
    signal = process_features_with_validation(...)

    # Step 5: Execute entry (immediate, at next bar open)
    execution = execute_entry_at_next_open(signal, next_candle)
    if execution.executed:
        trade = create_trade_from_entry(...)
        _active_trades[trade.id] = trade
```

### Microservice: Asynchronous Event-Driven Processing

**Data Adapter Service**: Publishes candles to Redis streams
**Feature Engine Service**: Consumes candles, computes features, publishes to streams
**HTF Bias Service**: Consumes HTF features, computes bias, publishes to streams
**Bot Core Service**: Consumes features + bias, generates signals, publishes to streams
**Execution Service**: Consumes signals + candles, manages trades

## 3. Critical Behavioral Differences

### 3.1 Timing and Synchronization Issues

#### Legacy: Deterministic Timing
- Features and HTF bias computed synchronously in same process
- Signals generated immediately after guardrail checks
- Trades executed at next bar open within same processing cycle

#### Microservice: Event-Driven Timing
- **Message Delays**: Redis Streams introduce variable latency between services
- **Out-of-Order Processing**: Messages may arrive out of timestamp order during replay
- **Race Conditions**: Bias updates may arrive after feature processing for same timestamp

**Impact**: Same candle could produce different signals due to stale bias or delayed messages.

### 3.2 HTF Bias Handling

#### Legacy: Always Computed, Immediately Available
```python
# Computed every bar regardless of trading activity
htf_bias = self._htf_bias_func(features, validation_context)
# Available immediately for signal generation
signal = process_features_with_validation(features=features, htf_bias=htf_bias, ...)
```

#### Microservice: Cached with Potential Staleness
```python
# Bias cache with TTL
bias_cache = HTFBiasCache(ttl_seconds=config.bias_cache_ttl_seconds, max_history=2000)

# Uses timestamp-aware lookup with fallback to default
bias = bias_cache.get_for_timestamp_or_default(features.timestamp)
```

**Critical Issue**: During replay, if HTF bias messages arrive after feature processing for the same timestamp, the cache lookup will return `None` or stale bias, potentially blocking signal generation.

### 3.3 Signal Filtering Differences

#### Legacy: All Signals Considered
```python
signal = process_features_with_validation(...)
# All confidence levels processed, but execution depends on score
if signal.confidence == "A+":
    execution = execute_entry_at_next_open(signal, next_candle)
```

#### Microservice: A+ Signals Only
```python
signal = score_signal(...)  # Raw signal generation
if signal.confidence != "A+":
    return None  # Filtered out entirely
```

**Impact**: Microservice only publishes A+ signals, potentially missing edge cases where signals upgrade during execution validation.

### 3.4 State Management Differences

#### Legacy: Centralized State
- Single process maintains all state (active trades, daily PnL, loss streaks)
- Immediate state updates after trade closures
- Session resets handled synchronously

#### Microservice: Distributed State
- **Bot Core**: Maintains guardrails state (loss streaks, daily limits)
- **Execution**: Maintains active trades, broker positions
- State reconciliation required on service restarts

**Critical Issue**: Race conditions possible when multiple trades close simultaneously or during service restarts.

### 3.5 Session Reset Timing

#### Legacy: Synchronous Session Management
```python
# Check session boundaries before any processing
current_date = current_timestamp.date()
if self._session_date != current_date:
    self._reset_session(current_timestamp)  # Immediate state reset
```

#### Microservice: Asynchronous Session Management
- **Bot Core**: Session validation per message
- **Execution**: Daily tracker checks on candle processing
- Potential for inconsistent session state across services

**Impact**: Services may have different session boundaries if messages are delayed.

## 4. Data Flow and Sequencing Differences

### 4.1 Message Ordering During Replay

**Legacy**: Deterministic order guaranteed by DataFrame iteration
**Microservice**: Redis Streams may deliver messages out of order during high-speed replay

**Mitigation**: Services use timestamp-based sorting and synchronizers, but this adds complexity and potential for dropped messages.

### 4.2 Candle-Feature Synchronization

**Legacy**: Perfect synchronization by design (processed together)
**Microservice**: Requires `CandleFeatureSynchronizer` with timeout-based cleanup

```python
# Execution service synchronizer with 5-minute timeout
synchronizer = CandleFeatureSynchronizer(timeout_seconds=300)
```

**Risk**: During replay with gaps (e.g., non-trading hours), unpaired messages may be dropped.

### 4.3 Signal Buffering and Execution

**Legacy**: Immediate execution decision
**Microservice**: Signals buffered until next candle open

```python
# Signals buffered for next bar execution
self._pending_signals.append(signal)

# Executed at next candle's open price
await trade_manager.execute_pending_signals(candle.open)
```

**Impact**: Execution price uses next candle's open, which may differ from legacy's next_candle parameter.

## 5. State Recovery and Persistence

### Legacy: Stateless Recovery
- State rebuilt from DataFrame replay
- No persistence between runs
- Deterministic results

### Microservice: Persistent State
- **Database Recovery**: Active trades and daily state persisted
- **Warmup Requirements**: Feature processors need database replay to initialize
- **State Reconciliation**: Broker position reconciliation on restart

**Critical Issue**: If database state becomes inconsistent with broker state, trades may be orphaned or duplicated.

## 6. Guardrails and Risk Management

### Legacy: Immediate Guardrail Evaluation
```python
guardrails_allowed, blocking_reasons = self._check_guardrails(
    validation_context, current_timestamp, features
)
if not guardrails_allowed:
    return None  # Skip signal generation
```

### Microservice: Distributed Guardrails
- **Bot Core**: Evaluates session and behavior guardrails
- **Execution**: Evaluates daily limits and concurrent trade limits

**Impact**: Guardrail decisions may be split across services with potential for inconsistency.

## 7. VWAP Reclaim State Machine Differences

### Legacy: Integrated State Machine
- State machine embedded in feature processor
- Immediate notification of trade events
- Single-process state consistency

### Microservice: Separate State Management
- `StateMachineManager` in Execution service
- Database persistence of state machine snapshots
- Potential for state machine drift during service restarts

**Critical Issue**: State machine state must be perfectly synchronized with trade execution for re-entry protection to work correctly.

## 8. Error Handling and Resilience

### Legacy: Fail-Fast Approach
- Single process failure stops entire backtest
- Immediate error visibility
- Deterministic error reproduction

### Microservice: Fault Isolation
- Individual service failures don't stop others
- Message redelivery and dead letter queues
- Complex error correlation across services

**Impact**: Silent failures in one service may not be immediately visible, leading to incomplete or incorrect results.

## 9. Performance and Scaling Characteristics

### Legacy: CPU-Bound Synchronous Processing
- Single-threaded, memory-efficient
- Predictable performance
- No concurrency overhead

### Microservice: I/O-Bound Asynchronous Processing
- Concurrent message processing
- Redis and database I/O overhead
- Potential for message backlog during high-speed replay

## 10. Testing and Validation Challenges

### Legacy: Deterministic Testing
- Same inputs → same outputs
- Easy regression testing
- Simple debugging

### Microservice: Non-Deterministic Testing
- Message ordering dependencies
- State synchronization requirements
- Complex integration testing needed

## 11. Critical Risks and Mitigation Strategies

### 11.1 High-Risk Issues

1. **Stale HTF Bias**: During replay, features processed before bias arrives
   - **Mitigation**: Implement bias cache with proper timestamp handling and defaults

2. **Message Ordering**: Out-of-order processing during high-speed replay
   - **Mitigation**: Timestamp-based sorting and synchronizers

3. **State Inconsistency**: Distributed state across services
   - **Mitigation**: Atomic operations and state reconciliation

4. **Signal Filtering**: A+ only filtering may miss edge cases
   - **Mitigation**: Consider publishing all signals with confidence levels

### 11.2 Validation Requirements

1. **Parallel Backtesting**: Run both implementations on same dataset
2. **Signal Comparison**: Compare signal generation at each timestamp
3. **Trade Outcome Comparison**: Validate trade entries, exits, and PnL
4. **State Synchronization**: Ensure daily limits and guardrails behave identically

## 12. Recommendations

### For Production Deployment
1. Implement comprehensive monitoring and alerting for message delays
2. Add circuit breakers for service failures
3. Implement message ordering guarantees in Redis Streams
4. Add state consistency checks across services

### For Backtesting Validation
1. Run parallel backtests with both implementations
2. Implement signal-by-signal comparison tools
3. Add comprehensive logging for debugging discrepancies
4. Consider hybrid approach: microservices for live trading, legacy for backtesting

### For Risk Management
1. Start with conservative limits in microservice deployment
2. Implement kill switches at multiple levels
3. Add manual override capabilities
4. Monitor for silent failures and state drift

## Conclusion

While the microservice architecture provides scalability and fault isolation benefits for live trading, it introduces several behavioral differences that could significantly impact backtest results and trading outcomes. The asynchronous, event-driven nature fundamentally changes the deterministic behavior of the legacy implementation.

**Key Recommendation**: Thoroughly validate the microservice implementation against the legacy backtester using identical datasets before deploying to live trading. Consider maintaining the legacy implementation as the authoritative backtesting system while using microservices for live execution.
