# Grafana Operations Dashboard

This directory contains the Grafana configuration and dashboard for the SCP Trading System.

## Quick Start

```bash
# From the infra directory
cd /Users/shalev/Code/SCP/infra

# Start infrastructure (includes Grafana)
docker-compose -f docker-compose.infra.yml up -d

# Wait for Grafana to start (check logs)
docker logs -f scp-grafana

# Access dashboard
open http://localhost:3000
```

**Login:** admin / admin

The "SCP Operations Dashboard" will auto-load with all 25 panels.

## Directory Structure

```
grafana/
├── README.md                         # This file
├── dashboards/
│   └── operations.json               # Main operations dashboard (25 panels)
└── provisioning/
    ├── datasources/
    │   └── prometheus.yml            # Auto-configured Prometheus datasource
    └── dashboards/
        └── default.yml               # Dashboard auto-loader config
```

## Dashboard Overview

### Row 1 - Global Safety Status (5 panels)
- Trading Enabled
- Unsafe State (Kill Switch)
- Execution Service Up
- Trading Halt Reason
- Enforcer Tier

### Row 2 - Market Data Health (3 panels)
- Market Data Lag
- Data Provider Connected
- Data Gaps (Last 5m)

### Row 3 - Signal Flow & SOP Quality (4 panels)
- Signals Generated Rate
- Signal Rejection Reasons
- A+ Quality Gate
- Signal Generation Latency (p95)

### Row 4 - Execution & Orders (3 panels)
- Orders Sent vs Filled
- Order Rejections
- Execution Latency (p95)

### Row 5 - Positions & Risk (3 panels)
- Open Positions
- Daily PnL
- Daily Drawdown

### Row 6 - Debug / Secondary (7 panels, collapsed)
- HTF Bias Current
- HTF Bias Change Frequency
- Loss Streak Current
- Redis Connectivity
- Event Processing Latency (p95)
- Database Query Latency (p95)
- Feature Queue Depth

## Global Variables

- **$mode**: Environment selector (dev/test/replay/paper/live)
  - All panels filter by this variable
  - Select from dropdown at top of dashboard

## Color Coding

- **Green**: OK - normal operation
- **Orange**: WATCH - warnings
- **Red**: STOP TRADING - critical failures

## Troubleshooting

### Dashboard not loading?

Check provisioning:
```bash
docker exec scp-grafana ls -la /etc/grafana/provisioning/datasources
docker exec scp-grafana ls -la /var/lib/grafana/dashboards
```

### No data in panels?

1. Check Prometheus targets: http://localhost:9090/targets
2. Verify services are running: `docker ps | grep scp-`
3. Test metrics endpoint: `curl http://localhost:8005/metrics`

### Need to reset?

```bash
docker-compose -f docker-compose.infra.yml stop grafana
docker volume rm scp_grafana_data
docker-compose -f docker-compose.infra.yml up -d grafana
```

## More Information

See [GRAFANA_DASHBOARD_SETUP.md](../../GRAFANA_DASHBOARD_SETUP.md) for complete documentation.
