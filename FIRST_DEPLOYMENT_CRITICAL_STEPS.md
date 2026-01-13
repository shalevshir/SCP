# First Deployment: Critical Steps Only

**Goal:** Deploy the system safely for paper trading with live data, ensuring we can halt trading immediately if needed.

**Status:** Ready to start  
**Estimated Duration:** 1-2 weeks  
**Priority:** 🔴 Critical

---

## Current State

✅ **Complete:**
- All 5 services implemented and integrated
- Databento live data integration
- PaperBroker implementation
- Integration tests and parity validation
- State persistence and recovery
- Health checks

❌ **Missing (Critical for First Deployment):**
- Kill switch to halt trading
- Broker mode enforcement (prevent accidental live trading)
- Basic monitoring/alerts for critical failures

---

## Critical Steps

### Step 1: Kill Switch Implementation 🔴 CRITICAL

**Why:** Must be able to halt all trading immediately in case of system malfunction or unexpected behavior.

**Tasks:**
1. **Execution Service Kill Switch**
   - `POST /admin/kill` - Immediately stops processing new signals
   - `POST /admin/resume` - Resumes signal processing
   - Kill state persists in database (survives restarts)
   - Kill state exposed in `/health` endpoint
   - When killed: reject all new signals, optionally close all positions

2. **Bot Core Kill Switch**
   - `POST /admin/kill` - Stops signal generation
   - `POST /admin/resume` - Resumes signal generation
   - Kill state persists in database
   - When killed: stop consuming features and generating signals

**Acceptance Criteria:**
- Kill switch stops trading within 1 second
- Kill state persists across service restarts
- Health check shows kill status
- Clear logging when kill switch activated

**Files to Modify:**
- `services/execution/src/execution_svc/main.py` - Add kill switch endpoints
- `services/bot-core/src/bot_core_svc/main.py` - Add kill switch endpoints
- `services/shared/src/scp_shared/database/repositories.py` - Add kill state table (or use existing daily_state)

---

### Step 2: Broker Mode Enforcement 🔴 CRITICAL

**Why:** Prevent accidental live trading. First deployment must be paper-only.

**Tasks:**
1. **Use broker_mode config**
   - Modify `services/execution/src/execution_svc/main.py` to use `config.broker_mode`
   - Create broker factory function:
     ```python
     def create_broker(mode: str) -> BaseBroker:
         if mode == "paper":
             return PaperBroker()
         elif mode == "live":
             raise ValueError("Live trading not enabled for first deployment")
         else:
             raise ValueError(f"Invalid broker_mode: {mode}")
     ```

2. **Environment Variable Validation**
   - Fail fast if `BROKER_MODE` is not set or invalid
   - Log clearly which mode is active at startup
   - Add to health check: show current broker mode

3. **Safety Guard: Force Paper Mode**
   - For first deployment, hardcode or validate that `BROKER_MODE=paper`
   - Add explicit check: if live mode attempted, raise error

**Acceptance Criteria:**
- System fails to start if `BROKER_MODE` is not "paper"
- Clear logging shows "PAPER MODE ACTIVE" at startup
- Health check shows broker mode
- Attempting live mode raises clear error

**Files to Modify:**
- `services/execution/src/execution_svc/main.py` - Use config.broker_mode
- `services/execution/src/execution_svc/config.py` - Validate broker_mode

---

### Step 3: Basic Critical Alerts 🟡 HIGH

**Why:** Need to know immediately if system fails or critical limits are hit.

**Tasks:**
1. **PDLL Alert**
   - When daily loss limit hit, send alert (log + optional email/Slack)
   - Alert includes: current P&L, loss streak, time of day

2. **Service Crash Alert**
   - If any service crashes/restarts, log critical error
   - Health check failures should be visible

3. **Kill Switch Alert**
   - When kill switch activated, send immediate alert
   - Include: who activated it, timestamp, reason (if provided)

**Acceptance Criteria:**
- PDLL hit generates alert (at minimum, structured log)
- Service crashes are logged with full context
- Kill switch activation is immediately visible

**Implementation Notes:**
- Start with structured logging (JSON format)
- Can add email/Slack integration later
- Use existing logger from `scp_shared.common.get_logger()`

**Files to Modify:**
- `services/execution/src/execution_svc/trade_manager.py` - Add PDLL alert
- `services/execution/src/execution_svc/main.py` - Add kill switch alert
- `services/bot-core/src/bot_core_svc/main.py` - Add kill switch alert

---

### Step 4: Paper Trading Validation Setup 🟡 HIGH

**Why:** Must validate system behavior with live data before considering live trading.

**Tasks:**
1. **Production-Like Paper Environment**
   - Deploy all services with live Databento data
   - Use `BROKER_MODE=paper`
   - Run for minimum 1 week continuously
   - Monitor: signals, trades, P&L, system stability

2. **Validation Checklist**
   - [ ] System runs 7 days without crashes
   - [ ] Signal generation matches backtester expectations
   - [ ] Trades execute correctly (entry, SL, TP, invalidation)
   - [ ] Kill switch works and is tested
   - [ ] State recovery works after restart
   - [ ] No data loss during failures

3. **Daily Validation Report**
   - Generate daily summary: signals, trades, P&L, errors
   - Compare to backtester expectations
   - Track system uptime

**Acceptance Criteria:**
- System runs continuously for 7+ days
- All validation criteria met
- Daily reports show expected behavior

**Files to Create:**
- `scripts/generate_daily_report.py` - Daily validation report
- `docs/paper_trading_validation.md` - Validation checklist

---

## Implementation Order

```
Week 1:
  Day 1-2: Step 1 (Kill Switch)
  Day 3:   Step 2 (Broker Mode Enforcement)
  Day 4:   Step 3 (Basic Alerts)
  Day 5:   Integration testing of all safety features

Week 2:
  Day 1:   Step 4 setup (Paper trading environment)
  Day 2-7: Run paper trading validation
```

---

## Success Criteria for First Deployment

Before going live, ALL of these must be true:

1. ✅ Kill switch implemented and tested
2. ✅ Broker mode enforcement prevents live trading
3. ✅ Basic alerts notify on critical events
4. ✅ Paper trading runs 7+ days without issues
5. ✅ System recovers correctly from failures
6. ✅ Daily validation reports show expected behavior

---

## What's NOT Included (Can Wait)

These are important but not critical for first deployment:

- ❌ Full Prometheus metrics (health checks are sufficient initially)
- ❌ Distributed tracing (logging is sufficient initially)
- ❌ Real broker integration (paper trading only for first deployment)
- ❌ Advanced monitoring dashboards (logs + health checks sufficient)
- ❌ Runtime config updates (can redeploy for config changes)
- ❌ Data retention policies (can add later)

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Accidental live trading | Broker mode enforcement + validation |
| System malfunction | Kill switch + alerts |
| Data loss | State persistence already implemented |
| Service crashes | Health checks + restart policies |
| Unexpected behavior | Paper trading validation period |

---

## Next Steps After First Deployment

Once paper trading validation is successful:

1. **Epic 4**: Real broker integration (Interactive Brokers)
2. **Epic 2**: Full observability (Prometheus, Grafana, tracing)
3. **Epic 5**: Advanced production features (runtime config, retention policies)
4. **Go-Live**: With conservative limits and monitoring
