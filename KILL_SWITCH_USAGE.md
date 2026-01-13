# Kill Switch Usage Guide

## Overview

The kill switch provides emergency halt capability for the trading system. When activated, it immediately stops new trading activity while maintaining safety for active positions.

## Endpoints

### Execution Service (Port 8005)

```bash
# Activate kill switch
curl -X POST http://localhost:8005/admin/kill?reason="Emergency%20halt"

# Resume trading
curl -X POST http://localhost:8005/admin/resume

# Check status
curl http://localhost:8005/admin/status
```

### Bot Core Service (Port 8004)

```bash
# Activate kill switch
curl -X POST http://localhost:8004/admin/kill?reason="Emergency%20halt"

# Resume trading
curl -X POST http://localhost:8004/admin/resume

# Check status
curl http://localhost:8004/admin/status
```

## Behavior

### When Kill Switch is Activated

**Execution Service:**
- ✅ Continues monitoring active trades (SL/TP still work)
- ❌ Rejects all new signals from Bot Core
- 🚨 Logs warning for each rejected signal

**Bot Core Service:**
- ✅ Continues consuming features (stays in sync)
- ❌ Stops generating new signals
- 🚨 Logs debug message for each skipped signal

### State Persistence

Kill switch state persists in PostgreSQL (`kill_switch_state` table):
- Survives service restarts
- Independent per service (can kill one without affecting the other)
- Tracks who activated it and why

## Example Usage

### Emergency Halt (Both Services)

```bash
# Kill both services
curl -X POST http://localhost:8005/admin/kill?reason="PDLL%20hit%20manually"
curl -X POST http://localhost:8004/admin/kill?reason="PDLL%20hit%20manually"
```

### Partial Halt (Stop Signal Generation Only)

```bash
# Kill only Bot Core (stops signal generation)
# Execution continues to manage existing trades
curl -X POST http://localhost:8004/admin/kill?reason="Testing%20signal%20generation"
```

### Resume Trading

```bash
# Resume both services
curl -X POST http://localhost:8005/admin/resume
curl -X POST http://localhost:8004/admin/resume
```

## Health Check Integration

Kill switch status is NOT included in `/health` endpoints (to keep them simple).

Use `/admin/status` to check kill state:

```bash
curl http://localhost:8005/admin/status
# Returns:
# {
#   "service": "execution",
#   "is_killed": false,
#   "killed_at": null,
#   "killed_by": null,
#   "reason": null,
#   "updated_at": "2024-01-15T10:30:00Z"
# }
```

## Database Schema

```sql
CREATE TABLE kill_switch_state (
    service_name VARCHAR(50) PRIMARY KEY,
    is_killed BOOLEAN NOT NULL DEFAULT FALSE,
    killed_at TIMESTAMPTZ,
    killed_by VARCHAR(100),
    reason TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Testing

Run unit tests:

```bash
# Execution service
cd services/execution
poetry run pytest tests/unit/test_kill_switch.py -v

# Bot Core service
cd services/bot-core
poetry run pytest tests/unit/test_kill_switch.py -v
```

## Production Usage

1. **Monitor for critical events** (PDLL hit, loss streak, etc.)
2. **Activate kill switch** via API or monitoring system
3. **Investigate issue** while system is halted
4. **Resume trading** when issue is resolved

**Important:** Kill switch does NOT close existing positions automatically. Active trades continue to be monitored for SL/TP exits.
