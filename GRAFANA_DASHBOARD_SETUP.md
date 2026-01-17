# Grafana Operations Dashboard Setup

**Status:** ✅ Complete  
**Date:** January 16, 2026

## Overview

Complete Grafana dashboard implementation for the Shir Capital Trading System with 25 panels across 6 rows, following the specification in `shir_capital_grafana_operations_dashboard.md`.

---

## Files Created

### Docker Infrastructure

**Modified:** `infra/docker-compose.infra.yml`
- Added Grafana service on port 3000
- Configured auto-provisioning with mounted volumes
- Added health check and proper dependencies

### Grafana Provisioning

**Created:** `infra/grafana/provisioning/datasources/prometheus.yml`
- Auto-configures Prometheus as default datasource
- Connection to `prometheus:9090` (Docker internal network)
- 15s scrape interval, 30s query timeout

**Created:** `infra/grafana/provisioning/dashboards/default.yml`
- Auto-loads dashboards from `/var/lib/grafana/dashboards`
- 10s update interval
- Allows UI updates for customization

### Operations Dashboard

**Created:** `infra/grafana/dashboards/operations.json`
- Complete dashboard with all 25 panels
- 6 rows: Safety Status, Market Data, Signals, Execution, Risk, Debug
- Global `$mode` variable (dev/test/replay/paper/live)
- 5s refresh rate for live monitoring
- Proper color thresholds (red/orange/green)

---

## Dashboard Structure

### Row 1 - Global Safety Status (Always Visible)
- Panel 1: Trading Enabled (0=green DISABLED, 1=red ENABLED)
- Panel 2: Unsafe State / Kill Switch (0=green SAFE, >0=red UNSAFE)
- Panel 3: Execution Service Up (1=green UP, 0=red DOWN)
- Panel 4: Trading Halt Reason (NONE=green, else=red with reason name)
- Panel 5: Enforcer Tier (Conservative/Early Mild/Mild/Offensive)

### Row 2 - Market Data Health
- Panel 6: Market Data Lag (time series, <0.5s threshold)
- Panel 7: Data Provider Connected (1=green, 0=red per provider)
- Panel 8: Data Gaps Last 5m (0=green, >0=red)

### Row 3 - Signal Flow & SOP Quality
- Panel 9: Signals Generated Rate (time series, signals/min)
- Panel 10: Signal Rejection Reasons (pie chart, stacked by reason)
- Panel 11: A+ Quality Gate (>=8.0=green, <8.0=red)
- Panel 12: Signal Generation Latency p95 (time series)

### Row 4 - Execution & Orders (Money Zone)
- Panel 13: Orders Sent vs Filled (time series, blue=sent, green=filled)
- Panel 14: Order Rejections (stacked bar chart by reason)
- Panel 15: Execution Latency p95 (time series, ack + fill)

### Row 5 - Positions & Risk
- Panel 16: Open Positions (<=1=green, >1=red)
- Panel 17: Daily PnL (time series with min/max/last)
- Panel 18: Daily Drawdown (gauge, <300=green, 300-480=orange, >480=red)

### Row 6 - Debug / Secondary (Collapsed by Default)
- Panel 19: HTF Bias Current (gauge, 1=bullish, 0=neutral, -1=bearish)
- Panel 20: HTF Bias Change Frequency (>4/hour=choppy, <2/hour=trending)
- Panel 21: Loss Streak Current (0=green, 1=orange, >=2=red)
- Panel 22: Redis Connectivity (1=green CONNECTED, 0=red DISCONNECTED)
- Panel 23: Event Processing Latency p95 (by service)
- Panel 24: Database Query Latency p95 (by service and operation, >1s=alert)
- Panel 25: Feature Queue Depth (0-10=green, 10-50=orange, >50=red)

---

## Quick Start

### 1. Start Infrastructure

```bash
cd infra
docker-compose -f docker-compose.infra.yml up -d
```

This starts:
- Redis (port 6379)
- PostgreSQL/TimescaleDB (port 5432)
- Prometheus (port 9090)
- **Grafana (port 3000)**

### 2. Access Grafana

1. Open browser: http://localhost:3000
2. Login credentials:
   - Username: `admin`
   - Password: `admin` (or `$GRAFANA_PASSWORD` env var)
3. Dashboard auto-loads: "SCP Operations Dashboard"

### 3. Select Mode

Use the dropdown at the top to select environment:
- `dev` - Development mode
- `test` - Testing mode
- `replay` - Replay/backtest mode
- `paper` - Paper trading
- `live` - Live trading (production)

### 4. Start Services (Optional)

To see live data, start the microservices:

```bash
# Start all services
docker-compose -f docker-compose.infra.yml \
               -f docker-compose.services.yml up -d
```

---

## Dashboard Features

### Auto-Provisioning

- Dashboard automatically loads on Grafana startup
- Prometheus datasource auto-configured
- No manual import required

### Global Variables

- **$mode**: Filter all panels by environment (dev/test/replay/paper/live)
- Consistent filtering across all 25 panels

### Color Coding

Following the spec's visual rules:
- **Green (#73BF69)**: OK - normal operation
- **Orange (#FF9830)**: WATCH - warnings
- **Red (#E02F44)**: STOP TRADING - critical failures
- Blue: Informational (non-critical)

### Refresh Rate

- Default: 5 seconds (suitable for live trading)
- Adjustable via dashboard controls
- Time range: Last 6 hours (default)

---

## Panel Query Examples

### Trading Halt Reason (Panel 4)

```promql
max by (reason) (scp_trading_halt_reason{mode="$mode"} == 1)
```

Shows which halt reason is active (returns reason label where value=1).

### A+ Quality Gate (Panel 11)

```promql
avg(scp_signal_score{mode="$mode"})
```

Average signal score. Must be >=8.0 for A+ quality.

### Daily Drawdown (Panel 18)

```promql
scp_daily_drawdown{mode="$mode"}
```

Current daily drawdown. Thresholds at 50% and 80% of PDLL (600 points).

### Orders Sent vs Filled (Panel 13)

```promql
rate(scp_orders_sent_total{mode="$mode"}[1m]) * 60
rate(scp_orders_filled_total{mode="$mode"}[1m]) * 60
```

Orders per minute. Sent should match filled (any gap = rejections).

---

## Troubleshooting

### Dashboard Not Loading

Check Grafana logs:
```bash
docker logs scp-grafana
```

Ensure provisioning directories are mounted correctly:
```bash
docker exec scp-grafana ls -la /etc/grafana/provisioning/datasources
docker exec scp-grafana ls -la /var/lib/grafana/dashboards
```

### No Data in Panels

1. **Check Prometheus is scraping:**
   - Open http://localhost:9090/targets
   - Verify all 5 services show "UP"

2. **Check services are running:**
   ```bash
   docker ps | grep scp-
   ```

3. **Verify metrics endpoint:**
   ```bash
   curl http://localhost:8005/metrics | grep scp_
   ```

### Wrong Mode Selected

- Use the `$mode` dropdown at the top of the dashboard
- Ensure services are started with correct `SERVICE_MODE` env var:
  ```bash
  docker-compose -f docker-compose.infra.yml \
                 -f docker-compose.services.yml \
                 -f docker-compose.dev.yml up -d
  ```

---

## Customization

The dashboard allows UI updates (`allowUiUpdates: true` in provisioning), so you can:

1. Adjust panel sizes and positions
2. Modify thresholds
3. Change colors
4. Add annotations
5. Adjust time ranges

Changes persist in Grafana's database (`grafana_data` volume).

To reset to original:
1. Stop Grafana: `docker-compose -f docker-compose.infra.yml stop grafana`
2. Remove volume: `docker volume rm scp_grafana_data`
3. Restart: `docker-compose -f docker-compose.infra.yml up -d grafana`

---

## Production Considerations

### Security

For production deployment:

1. **Change default password:**
   ```bash
   export GRAFANA_PASSWORD="your-secure-password"
   ```

2. **Enable HTTPS:**
   - Add reverse proxy (nginx/Caddy) in front of Grafana
   - Configure SSL certificates

3. **Restrict access:**
   - Use firewall rules to limit port 3000 access
   - Configure Grafana authentication (LDAP, OAuth, etc.)

### High Availability

- Use external PostgreSQL for Grafana's database
- Configure Grafana clustering for multiple instances
- Use external Prometheus with federation

### Alerting

Grafana can send alerts based on panel queries:

1. Edit panel
2. Click "Alert" tab
3. Configure alert rules and notification channels
4. Mirror dashboard logic 1:1 (per spec requirement)

---

## Architecture Diagram

```
┌─────────────┐
│ Services    │ → /metrics → ┌────────────┐
│ (8001-8005) │              │ Prometheus │
└─────────────┘              │   :9090    │
                             └──────┬─────┘
                                    │ datasource
                             ┌──────▼─────┐
                             │  Grafana   │
                             │   :3000    │
                             └────────────┘
                                    │
                             ┌──────▼─────┐
                             │  Browser   │
                             │ Dashboard  │
                             └────────────┘
```

---

## Next Steps

1. ✅ Infrastructure deployed
2. ✅ Dashboard auto-provisioned
3. ⏳ Test with live services
4. ⏳ Configure alerts (mirror dashboard logic)
5. ⏳ Add annotations for key events (session open, trades, kill switch)
6. ⏳ Production security hardening

---

## References

- [Dashboard Spec](shir_capital_grafana_operations_dashboard.md)
- [Metrics Implementation](GRAFANA_DASHBOARD_METRICS_IMPLEMENTATION.md)
- [Prometheus Config](infra/prometheus/prometheus.yml)
- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
