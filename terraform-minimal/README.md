# SCP Trader Dashboard - Minimal AWS Deployment

Cost-optimized deployment for the Trader Dashboard stage: **~$22-37/month** (or ~$12-17 with Spot instances).

## Cost Comparison

| Option | Monthly Cost | Notes |
|--------|--------------|-------|
| Full production (ECS + RDS + ElastiCache) | ~$200 | High availability |
| **Single EC2 On-Demand** | **~$22-37** | Simple, reliable |
| Single EC2 Spot | ~$12-17 | 70% cheaper, can be interrupted |

## Two Deployment Options

### Option 1: Terraform (Recommended)

Automated setup with proper security groups and elastic IP.

```bash
# 1. Configure
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars  # Add your IB credentials and IP

# 2. Deploy
terraform init
terraform apply

# 3. Follow the output instructions
```

### Option 2: Manual EC2 + Script

If you prefer to manually create the EC2 instance:

1. **Launch EC2 in AWS Console:**
   - AMI: Amazon Linux 2023
   - Instance type: t3.small ($15/mo) or t3.medium ($30/mo)
   - Storage: 30GB gp3
   - Security group: Allow ports 22, 3000, 5900 from your IP

2. **SSH and run setup script:**
   ```bash
   ssh -i your-key.pem ec2-user@YOUR_IP
   
   # Download and run setup
   curl -sSL https://raw.githubusercontent.com/YOUR_REPO/setup-ec2.sh > setup.sh
   chmod +x setup.sh
   
   # Set credentials
   export IB_USERNAME="your_username"
   export IB_PASSWORD="your_password"
   export GRAFANA_PASSWORD="your_password"
   
   ./setup.sh
   ```

## Instance Size Recommendations

| Stage | Instance | RAM | Cost | Notes |
|-------|----------|-----|------|-------|
| Dashboard only | t3.small | 2GB | $15/mo | 4 services + infra |
| Paper trading | t3.medium | 4GB | $30/mo | 5 services + infra |
| Live trading | t3.medium+ | 4GB+ | $30+/mo | Consider production setup |

## What's Running on the Instance

```
┌─────────────────────────────────────────────────┐
│              EC2 Instance (t3.small)            │
│                                                 │
│  Docker Compose:                                │
│  ├── PostgreSQL     (container)                 │
│  ├── Redis          (container)                 │
│  ├── Prometheus     (container)                 │
│  ├── Grafana        (container)                 │
│  ├── data-adapter   (container)                 │
│  ├── feature-engine (container)                 │
│  ├── htf-bias       (container)                 │
│  └── bot-core       (container)                 │
│                                                 │
│  Native Services:                               │
│  ├── Xvfb           (virtual display)           │
│  ├── x11vnc         (VNC server for IB 2FA)     │
│  └── IB Gateway     (via IBC)                   │
└─────────────────────────────────────────────────┘
```

## Weekly IB Gateway 2FA

IB Gateway requires re-authentication every week:

```bash
# Create SSH tunnel
ssh -L 5900:localhost:5900 ec2-user@YOUR_IP

# Connect VNC client to localhost:5900
# Complete 2FA in the IB Gateway GUI
```

## Upgrading to Production

When you're ready for paper/live trading with high availability:

1. Use the full Terraform setup in `terraform-aws-scp.zip`
2. Or migrate to managed services:
   - PostgreSQL → RDS
   - Redis → ElastiCache
   - Services → ECS Fargate

## Files

| File | Purpose |
|------|---------|
| `main.tf` | Terraform configuration (single EC2) |
| `terraform.tfvars.example` | Configuration template |
| `setup-ec2.sh` | Manual setup script (no Terraform) |

## Troubleshooting

### IB Gateway won't start
```bash
# Check logs
sudo journalctl -u ibgateway -f

# Restart services
sudo systemctl restart xvfb x11vnc ibgateway
```

### Docker services not running
```bash
cd /opt/scp/infra
docker-compose -f docker-compose.infra.yml \
  -f docker-compose.services.yml \
  -f docker-compose.trader-dashboard.yml logs -f
```

### Can't connect to Grafana
- Check security group allows port 3000 from your IP
- Verify containers are running: `docker ps`
