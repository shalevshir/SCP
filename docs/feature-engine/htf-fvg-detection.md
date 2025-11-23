# HTF Fair Value Gap (FVG) Detection & Scoring

## Overview

The Fair Value Gap detection and scoring system identifies 3-candle price imbalances on HTF charts where institutional order flow creates gaps that price often returns to fill. FVGs act as magnetic zones for price action and provide high-probability support/resistance areas for trade entries. The scoring system then adjusts HTF bias based on FVG alignment with the current trend.

## Purpose

Fair Value Gaps occur when there's a visible gap between three consecutive candles, indicating:

1. **Institutional Order Flow** - Large orders creating imbalances
2. **Support/Resistance Zones** - Areas where price is likely to return
3. **Entry Opportunities** - High-probability zones for trade entries
4. **Profit Targets** - Natural areas for price to seek liquidity
5. **Bias Confirmation** - Aligned FVGs increase trend confidence

## Function Signatures

### detect_fvg()

```python
def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Detect Fair Value Gaps in price data.
    
    Args:
        df: DataFrame with 'high', 'low' columns (minimum 3 rows)
    
    Returns:
        DataFrame with columns:
        - fvg_index: Index where FVG formed (at candle 3)
        - fvg_type: 'bullish' or 'bearish'
        - fvg_high: Upper boundary of gap
        - fvg_low: Lower boundary of gap
        - filled: False (initial state)
        - fill_index: None (initial state)
    """
```

### check_fvg_filled()

```python
def check_fvg_filled(
    df: pd.DataFrame,
    fvg_df: pd.DataFrame
) -> pd.DataFrame:
    """Check which FVGs have been filled by subsequent price.
    
    Args:
        df: Original OHLC DataFrame
        fvg_df: DataFrame returned by detect_fvg()
    
    Returns:
        Updated fvg_df with 'filled' and 'fill_index' updated
    """
```

### score_fvg_alignment()

```python
def score_fvg_alignment(
    fvg_df: pd.DataFrame,
    current_bias: str,
) -> float:
    """Score FVG alignment with HTF bias.
    
    Args:
        fvg_df: DataFrame from detect_fvg() with 'filled' status updated
        current_bias: Current HTF bias ("bullish", "bearish", "neutral")
    
    Returns:
        Float score adjustment:
        - Positive: FVGs aligned with bias (increases confidence)
        - Negative: FVGs oppose bias (decreases confidence)
        - Zero: No FVGs or neutral bias
    
    Logic:
        - Each unfilled bullish FVG aligned with bullish bias: +0.5
        - Each unfilled bearish FVG aligned with bearish bias: +0.5
        - Each unfilled FVG opposing current bias: -0.5
        - Filled FVGs ignored (no longer relevant)
        - Neutral bias always returns 0.0
    """
```

## FVG Detection Algorithm

### 3-Candle Pattern

FVG detection requires analyzing three consecutive candles:

**Bullish FVG (Gap Up):**
```
Candle 1: High=100, Low=98
Candle 2: High=101, Low=100.5  ← Must stay above candle 1 high
GAP: 100 to 103  ← The imbalance zone
Candle 3: High=105, Low=103  ← Must start above candle 1 high

Conditions:
✓ candle_1.high < candle_3.low  (gap exists)
✓ candle_2.high < candle_3.low  (candle 2 doesn't fill from above)
✓ candle_2.low > candle_1.high  (candle 2 doesn't fill from below)
```

**Bearish FVG (Gap Down):**
```
Candle 1: High=102, Low=100
Candle 2: High=99.5, Low=97.5  ← Must stay below candle 1 low
GAP: 97 to 100  ← The imbalance zone
Candle 3: High=97, Low=95  ← Must start below candle 1 low

Conditions:
✓ candle_1.low > candle_3.high  (gap exists)
✓ candle_2.low > candle_3.high  (candle 2 doesn't fill from below)
✓ candle_2.high < candle_1.low  (candle 2 doesn't fill from above)
```

## FVG Alignment Scoring

### Overview

The `score_fvg_alignment()` function adjusts HTF bias score based on alignment of unfilled FVGs with the current trend direction. Aligned FVGs increase confidence, while opposing FVGs reduce it.

### Scoring Logic

```python
from rule_engine.htf.vwap.fvg import score_fvg_alignment

# Bullish bias scenario
fvg_df = detect_fvg(df_1h)
fvg_df = check_fvg_filled(df_1h, fvg_df)

# 3 unfilled bullish FVGs, 1 bearish FVG
score = score_fvg_alignment(fvg_df, "bullish")
# Result: (3 * 0.5) - (1 * 0.5) = +1.0
```

### Rules

1. **Each unfilled aligned FVG**: +0.5 to score
2. **Each unfilled opposing FVG**: -0.5 to score
3. **Filled FVGs**: Ignored (no longer relevant)
4. **Neutral bias**: Always returns 0.0
5. **Net score**: (aligned count × 0.5) - (opposing count × 0.5)

### Scoring Examples

#### Strong Bullish Alignment

```python
# 4 unfilled bullish FVGs, 0 bearish FVGs
# Current bias: "bullish"
score = (4 * 0.5) - (0 * 0.5) = +2.0  # Strong bullish confirmation
```

#### Weak Bullish (Opposition)

```python
# 2 unfilled bullish FVGs, 3 bearish FVGs
# Current bias: "bullish"
score = (2 * 0.5) - (3 * 0.5) = -0.5  # Opposing FVGs reduce confidence
```

#### Balanced (No Effect)

```python
# 2 unfilled bullish FVGs, 2 bearish FVGs
# Current bias: "bullish"
score = (2 * 0.5) - (2 * 0.5) = 0.0  # Cancel out
```

#### Neutral Bias

```python
# Any FVG counts
# Current bias: "neutral"
score = 0.0  # Always zero for neutral
```

### HTF Bias Integration

```python
def compute_htf_bias_with_fvg_scoring(df_1h: pd.DataFrame) -> HTFBias:
    """Compute HTF bias with FVG alignment adjustment."""
    
    # Base bias calculation
    base_score = calculate_base_score(df_1h)
    bias_direction = "bullish" if base_score > 0 else "bearish"
    
    # Detect and check FVGs
    fvg_df = detect_fvg(df_1h)
    fvg_df = check_fvg_filled(df_1h, fvg_df)
    
    # Adjust score based on FVG alignment
    fvg_adjustment = score_fvg_alignment(fvg_df, bias_direction)
    final_score = base_score + fvg_adjustment
    
    logger.info(
        f"HTF Bias: {bias_direction}, "
        f"Base Score: {base_score:.2f}, "
        f"FVG Adjustment: {fvg_adjustment:+.2f}, "
        f"Final Score: {final_score:.2f}"
    )
    
    return HTFBias(
        direction=bias_direction,
        score=final_score,
        fvg_adjustment=fvg_adjustment
    )
```

### Multi-Timeframe Scoring

```python
def score_fvgs_multi_timeframe(
    df_1h: pd.DataFrame,
    df_15m: pd.DataFrame,
    current_bias: str
) -> dict:
    """Score FVG alignment across multiple timeframes."""
    
    # Detect FVGs on both timeframes
    fvg_1h = detect_fvg(df_1h)
    fvg_1h = check_fvg_filled(df_1h, fvg_1h)
    
    fvg_15m = detect_fvg(df_15m)
    fvg_15m = check_fvg_filled(df_15m, fvg_15m)
    
    # Score each timeframe
    score_1h = score_fvg_alignment(fvg_1h, current_bias)
    score_15m = score_fvg_alignment(fvg_15m, current_bias)
    
    # Combined weighted score (1H has more weight)
    combined_score = (score_1h * 0.7) + (score_15m * 0.3)
    
    return {
        'score_1h': score_1h,
        'score_15m': score_15m,
        'combined_score': combined_score,
        'confluence': 'high' if (score_1h > 0 and score_15m > 0) else 'low'
    }
```

## Use Cases

### 1. Trade Validation

```python
def validate_trade_with_fvg_scoring(
    df_1h: pd.DataFrame,
    trade_direction: str
) -> bool:
    """Validate trade using FVG alignment."""
    
    fvg_df = detect_fvg(df_1h)
    fvg_df = check_fvg_filled(df_1h, fvg_df)
    
    score = score_fvg_alignment(fvg_df, trade_direction)
    
    # Require positive FVG alignment for trade
    if score <= 0:
        logger.warning(f"Trade rejected: FVG score {score:.2f} not positive")
        return False
    
    logger.info(f"Trade validated: FVG score {score:+.2f}")
    return True
```

### 2. Position Sizing

```python
def adjust_position_size_by_fvg_score(
    base_position: float,
    fvg_df: pd.DataFrame,
    current_bias: str
) -> float:
    """Adjust position size based on FVG alignment."""
    
    score = score_fvg_alignment(fvg_df, current_bias)
    
    # Scale position by FVG confidence
    if score >= 1.5:
        multiplier = 1.2  # Strong alignment → larger position
    elif score >= 0.5:
        multiplier = 1.0  # Normal alignment → normal position
    elif score >= 0:
        multiplier = 0.8  # Weak alignment → smaller position
    else:
        multiplier = 0.5  # Opposing FVGs → much smaller position
    
    adjusted_position = base_position * multiplier
    
    logger.info(
        f"Position sizing: score={score:+.2f}, "
        f"multiplier={multiplier:.1f}, "
        f"position={adjusted_position:.2f}"
    )
    
    return adjusted_position
```

### 3. Risk Management

```python
def adjust_stop_loss_by_fvg_score(
    entry_price: float,
    base_stop: float,
    fvg_df: pd.DataFrame,
    current_bias: str
) -> float:
    """Tighten or widen stop loss based on FVG score."""
    
    score = score_fvg_alignment(fvg_df, current_bias)
    distance = abs(entry_price - base_stop)
    
    # Strong FVG alignment → tighter stop (more confidence)
    if score >= 1.5:
        adjusted_distance = distance * 0.8
    elif score >= 0.5:
        adjusted_distance = distance * 1.0
    elif score >= 0:
        adjusted_distance = distance * 1.2
    else:
        adjusted_distance = distance * 1.5  # Wider stop if opposing FVGs
    
    if current_bias == "bullish":
        adjusted_stop = entry_price - adjusted_distance
    else:
        adjusted_stop = entry_price + adjusted_distance
    
    return adjusted_stop
```

## Usage Examples

### Basic Detection and Scoring

```python
from rule_engine.htf.structure import detect_fvg, check_fvg_filled
from rule_engine.htf.vwap.fvg import score_fvg_alignment

# Detect all FVGs
fvg_df = detect_fvg(df_1h)
print(f"Found {len(fvg_df)} FVGs")

# Check which are filled
fvg_df = check_fvg_filled(df_1h, fvg_df)

# Filter unfilled FVGs
unfilled = fvg_df[~fvg_df['filled']]
print(f"{len(unfilled)} FVGs remain unfilled")

# Score alignment with current bias
current_bias = "bullish"
score_adj = score_fvg_alignment(fvg_df, current_bias)
print(f"FVG score adjustment: {score_adj:+.1f}")
```

### Trading Entry Zones

```python
# Find unfilled bullish FVGs for long entries
bullish_fvgs = fvg_df[
    (fvg_df['fvg_type'] == 'bullish') & 
    (~fvg_df['filled'])
]

for idx, fvg in bullish_fvgs.iterrows():
    print(f"Long Entry Zone: {fvg['fvg_low']:.2f} - {fvg['fvg_high']:.2f}")
    # Use as support zone for long entries
```

## Testing

### FVG Detection Tests

The module includes 28 comprehensive unit tests covering:

- **Core Detection** (5 tests): Bullish/bearish FVG detection
- **Fill Tracking** (9 tests): Tracking when FVGs get filled
- **Edge Cases** (10 tests): Empty data, equality violations, custom indices
- **Integration** (4 tests): Works with other structure functions

### FVG Scoring Tests

The module includes 20 comprehensive unit tests covering:

- **Core Functionality** (6 tests): Aligned/opposing FVGs with different biases
- **Filled Status** (3 tests): Only unfilled FVGs count
- **Edge Cases** (5 tests): Empty data, neutral bias, invalid inputs
- **Scoring Validation** (6 tests): Multiple FVGs, equal counts, net scores

All tests verify:
- Correct FVG detection with strict inequality
- Proper fill tracking (first fill only)
- Correct score calculations (±0.5 per FVG)
- Proper filtering of filled FVGs
- Neutral bias handling
- Input validation
- Edge case robustness

## Error Handling

```python
# Missing columns
ValueError: Missing required columns: {'high'}

# Empty data returns empty DataFrame (no error)
fvg_df = detect_fvg(empty_df)  # len(fvg_df) == 0

# Less than 3 candles returns empty DataFrame
fvg_df = detect_fvg(df_2_candles)  # len(fvg_df) == 0

# Invalid bias raises ValueError
ValueError: Invalid bias: sideways. Must be one of: ['bullish', 'bearish', 'neutral']
```

## Best Practices

1. **Always check filled status** before using FVGs
   - Unfilled FVGs = strong zones
   - Filled FVGs = already tested

2. **Combine with other structure** (BOS/CHoCH)
   - FVG + BOS = highest probability
   - FVG alone = medium probability

3. **Use for confluence, not sole signal**
   - Multiple timeframe FVGs aligned = stronger
   - Single isolated FVG = weaker

4. **Watch for gap size**
   - Larger gaps = stronger imbalance
   - Tiny gaps = less significant

5. **Track fill rates**
   - High fill rate in zone = strong area
   - Unfilled gaps near current price = targets

6. **Use scoring for confidence adjustment**
   - Positive score = increase position/tighten stops
   - Negative score = reduce position/widen stops

## References

- Task: [Implement FVG detection](https://www.notion.so/2b42bd6fbda6802d97abd15c795b9d7d)
- Task: [Add FVG interaction scoring](https://www.notion.so/2b42bd6fbda6806281cbf1eb4cff5704)
- Epic: [Full HTF Bias Engine Upgrade](https://www.notion.so/2b42bd6fbda6803d858de1e3002ab959)
- Related: `detect_swings()`, `detect_bos()`, `detect_choch()`, `detect_liquidity_sweeps()`

