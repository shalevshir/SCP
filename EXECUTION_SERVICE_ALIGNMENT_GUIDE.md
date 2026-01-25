# Execution Service Alignment Guide

## Current Status: ✅ No Breaking Changes, ⚠️ Incomplete SOP Implementation

---

## TL;DR

**Bot-core changes are backward compatible** - execution service will continue working.

**However**, to FULLY implement SOP continuation mode, execution service needs updates for:
1. TP2 secondary target monitoring
2. Breakeven (BE) move after TP1 hit
3. Optional: Partial exits at TP1

---

## What Execution Service Currently Does

```python
# In execute_entry():
trade = TradeRecord(
    entry_price=actual_entry_price,
    sl_price=signal.sl_price,
    tp_price=signal.tp_price,  # Uses TP1 (tp_price field)
    # DOES NOT use: tp2_price, be_after_tp1, tp_mode
)

# In _check_trade_exit():
# - Monitors single TP (tp_price)
# - Exits when TP hit
# - NO TP2 monitoring
# - NO BE move after TP1
```

---

## What Bot-Core Now Provides

New SignalMessage fields (all have defaults - backward compatible):
```python
tp_mode: str = "static"              # Mode indicator
tp2_price: float | None = None       # Secondary TP (continuation)
rr_tp1: float | None = None          # R:R at TP1
rr_potential: float | None = None    # Total potential
be_after_tp1: bool = False           # BE move flag
tp_target_source: str | None = None  # Target source
```

**Backward Compatibility**: If execution service ignores new fields, it works correctly:
- Uses `signal.tp_price` (which is TP1)
- Exits at TP1 hit
- Static mode continues as before

---

## Impact Analysis by Setup Type

### VWAP_FADE (Static Mode)
- ✅ **No impact** - Uses static mode
- ✅ Already working correctly
- ✅ Single TP at 3R

### DXY_CONTINUATION (Static Mode)
- ✅ **No impact** - Uses static mode
- ✅ Already working correctly
- ✅ Single TP at 3R

### VWAP_RECLAIM A+ (Continuation Mode)
- ⚠️ **Partial implementation**
- ✅ TP1 at 1.5R+ works (exits at tp_price)
- ❌ TP2 ignored (not monitored)
- ❌ BE move after TP1 not implemented
- ❌ No partial exits

---

## Required Changes for Full SOP Compliance

### 1. TradeRecord Extension (Required for TP2)

```python
@dataclass
class TradeRecord:
    # Existing fields...
    tp_price: float  # TP1 (primary)
    
    # NEW: Continuation mode fields
    tp_mode: str = "static"
    tp2_price: float | None = None
    tp1_hit: bool = False  # Track if TP1 already hit
    be_moved: bool = False  # Track if SL moved to BE
```

### 2. Execute Entry Updates

```python
async def execute_entry(self, signal: SignalMessage, entry_price: float) -> TradeRecord | None:
    # Existing code...
    
    trade = TradeRecord(
        # ...existing fields...
        tp_price=signal.tp_price,  # TP1
        # NEW: Continuation fields
        tp_mode=signal.tp_mode,
        tp2_price=signal.tp2_price,
        tp1_hit=False,
        be_moved=False,
    )
```

### 3. Exit Checking Updates

```python
async def _check_trade_exit(self, trade: TradeRecord, candle: Candle, features: dict) -> None:
    # Existing invalidation checks...
    
    # NEW: Check TP1 hit (for continuation mode)
    if trade.tp_mode == "continuation" and not trade.tp1_hit:
        if self._check_tp_hit(trade, candle, trade.tp_price):
            # TP1 hit in continuation mode
            if trade.be_after_tp1:
                # Move SL to breakeven
                trade.sl_price = trade.entry_price
                trade.be_moved = True
                await self._repo.update_sl_price(trade.trade_id, trade.entry_price)
                logger.info(f"Trade {trade.trade_id} TP1 hit - moved SL to BE @ {trade.entry_price:.2f}")
            
            trade.tp1_hit = True
            await self._repo.update_tp1_hit(trade.trade_id, True)
            
            # If no TP2, close trade at TP1
            if trade.tp2_price is None:
                await self._close_trade(trade, trade.tp_price, "TP1_HIT", candle.timestamp)
                return
            
            # Otherwise, continue monitoring for TP2
            # Optional: Partial exit at TP1 (50% position)
    
    # NEW: Check TP2 hit (for continuation mode)
    if trade.tp_mode == "continuation" and trade.tp1_hit and trade.tp2_price:
        if self._check_tp_hit(trade, candle, trade.tp2_price):
            await self._close_trade(trade, trade.tp2_price, "TP2_HIT", candle.timestamp)
            return
    
    # Existing: Check SL hit (now respects BE-moved SL)
    # ...
```

### 4. Database Schema Updates (Optional)

```sql
-- Add to trades table
ALTER TABLE trades ADD COLUMN IF NOT EXISTS tp_mode VARCHAR(20) DEFAULT 'static';
ALTER TABLE trades ADD COLUMN IF NOT EXISTS tp2_price NUMERIC(12,4);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS tp1_hit BOOLEAN DEFAULT FALSE;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS be_moved BOOLEAN DEFAULT FALSE;
```

---

## Implementation Priority

### Phase 1: Minimal (Current - Working) ✅
- Bot-core sends continuation signals
- Execution uses TP1 (tp_price field)
- Exits at TP1 hit
- **Status**: Working but incomplete

### Phase 2: TP2 Monitoring (Recommended Next)
- Track TP2 separately
- Exit at TP2 if hit
- Keep trade open after TP1 until TP2/invalidation
- **Effort**: Medium (~200 lines)

### Phase 3: BE Move (Recommended)
- Move SL to BE after TP1 hit
- Protects capital on TP2 runs
- **Effort**: Small (~50 lines)

### Phase 4: Partial Exits (Optional)
- Exit 50% at TP1
- Let 50% run to TP2
- **Effort**: Medium (~150 lines)

---

## What Happens NOW (Phase 1)

### Continuation Mode Signal Generated:
```json
{
  "tp_mode": "continuation",
  "tp_price": 2665.0,    // TP1
  "tp2_price": 2700.0,   // Ignored by execution
  "be_after_tp1": true,  // Ignored by execution
  "rr_tp1": 1.5,
  "rr_potential": 5.0
}
```

### Execution Service Behavior:
1. ✅ Creates trade with SL=2640.0, TP=2665.0 (uses tp_price = TP1)
2. ✅ Monitors candles for SL/TP hit
3. ✅ Exits at 2665.0 (TP1 hit) → **Captures 1.5R profit**
4. ❌ Never monitors for TP2=2700.0
5. ❌ Never moves SL to BE

**Result**: Trade exits early (1.5R) instead of running to TP2 (5R potential).

---

## Risk Assessment

### Current State (Phase 1):
- ✅ **No breakage** - Everything works
- ✅ **Capital protected** - Exits at TP1 with profit
- ⚠️ **Leaves profit on table** - Doesn't capture TP2 extensions
- ⚠️ **Not fully SOP-compliant** - Missing staged TP behavior

### If Phase 2/3 Implemented:
- ✅ **Full SOP compliance** - Staged TPs with BE protection
- ✅ **Higher R:R potential** - Captures extension moves
- ⚠️ **Increased complexity** - More state to track
- ⚠️ **Requires testing** - New exit logic needs validation

---

## Recommendation

### Immediate (Now):
✅ **Ship bot-core changes** - Backward compatible, well-tested

### Short-term (Next Sprint):
🔲 **Phase 2: TP2 Monitoring** - Capture extension potential  
🔲 **Phase 3: BE Move** - Protect capital after TP1

### Medium-term (Later):
🔲 **Phase 4: Partial Exits** - Advanced position management

---

## Test Strategy for Execution Updates

When implementing Phases 2/3, follow TDD:

### RED - Write failing tests:
```python
class TestContinuationModeExecution:
    def test_tp1_hit_moves_sl_to_be_when_be_after_tp1_true(self):
        """TP1 hit should move SL to BE for continuation mode."""
        # Setup continuation signal with be_after_tp1=True
        # Execute trade
        # Send candle that hits TP1
        # Verify: SL moved to entry_price, trade still active
        # Verify: Now monitoring for TP2
    
    def test_tp2_hit_closes_trade_after_tp1(self):
        """TP2 hit should close trade after TP1."""
        # Setup continuation signal with TP2
        # Execute trade, hit TP1 (moves to BE)
        # Send candle that hits TP2
        # Verify: Trade closed at TP2, exit_reason="TP2_HIT"
    
    def test_static_mode_unaffected_by_changes(self):
        """Static mode continues to work as before."""
        # Setup FADE signal (static mode)
        # Execute trade
        # Hit TP1 -> should close immediately
        # Verify: NO BE move, NO TP2 monitoring
```

### GREEN - Implement minimal code to pass

### REFACTOR - Clean up

---

## Files to Update (Phase 2/3)

1. `services/shared/src/scp_shared/execution/types.py`
   - Add tp_mode, tp2_price, tp1_hit, be_moved to TradeRecord

2. `services/execution/src/execution_svc/trade_manager.py`
   - Update execute_entry() to capture TP plan fields
   - Update _check_trade_exit() for TP1/TP2 logic
   - Add _check_tp_hit() helper
   - Add _move_sl_to_be() helper

3. `services/execution/src/execution_svc/trade_repository.py`
   - Add update_tp1_hit() method
   - Add update_sl_price() method
   - Add update_be_moved() method

4. `services/execution/tests/unit/test_continuation_execution.py` (new)
   - Test TP1 hit → BE move
   - Test TP2 monitoring
   - Test backward compatibility

5. `infra/migrations/009_add_continuation_fields.sql` (optional)
   - ALTER TABLE trades ADD COLUMN tp_mode
   - ALTER TABLE trades ADD COLUMN tp2_price
   - ALTER TABLE trades ADD COLUMN tp1_hit
   - ALTER TABLE trades ADD COLUMN be_moved

---

## Example: Full Continuation Flow (Future)

### Signal Generated (Bot-Core):
```
TP1: 2665.0 (1.5R)
TP2: 2700.0 (5R potential)
be_after_tp1: True
```

### Execution Flow (Phase 2/3):
1. **Entry**: Open at 2650.0, SL=2640.0, monitoring TP1=2665.0
2. **TP1 Hit**: Price reaches 2665.0
   - Log: "TP1 hit @ 2665.0 (1.5R profit)"
   - Action: Move SL to 2650.0 (BE)
   - Update: tp1_hit=True, be_moved=True
   - Continue: Monitor TP2=2700.0
3. **TP2 Hit**: Price reaches 2700.0
   - Exit: "TP2_HIT" @ 2700.0
   - Realized: 5R profit
4. **Alternative - Invalidation**: Price reverses to BE
   - Exit: "SL_HIT_BE" @ 2650.0
   - Realized: 0R (breakeven, capital protected)

---

## Migration Path

### Option A: Incremental (Recommended)
1. Ship bot-core changes NOW (backward compatible)
2. Implement Phase 2 (TP2 monitoring) in next sprint
3. Implement Phase 3 (BE move) concurrently with Phase 2
4. Implement Phase 4 (partials) later if needed

### Option B: Complete Feature
- Wait to ship until execution fully implemented
- Requires ~300 lines + tests in execution service
- Longer development cycle

**Recommendation**: **Option A** - Ship now, iterate

---

## Backward Compatibility Guarantee

Current execution service behavior:
```python
# Receives signal with new fields
signal = SignalMessage(
    tp_price=2665.0,        # TP1 - USED
    tp_mode="continuation", # NEW - IGNORED
    tp2_price=2700.0,       # NEW - IGNORED
    be_after_tp1=True,      # NEW - IGNORED
    # ...
)

# Creates trade
trade = TradeRecord(
    tp_price=signal.tp_price,  # 2665.0 (TP1)
    # Ignores tp2_price, be_after_tp1
)

# Monitors and exits
# ✅ Exits at TP1 (2665.0)
# ❌ Doesn't monitor TP2
# ❌ Doesn't move to BE
```

**Result**: Works correctly but doesn't capture full continuation potential.

---

## Decision Matrix

| Scenario | Current Behavior | With Phase 2/3 | Impact |
|----------|------------------|----------------|--------|
| VWAP_FADE | Exit at 3R TP | Exit at 3R TP | ✅ No change |
| VWAP_RECLAIM A+ (1.5R TP1) | Exit at 1.5R | Exit at 1.5R, move to BE, monitor TP2 | ⚠️ Current captures 1.5R, future captures up to 5R |
| VWAP_RECLAIM A+ (3R+ available) | Exit at 3R+ | Exit at TP1, move to BE, monitor TP2 | ⚠️ Current uses higher TP1, future uses staged |

---

## Testing Requirements (When Implementing Phase 2/3)

### Unit Tests:
- [ ] TP1 hit moves SL to BE (continuation mode)
- [ ] TP1 hit closes trade (no TP2 provided)
- [ ] TP2 hit closes trade after TP1
- [ ] Invalidation after TP1 exits at BE (not SL)
- [ ] Static mode unaffected (no BE move, no TP2)
- [ ] Database persistence of tp1_hit, be_moved flags
- [ ] Trade recovery restores TP2 monitoring state

### Integration Tests:
- [ ] Full continuation flow: signal → entry → TP1 → BE → TP2
- [ ] Full continuation flow: signal → entry → TP1 → BE → invalidation (exits at BE)
- [ ] Static mode flow unchanged

---

## Estimated Effort (Phase 2/3)

**Implementation**: 
- Code: ~250 lines
- Tests: ~300 lines
- Migration: 1 SQL file

**Time**: 1-2 days with TDD approach

**Complexity**: Medium (state tracking, DB updates, edge cases)

---

## Immediate Action Items

### For Current Deployment:
1. ✅ **Deploy bot-core changes** - Fully tested, backward compatible
2. ✅ **Document execution limitations** - This guide
3. ✅ **Monitor TP1 exits** - Track continuation signals exiting early

### For Next Sprint:
1. 🔲 **Create execution service ticket** - Link to this guide
2. 🔲 **Write TDD plan** - RED-GREEN-REFACTOR for Phases 2/3
3. 🔲 **Implement TP2 + BE logic** - Follow continuation flow

---

## Summary

**Question**: Do we need to change execution service?

**Answer**: 
- **Technically**: No, it won't break ✅
- **Functionally**: Yes, for full SOP compliance ⚠️

**Current State**: Bot-core is SOP-compliant, execution is partially compliant

**Recommendation**: Ship bot-core now, update execution in next sprint to capture full continuation potential

---

## Quick Check Commands

```bash
# Verify bot-core works (should pass)
cd services/bot-core
poetry run pytest tests/unit/ -v

# Verify execution still works (should pass)
cd services/execution
poetry run pytest tests/unit/ -v

# Verify integration works (should pass)
cd /Users/shalev/Code/SCP
poetry run pytest tests/integration/test_signals_to_trades.py -v
```

All should pass with current implementation.
