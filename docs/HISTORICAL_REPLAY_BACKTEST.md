# Historical Replay & Backtesting System

## Overview

The historical replay script (`scripts/replay_historical.py`) is a validation testing tool that replays historical market data through the entire microservices pipeline. It enables end-to-end testing of the trading system by simulating real-time market conditions using historical GC (Gold) and DXY (US Dollar Index) candle data.

**Primary Use Case**: Validate that microservices produce identical results to the backtester by processing the same historical data.

## Architecture

### Data Flow

```
CSV Files (Historical Data)
    ↓
HistoricalDataLoader (align GC + DXY by timestamp)
    ↓
Redis Streams (candles.1m.gc, candles.1m.dxy)
    ↓
Feature Engine → features.1m/15m/1h
    ↓
HTF Bias + Bot Core → signals.pending
    ↓
Execution → trades.{opened,closed}
    ↓
PostgreSQL (persisted results)
```

### Key Components

#### 1. Data Loading (`HistoricalDataLoader`)
- Loads GC and DXY OHLCV data from CSV files
- Aligns candles by timestamp (inner join)
- Ensures paired candles for both symbols

#### 2. Stream Publishing
- Publishes to Redis streams: `candles.1m.gc` and `candles.1m.dxy`
- Uses XADD with MAXLEN trimming to prevent memory bloat
- Applies backpressure monitoring to prevent overwhelming consumers

#### 3. Backpressure Control
- Monitors consumer group pending messages using XPENDING
- Pauses publishing when any consumer has >500 unacknowledged messages
- Prevents memory exhaustion and ensures pipeline stability

#### 4. Pipeline Synchronization
- Waits for each pipeline stage to complete processing
- Stage 1: Feature Engine consumes candles
- Stage 2: Bot Core consumes features
- Stage 3: Execution consumes signals
- Uses XINFO GROUPS to track consumer progress

## Configuration

### Backpressure Settings
```python
MAX_PENDING_MESSAGES = 500          # Max unacked messages before pausing
BACKPRESSURE_CHECK_INTERVAL = 50    # Check every N publishes
BACKPRESSURE_WAIT_SECONDS = 0.5     # Wait time when backpressure detected
```

### Stream Trimming
```python
STREAM_MAXLEN = 50000  # ~30 days of 1m candles
# NOTE: Must exceed total candles to prevent data loss for slower consumers
# 30 days × 24h × 60min = 43,200 candles → 50,000 buffer
```

### Monitored Consumer Groups
- `candles.1m.gc:feature-engine`
- `candles.1m.dxy:feature-engine`
- `candles.1m.gc:htf-bias`
- `candles.1m.dxy:htf-bias`
- `features.1m:bot-core`
- `features.1m:execution`
- `htf.bias:bot-core`
- `signals.pending:execution`

## Usage

### Basic Replay (Turbo Mode)
```bash
poetry run python scripts/replay_historical.py \
    --start 2024-11-01 \
    --end 2024-11-30 \
    --speed 0  # Turbo mode (no delays)
```

### Speed-Controlled Replay
```bash
# 100x faster than real-time
poetry run python scripts/replay_historical.py \
    --start 2024-11-01 \
    --end 2024-11-30 \
    --speed 100

# Real-time replay (1x speed)
poetry run python scripts/replay_historical.py \
    --start 2024-11-01 \
    --end 2024-11-30 \
    --speed 1
```

### Custom Configuration
```bash
poetry run python scripts/replay_historical.py \
    --start 2024-11-01T00:00:00Z \
    --end 2024-11-30T23:59:59Z \
    --data-dir data/gc_dx_ohlcv \
    --redis-url redis://localhost:6379 \
    --processing-delay 10.0
```

## Speed Modes

| Mode | Speed | Use Case |
|------|-------|----------|
| **Turbo** | 0 (no delays) | Fast validation testing, maximum throughput |
| **Accelerated** | 100x-1000x | Testing with some time realism |
| **Real-time** | 1x | Debugging timing-sensitive issues |

**Turbo Mode** (speed=0):
- No artificial delays between candles
- Relies entirely on backpressure control
- Publishes as fast as consumers can process
- Typical speedup: 100x-1000x depending on hardware

## Current Limitations & Issues

### 1. **No Result Validation**
- Script publishes data but doesn't verify correctness
- No comparison between microservices output and backtester results
- **Impact**: Cannot confirm if pipeline produces expected trades/signals

### 2. **Limited Observability**
- Minimal logging during execution
- No metrics on pipeline performance
- No visibility into processing bottlenecks
- **Impact**: Hard to diagnose issues or optimize performance

### 3. **Hard-coded Configuration**
- Backpressure thresholds are constants, not configurable
- Stream maxlen is fixed in code
- Consumer groups list is static
- **Impact**: Can't tune for different hardware or testing scenarios

### 4. **No Error Recovery**
- Crashes on any exception during replay
- No checkpoint/resume functionality
- Must restart from beginning on failure
- **Impact**: Wastes time on long replays if interrupted

### 5. **Single Symbol Pair**
- Only supports GC + DXY
- Hard-coded symbol names
- **Impact**: Can't test other trading pairs

### 6. **Memory Inefficiency**
- Loads entire dataset into memory with pandas
- Could stream row-by-row for large datasets
- **Impact**: Memory pressure on multi-month replays

### 7. **No Dry-run Mode**
- Can't preview what would be replayed
- No validation of date ranges or data availability
- **Impact**: Wastes time discovering data issues mid-replay

### 8. **Fixed Timeframe**
- Only replays 1m candles
- Can't test 5m, 15m, or other timeframes
- **Impact**: Limited testing coverage

## Recommended Improvements

### Priority 1: Result Validation

**Problem**: No verification that microservices produce correct output.

**Solution**: Add result comparison module
```python
class ReplayValidator:
    async def compare_trades(
        self,
        expected: list[Trade],  # From backtester
        actual: list[Trade],    # From microservices
    ) -> ValidationReport:
        """Compare backtest vs microservices trades."""
        # Compare entry/exit prices, timestamps, P&L
        # Generate diff report
        pass
```

**Benefits**:
- Automated correctness verification
- Catch regressions in signal logic
- Build confidence in production deployment

### Priority 2: Metrics & Observability

**Problem**: No visibility into pipeline performance.

**Solution**: Add Prometheus metrics + structured logging
```python
from prometheus_client import Counter, Histogram, Gauge

candles_published = Counter('replay_candles_published_total', 'Total candles published')
processing_latency = Histogram('replay_processing_seconds', 'Time from publish to signal')
consumer_lag = Gauge('replay_consumer_lag', 'Messages behind', ['stream', 'group'])
```

**Benefits**:
- Identify bottlenecks (Feature Engine vs Bot Core)
- Monitor consumer lag in real-time
- Track replay progress with Grafana dashboard

### Priority 3: Configuration Externalization

**Problem**: Hard-coded constants make tuning difficult.

**Solution**: Move to YAML config file
```yaml
# config/replay.yaml
backpressure:
  max_pending_messages: 500
  check_interval: 50
  wait_seconds: 0.5

streams:
  maxlen: 50000

consumers:
  - stream: candles.1m.gc
    group: feature-engine
  - stream: candles.1m.dxy
    group: feature-engine
```

**Benefits**:
- Tune for different environments (dev/prod/CI)
- A/B test different settings
- Document configuration options

### Priority 4: Checkpoint & Resume

**Problem**: Long replays must restart from beginning on failure.

**Solution**: Add state persistence
```python
class ReplayCheckpoint:
    def __init__(self, checkpoint_file: Path):
        self.checkpoint_file = checkpoint_file

    async def save(self, timestamp: datetime, published_count: int):
        """Save progress to disk."""
        pass

    async def load(self) -> tuple[datetime, int] | None:
        """Resume from last checkpoint."""
        pass
```

**Benefits**:
- Resume multi-hour replays after interruption
- Save time on debugging
- Support incremental testing

### Priority 5: Multi-symbol Support

**Problem**: Only GC + DXY supported.

**Solution**: Parameterize symbols
```python
parser.add_argument(
    "--symbols",
    nargs="+",
    default=["GC", "DXY"],
    help="Symbols to replay (default: GC DXY)"
)
```

**Benefits**:
- Test other trading pairs
- Future-proof for portfolio expansion
- Isolate single-symbol testing

### Priority 6: Streaming Data Load

**Problem**: Loading entire dataset into memory is inefficient.

**Solution**: Stream rows with chunked iteration
```python
for chunk in loader.load_chunked(symbols, timeframe, start, end, chunk_size=10000):
    for candle_pair in chunk:
        await publish_candle(candle_pair)
```

**Benefits**:
- Reduce memory footprint
- Support year+ replays
- Better performance on large datasets

### Priority 7: Dry-run & Validation

**Problem**: Can't preview replay before execution.

**Solution**: Add dry-run mode
```bash
poetry run python scripts/replay_historical.py \
    --start 2024-11-01 \
    --end 2024-11-30 \
    --dry-run
```

Output:
```
Dry-run Report:
- Data directory: data/gc_dx_ohlcv
- Date range: 2024-11-01 to 2024-11-30 (30 days)
- GC candles: 43,200
- DXY candles: 43,200
- Aligned pairs: 43,200
- Estimated duration (turbo): ~5 minutes
- Streams to be used: candles.1m.gc, candles.1m.dxy
```

**Benefits**:
- Catch data issues before replay starts
- Estimate runtime
- Validate date range coverage

### Priority 8: Multi-timeframe Support

**Problem**: Only 1m candles supported.

**Solution**: Add timeframe parameter
```python
parser.add_argument(
    "--timeframe",
    default="1m",
    choices=["1m", "5m", "15m", "1h"],
    help="Candle timeframe (default: 1m)"
)
```

**Benefits**:
- Test higher timeframe strategies
- Validate HTF bias independently
- Faster testing with fewer candles

## Performance Optimization Ideas

### 1. Parallel Publishing
- Publish GC and DXY in parallel with asyncio.gather()
- Current: sequential (GC then DXY)
- Expected speedup: ~2x

### 2. Batch Publishing
- Group candles into batches of 10-100
- Use Redis pipelining
- Reduce network round-trips

### 3. Pre-compute Alignment
- Save aligned candles to cache file
- Skip merge step on repeated runs
- Useful for iterative testing

### 4. Smart Backpressure
- Use weighted backpressure by service criticality
- Allow Feature Engine to lag more than Bot Core
- Optimize for pipeline throughput

## Testing Workflow

### Current Workflow (Manual)
1. Run replay script
2. Wait for completion
3. Manually query PostgreSQL for trades
4. Manually compare to backtester results
5. Manually verify correctness

**Issues**: Time-consuming, error-prone, not automated

### Proposed Workflow (Automated)
1. Run replay with `--validate` flag
2. Script automatically queries PostgreSQL
3. Compares to expected results from backtester CSV
4. Generates validation report with diffs
5. Exits with code 0 (pass) or 1 (fail)

**Benefits**: CI/CD integration, automated regression testing

## Example Validation Report

```
Historical Replay Validation Report
====================================
Period: 2024-11-01 to 2024-11-30
Replay Duration: 6m 32s
Candles Published: 43,200 pairs

Pipeline Performance:
- Feature Engine: 43,200/43,200 processed (avg 110/sec)
- Bot Core: 43,200/43,200 processed (avg 105/sec)
- Execution: 27 signals processed

Trade Comparison:
✓ Total trades: 12 (expected: 12)
✓ Entry prices: 12/12 match (within 0.01 ticks)
✓ Exit prices: 11/12 match
  ✗ Trade #8: expected exit 2024.50, actual 2024.75 (0.25 tick diff)
✓ P&L: $4,250 (expected: $4,200, diff: +$50)

Signal Comparison:
✓ Total signals: 27 (expected: 27)
✓ Signal scores: 27/27 match
✓ Invalidations: 15 (expected: 15)

Status: PASSED (1 minor exit price deviation)
```

## Related Documentation

- [Microservices Architecture](./MICROSERVICES_ARCHITECTURE.md)
- [Redis Streams Guide](./REDIS_STREAMS.md)
- [Testing Strategy](./TESTING_STRATEGY.md)
- [Backtesting System](./BACKTESTING.md)

## Future Enhancements

### Advanced Features
- **Live vs Historical Comparison**: Run live and replay side-by-side to verify consistency
- **Stress Testing**: Replay at 1000x+ speed to find breaking points
- **Candle Injection**: Inject specific candle patterns to test edge cases
- **State Snapshots**: Capture full system state at specific timestamps for debugging
- **Performance Profiling**: Integrated cProfile/pyinstrument for bottleneck analysis

### Integration Possibilities
- **Grafana Dashboard**: Real-time replay progress visualization
- **Slack Notifications**: Alert on validation failures or completion
- **S3 Storage**: Archive replay results for historical analysis
- **Jupyter Integration**: Interactive replay analysis notebooks
