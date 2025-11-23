# HTF Liquidity Sweep Detection

## Overview

The liquidity sweep detection system identifies when price action "wicks" through prior swing levels but fails to close beyond them, indicating potential false breakouts, stop hunts, or reversal setups. These events are critical for fade trading strategies and trend invalidation signals.

## Purpose

Liquidity sweeps occur when institutional or algorithmic traders intentionally push price through known liquidity zones (stops at swing highs/lows) before reversing, trapping retail traders. Detecting these events helps:

1. **Identify false breakouts** - Distinguish real structural breaks from temporary sweeps
2. **Find fade opportunities** - Enter against failed sweeps for high R:R setups
3. **Validate trend strength** - Successful sweeps that become breakouts confirm momentum
4. **Invalidate bias** - Failed sweeps against trend signal weakness

## Function Signature

```python
def detect_liquidity_sweeps(
    df: pd.DataFrame,
    swing_highs: list[int],
    swing_lows: list[int],
) -> tuple[pd.Series, pd.Series]:
    """Detect liquidity sweep events.
    
    Args:
        df: DataFrame with 'high', 'low', 'close' columns
        swing_highs: List of integer indices where swing highs occurred
        swing_lows: List of integer indices where swing lows occurred
    
    Returns:
        Tuple of (sweep_events, sweep_success):
        - sweep_events: Series with labels ("sweep_high", "sweep_low", None)
        - sweep_success: Series indicating success (True/False/None)
    """
```

## Algorithm

### Step 1: Find Most Recent Swing

For each bar, identify the most recent swing high and swing low **before** the current bar:

```python
# Most recent swing high before bar i
prior_swing_high = max(swing_high for swing_high in swing_highs if swing_high < i)

# Most recent swing low before bar i
prior_swing_low = max(swing_low for swing_low in swing_lows if swing_low < i)
```

**Why most recent only?** Earlier swings may no longer represent active liquidity zones. Markets focus on the most recent structure.

### Step 2: Detect Sweep Conditions

**Sweep High:**
```python
if high > prior_swing_high and close < prior_swing_high:
    sweep_event = "sweep_high"
```
- Wick breaks above prior swing high (takes liquidity)
- Close fails to hold above (rejects breakout)

**Sweep Low:**
```python
if low < prior_swing_low and close > prior_swing_low:
    sweep_event = "sweep_low"
```
- Wick breaks below prior swing low (takes liquidity)
- Close fails to hold below (rejects breakdown)

**Ambiguous Case:**
```python
if sweeps_high and sweeps_low:
    sweep_event = None  # Reject whipsaw/chop
```

### Step 3: Track Success

Success is determined by the **next bar's close**:

**Successful Sweep High:**
```python
if next_close > prior_swing_high:
    success = True  # Breakout confirmed, became BOS
```

**Failed Sweep High:**
```python
if next_close <= prior_swing_high:
    success = False  # Reversal confirmed, fade opportunity
```

Similar logic applies for sweep lows.

## Return Values

### Sweep Events Series

| Value | Meaning | Trading Signal |
|-------|---------|----------------|
| `"sweep_high"` | Wick broke high, close didn't | Potential fade short |
| `"sweep_low"` | Wick broke low, close didn't | Potential fade long |
| `None` | No sweep or ambiguous | No signal |

### Sweep Success Series

| Value | Meaning | Next Action |
|-------|---------|-------------|
| `True` | Next bar confirmed breakout | Follow the break (BOS) |
| `False` | Next bar stayed inside | Fade opportunity |
| `None` | Last bar or no sweep | Cannot determine yet |

## Usage Examples

### Basic Detection

```python
from rule_engine.htf.structure import detect_swings, detect_liquidity_sweeps

# Detect swings on 1H chart
swing_highs, swing_lows = detect_swings(df_1h, lookback=5)

# Detect liquidity sweeps
sweep_events, sweep_success = detect_liquidity_sweeps(df_1h, swing_highs, swing_lows)

# Check most recent bar
latest_sweep = sweep_events.iloc[-1]
latest_success = sweep_success.iloc[-1]

if latest_sweep == "sweep_high" and latest_success == False:
    print("⚠ Failed sweep high - potential reversal/fade opportunity")
elif latest_sweep == "sweep_low" and latest_success == False:
    print("⚠ Failed sweep low - potential reversal/fade opportunity")
```

### Integration with BOS/CHoCH

```python
from rule_engine.htf.structure import (
    detect_swings,
    detect_bos,
    detect_choch,
    detect_liquidity_sweeps
)

# Detect all structure
swing_highs, swing_lows = detect_swings(df_1h, lookback=5)
bos = detect_bos(df_1h, swing_highs, swing_lows)
choch = detect_choch(df_1h, swing_highs, swing_lows)
sweep_events, sweep_success = detect_liquidity_sweeps(df_1h, swing_highs, swing_lows)

# Analyze recent structure
recent_idx = -1

if sweep_events.iloc[recent_idx] == "sweep_high":
    if sweep_success.iloc[recent_idx] == True:
        print("✓ Successful sweep → confirmed as bullish BOS")
    elif sweep_success.iloc[recent_idx] == False:
        print("⚠ Failed sweep → potential bearish reversal")
elif bos.iloc[recent_idx] == "bullish_bos":
    print("✓ Clean bullish BOS (no sweep)")
elif choch.iloc[recent_idx] == "bearish_choch":
    print("⚠ Bearish CHoCH detected")
```

### Fade Trading Strategy

```python
# Look for failed sweeps as fade opportunities
def find_fade_setups(df, swing_highs, swing_lows):
    """Find high-probability fade opportunities from failed sweeps."""
    sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
    
    fade_opportunities = []
    
    for i in range(len(df)):
        # Failed sweep high → fade short
        if sweep_events.iloc[i] == "sweep_high" and sweep_success.iloc[i] == False:
            entry = df['close'].iloc[i + 1]  # Next bar open
            stop = df['high'].iloc[i]        # Above sweep wick
            target = df['low'].iloc[i]       # Below sweep low
            
            fade_opportunities.append({
                'type': 'short',
                'index': i + 1,
                'entry': entry,
                'stop': stop,
                'target': target,
                'r_to_r': abs(target - entry) / abs(stop - entry)
            })
        
        # Failed sweep low → fade long
        elif sweep_events.iloc[i] == "sweep_low" and sweep_success.iloc[i] == False:
            entry = df['close'].iloc[i + 1]  # Next bar open
            stop = df['low'].iloc[i]         # Below sweep wick
            target = df['high'].iloc[i]      # Above sweep high
            
            fade_opportunities.append({
                'type': 'long',
                'index': i + 1,
                'entry': entry,
                'stop': stop,
                'target': target,
                'r_to_r': abs(target - entry) / abs(stop - entry)
            })
    
    return fade_opportunities
```

## Sweep vs BOS vs CHoCH

### Key Differences

| Feature | Liquidity Sweep | BOS | CHoCH |
|---------|----------------|-----|-------|
| **Wick Position** | Breaks level | May or may not break | May or may not break |
| **Close Position** | Doesn't break level | **Breaks level** | **Breaks opposite level** |
| **Meaning** | False breakout / trap | Trend continuation | Trend reversal |
| **Trade Signal** | Fade the sweep | Follow the break | Anticipate reversal |
| **Success Rate** | ~40-60% (many fail) | ~70-80% (most hold) | ~50-60% (reversal uncertain) |

### Conditions Are Mutually Exclusive

```python
# Sweep high: high > swing AND close < swing
# BOS high:   close > swing

# These cannot both be true for the same bar
if close > swing:
    # BOS (close broke)
elif high > swing and close < swing:
    # Sweep (wick broke, close didn't)
```

### Visual Example

```
Swing High at 100
─────────────────────

Bar A: Sweep High
  │  High: 105 (> 100) ✓
  ╞═ Close: 98 (< 100) ✓
  │  → SWEEP

Bar B: Bullish BOS
  │  High: 105 (> 100)
  ╞═ Close: 103 (> 100) ✓
  │  → BOS

Bar C: No Event
  │  High: 99 (< 100)
  ╞═ Close: 97 (< 100)
  │  → NONE
```

## Edge Cases

### 1. Ambiguous Sweep (Both Directions)

```python
# Candle sweeps BOTH high and low
if high > prior_swing_high and low < prior_swing_low:
    sweep_event = None  # Reject as whipsaw/chop
```

**Rationale:** Such volatility indicates indecision or chop, not a clean liquidity sweep.

### 2. Equality Does Not Trigger Sweep

```python
# Strict inequality required
if high == prior_swing_high:
    # NOT a sweep (no strict break)
```

**Rationale:** Touching a level is not the same as sweeping it.

### 3. Close Also Breaks → BOS, Not Sweep

```python
if high > prior_swing_high and close > prior_swing_high:
    # This is a BOS, not a sweep
    sweep_event = None
```

**Rationale:** If close also breaks, it's a confirmed breakout, not a failed sweep.

### 4. Last Bar Cannot Determine Success

```python
if i == len(df) - 1:
    sweep_success = None  # No next bar to evaluate
```

**Rationale:** Need next bar's close to determine if sweep was successful.

### 5. No Prior Swings

```python
if not swing_highs and not swing_lows:
    # No swings to sweep
    return all_none_series
```

## Trading Applications

### 1. Fade Entry Setup

**Bearish Fade (Failed Sweep High):**
- **Trigger:** Sweep high detected, next bar closes below swept level
- **Entry:** Market order on confirmation bar close
- **Stop:** Above sweep wick high + buffer
- **Target:** Prior swing low or structure support

**Bullish Fade (Failed Sweep Low):**
- **Trigger:** Sweep low detected, next bar closes above swept level
- **Entry:** Market order on confirmation bar close
- **Stop:** Below sweep wick low - buffer
- **Target:** Prior swing high or structure resistance

### 2. Trend Invalidation

```python
if current_trend == "bullish" and sweep_low_failed:
    # Bearish reversal signal
    htf_bias = "neutral"  # Invalidate bullish bias

if current_trend == "bearish" and sweep_high_failed:
    # Bullish reversal signal
    htf_bias = "neutral"  # Invalidate bearish bias
```

### 3. Confirmation of Breakout

```python
if sweep_high_successful:
    # Initially looked like a sweep, but broke through
    # This is now a confirmed bullish BOS
    htf_bias = "bullish"
    confidence = "high"  # Retested and broke
```

### 4. Structure Quality Filter

```python
def assess_structure_quality(df, swing_highs, swing_lows):
    """High sweep failure rate = choppy market."""
    sweep_events, sweep_success = detect_liquidity_sweeps(df, swing_highs, swing_lows)
    
    total_sweeps = sweep_events.notna().sum()
    failed_sweeps = (sweep_success == False).sum()
    
    if total_sweeps > 0:
        failure_rate = failed_sweeps / total_sweeps
        
        if failure_rate > 0.6:
            return "choppy"  # High failure → avoid
        elif failure_rate < 0.3:
            return "trending"  # Low failure → strong trend
        else:
            return "transitional"  # Mixed → cautious
    
    return "insufficient_data"
```

## Performance Characteristics

### Time Complexity

- **O(n × s)** where:
  - n = number of bars
  - s = number of swings per direction
- Similar to BOS/CHoCH detection

### Space Complexity

- **O(n)** for two result Series

### Optimization Tips

1. **Pre-filter swings** by removing very old swings (e.g., > 50 bars ago)
2. **Use numpy** for vectorized comparisons where possible
3. **Cache most recent swing** instead of searching repeatedly

## Integration with HTF Bias

```python
# In htf/calculator.py
from rule_engine.htf.structure import (
    detect_swings,
    detect_bos,
    detect_choch,
    detect_liquidity_sweeps
)

def compute_htf_bias(df_1h: pd.DataFrame, df_15m: pd.DataFrame) -> HTFBias:
    # Detect structure on 1H
    swing_highs_1h, swing_lows_1h = detect_swings(df_1h, lookback=5)
    bos_1h = detect_bos(df_1h, swing_highs_1h, swing_lows_1h)
    choch_1h = detect_choch(df_1h, swing_highs_1h, swing_lows_1h)
    sweep_events_1h, sweep_success_1h = detect_liquidity_sweeps(
        df_1h, swing_highs_1h, swing_lows_1h
    )
    
    # Check for recent failed sweeps (invalidate bias)
    recent_failed_sweep_high = (
        sweep_events_1h.iloc[-3:] == "sweep_high"
    ).any() and (sweep_success_1h.iloc[-3:] == False).any()
    
    recent_failed_sweep_low = (
        sweep_events_1h.iloc[-3:] == "sweep_low"
    ).any() and (sweep_success_1h.iloc[-3:] == False).any()
    
    # Adjust bias based on sweeps
    if recent_failed_sweep_high and current_bias == "bearish":
        # Bearish bias with failed high sweep → potential reversal
        bias_score -= 2.0
        confidence = "low"
    
    if recent_failed_sweep_low and current_bias == "bullish":
        # Bullish bias with failed low sweep → potential reversal
        bias_score -= 2.0
        confidence = "low"
    
    return HTFBias(
        direction=bias_direction,
        score=bias_score,
        confidence=confidence,
        sweep_high_count=sweep_events_1h.value_counts().get("sweep_high", 0),
        sweep_low_count=sweep_events_1h.value_counts().get("sweep_low", 0),
        failed_sweep_rate=(sweep_success_1h == False).sum() / max(sweep_events_1h.notna().sum(), 1)
    )
```

## Testing

The module includes 25 comprehensive unit tests covering:

### Core Functionality
- Sweep high detection
- Sweep low detection
- No sweep conditions
- Multiple sweeps

### Success Tracking
- Failed sweeps (next bar confirms reversal)
- Successful sweeps (next bar confirms breakout)
- Last bar handling (no next bar available)

### Edge Cases
- Ambiguous sweeps (both directions)
- Equality cases (strict inequality)
- Close also breaks (BOS, not sweep)
- Empty swing lists
- Empty DataFrame

### Validation
- Missing columns
- Invalid swing types
- Most recent swing only
- Prior swings only

### Integration
- Works with `detect_swings()`
- Custom DataFrame index
- Large datasets (1000+ bars)
- Complementary to BOS detection

## Error Handling

```python
# Missing columns
ValueError: Missing required columns: {'close'}

# Invalid swing types
ValueError: swing_highs and swing_lows must be lists

# Empty data returns empty Series (no error)
```

## Best Practices

1. **Always check sweep success** before trading
   - Failed sweeps = fade opportunities
   - Successful sweeps = follow the break

2. **Combine with other structure** (BOS/CHoCH)
   - Don't rely on sweeps alone
   - Look for confluence with trend direction

3. **Use most recent swings** (already implemented)
   - Don't compare to ancient swing levels
   - Focus on active liquidity zones

4. **Filter by market conditions**
   - High sweep failure rate = choppy market
   - Low sweep failure rate = strong trending

5. **Set proper stops**
   - For fades: Beyond sweep wick
   - For breakouts: Below/above swept level

## Future Enhancements

- [ ] Multi-swing detection (check multiple prior swings)
- [ ] Sweep magnitude scoring (how far beyond level)
- [ ] Volume confirmation (high volume on sweep = more significant)
- [ ] Time-based filtering (recent sweeps more relevant)
- [ ] Confluence detection (sweep + VWAP + FVG)

## References

- Task: [Implement liquidity sweep detection](https://www.notion.so/2b42bd6fbda680199823ed76ec78c685)
- Epic: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)
- Related: `detect_swings()`, `detect_bos()`, `detect_choch()`

