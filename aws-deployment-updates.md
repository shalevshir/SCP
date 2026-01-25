# SCP Trading System - AWS Cloud Deployment Updates

Instructions for updating your original implementation to run on AWS EC2.

---

## Overview of Changes

| Component | Original | AWS Cloud |
|-----------|----------|-----------|
| IB Gateway | Local install / manual | Docker container (gnzsnz/ib-gateway) |
| Infrastructure | Local Docker Compose | Same Docker Compose on EC2 |
| IB Connection | localhost:4001/4002 | Docker network: ib-gateway:4003/4004 |
| Access | Local browser | SSH tunnel + browser |

---

## Step 1: Add IB Gateway to docker-compose.infra.yml

Add the IB Gateway service to your existing `docker-compose.infra.yml`:

```yaml
# docker-compose.infra.yml - ADD THIS SERVICE

services:
  # ... existing postgres, redis, prometheus, grafana ...

  ib-gateway:
    image: ghcr.io/gnzsnz/ib-gateway:stable
    container_name: ib-gateway
    restart: always
    environment:
      TWS_USERID: ${IB_USERNAME}
      TWS_PASSWORD: ${IB_PASSWORD}
      TRADING_MODE: ${IB_TRADING_MODE:-paper}
      VNC_SERVER_PASSWORD: ${VNC_PASSWORD:-}
      TWOFA_TIMEOUT_ACTION: restart
      AUTO_RESTART_TIME: "11:59 PM"
      RELOGIN_AFTER_TWOFA_TIMEOUT: "yes"
      TIME_ZONE: ${TIME_ZONE:-America/New_York}
      READ_ONLY_API: "no"
      EXISTING_SESSION_DETECTED_ACTION: "primary"
    ports:
      - "127.0.0.1:5900:5900"
    expose:
      - "4003"
      - "4004"
    healthcheck:
      test: ["CMD-SHELL", "(echo > /dev/tcp/localhost/4004) 2>/dev/null || (echo > /dev/tcp/localhost/4003) 2>/dev/null || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s
```

---

## Step 2: Update docker-compose.services.yml

Modify your services to connect to IB Gateway via Docker network:

```yaml
# docker-compose.services.yml - UPDATED SECTIONS

services:
  data-adapter:
    environment:
      # UPDATED: Connect to IB Gateway container
      IB_HOST: ib-gateway
      IB_PORT: ${IB_PORT:-4004}  # 4004 for paper, 4003 for live
      IB_CLIENT_ID: 1
    depends_on:
      ib-gateway:  # ADDED
        condition: service_healthy
    # ... rest of config

  execution:
    environment:
      # UPDATED: Connect to IB Gateway container
      IB_HOST: ib-gateway
      IB_PORT: ${IB_PORT:-4004}
      IB_CLIENT_ID: 2
    depends_on:
      ib-gateway:  # ADDED
        condition: service_healthy
    # ... rest of config
```

---

## Step 3: Update docker-compose.trader-dashboard.yml

```yaml
# docker-compose.trader-dashboard.yml - UPDATED

services:
  data-adapter:
    environment:
      SERVICE_MODE: dashboard
      IB_HOST: ib-gateway
      IB_PORT: 4004
```

---

## Step 4: Update .env File

Add IB Gateway settings to your `.env`:

```bash
# =============================================================================
# IB Gateway Configuration (ADD THESE)
# =============================================================================
IB_USERNAME=your_ib_username
IB_PASSWORD=your_ib_password
IB_TRADING_MODE=paper
IB_PORT=4004
VNC_PASSWORD=your_vnc_password
TIME_ZONE=America/New_York
```

**Set secure permissions:**
```bash
chmod 600 .env
```

---

## Step 5: Startup Command

```bash
cd /home/ec2-user/SCP/infra

# Start everything
docker-compose \
  -f docker-compose.infra.yml \
  -f docker-compose.services.yml \
  -f docker-compose.trader-dashboard.yml \
  up -d --build

# View logs
docker-compose \
  -f docker-compose.infra.yml \
  -f docker-compose.services.yml \
  -f docker-compose.trader-dashboard.yml \
  logs -f
```

---

## Step 6: Verify Deployment

```bash
# Check all containers
docker ps

# Check IB Gateway logs
docker logs -f ib-gateway
# Look for: "Login has completed" and "IBKR Gateway; event=Opened"

# Check service health
for port in 8001 8002 8003 8004; do
  echo "Port $port: $(curl -s http://localhost:$port/health)"
done
```

---

## Step 7: VNC for IB Gateway 2FA

```bash
# Create SSH tunnel (local machine)
ssh -L 5900:localhost:5900 -i ~/.ssh/id_rsa ec2-user@YOUR_EC2_IP

# Connect VNC client to localhost:5900
# Mac: Finder → Go → Connect to Server → vnc://localhost:5900
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start services | `docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.trader-dashboard.yml up -d --build` |
| Stop services | `docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.trader-dashboard.yml down` |
| View logs | `docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.trader-dashboard.yml logs -f` |
| IB Gateway logs | `docker logs -f ib-gateway` |
| Restart IB Gateway | `docker restart ib-gateway` |
| VNC tunnel | `ssh -L 5900:localhost:5900 -i ~/.ssh/id_rsa ec2-user@YOUR_EC2_IP` |
| Grafana tunnel | `ssh -L 3000:localhost:3000 -i ~/.ssh/id_rsa ec2-user@YOUR_EC2_IP` |

---

## IB Gateway Port Reference

| Port | Connection | Purpose |
|------|------------|---------|
| `ib-gateway:4003` | Docker network | Live trading API |
| `ib-gateway:4004` | Docker network | Paper trading API |
| `localhost:5900` | SSH tunnel | VNC for 2FA |

---

## Switching Modes

| Mode | IB_TRADING_MODE | IB_PORT |
|------|-----------------|---------|
| Dashboard (Stage 1) | paper | 4004 |
| Paper Trading (Stage 2) | paper | 4004 |
| Live Trading (Stage 3) | live | 4003 |
