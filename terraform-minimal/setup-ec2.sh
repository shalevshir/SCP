#!/bin/bash
# =============================================================================
# SCP Trader Dashboard - Quick Setup Script
# =============================================================================
#
# For manual EC2 setup without Terraform
#
# Prerequisites:
#   - EC2 instance (t3.small or larger, Amazon Linux 2023 or Ubuntu 22.04)
#   - Security group allowing: 22 (SSH), 3000 (Grafana), 5900 (VNC)
#   - Your SCP repository
#
# Usage:
#   1. Launch EC2 manually in AWS Console
#   2. SSH to the instance
#   3. Run: curl -sSL https://raw.githubusercontent.com/YOUR_REPO/setup.sh | bash
#   Or:
#   4. Copy this script and run: chmod +x setup.sh && ./setup.sh
#
# Cost: t3.small = ~$15/month, t3.medium = ~$30/month

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# -----------------------------------------------------------------------------
# Configuration - EDIT THESE
# -----------------------------------------------------------------------------

IB_USERNAME="${IB_USERNAME:-}"
IB_PASSWORD="${IB_PASSWORD:-}"
IB_TRADING_MODE="${IB_TRADING_MODE:-paper}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9')}"
SCP_REPO="${SCP_REPO:-}"  # Your git repo URL

# -----------------------------------------------------------------------------
# Detect OS
# -----------------------------------------------------------------------------

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    log_error "Cannot detect OS"
    exit 1
fi

log_info "Detected OS: $OS"

# -----------------------------------------------------------------------------
# Install Dependencies
# -----------------------------------------------------------------------------

log_info "Installing dependencies..."

if [[ "$OS" == "amzn" ]]; then
    # Amazon Linux 2023
    sudo dnf update -y
    sudo dnf install -y docker git java-11-amazon-corretto-headless \
        xorg-x11-server-Xvfb x11vnc unzip curl
elif [[ "$OS" == "ubuntu" ]]; then
    # Ubuntu
    sudo apt-get update
    sudo apt-get install -y docker.io git openjdk-11-jre-headless \
        xvfb x11vnc unzip curl
else
    log_error "Unsupported OS: $OS"
    exit 1
fi

# Start Docker
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER

# Install Docker Compose
log_info "Installing Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# -----------------------------------------------------------------------------
# Create Directory Structure
# -----------------------------------------------------------------------------

log_info "Creating directory structure..."

sudo mkdir -p /opt/scp/{infra,services,config,data}
sudo mkdir -p /opt/scp/data/{postgres,redis,grafana,prometheus}
sudo chown -R $USER:$USER /opt/scp

# -----------------------------------------------------------------------------
# Clone Repository (if provided)
# -----------------------------------------------------------------------------

if [ -n "$SCP_REPO" ]; then
    log_info "Cloning repository..."
    git clone "$SCP_REPO" /opt/scp/repo
    cp -r /opt/scp/repo/* /opt/scp/
fi

# -----------------------------------------------------------------------------
# Create Environment File
# -----------------------------------------------------------------------------

log_info "Creating environment file..."

cat > /opt/scp/.env << EOF
# SCP Trading System Environment
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
GRAFANA_PASSWORD=$GRAFANA_PASSWORD
SERVICE_MODE=dashboard
IB_TRADING_MODE=$IB_TRADING_MODE
EOF

chmod 600 /opt/scp/.env

log_info "Environment file created at /opt/scp/.env"
log_info "PostgreSQL password: $POSTGRES_PASSWORD"

# -----------------------------------------------------------------------------
# Install IB Gateway + IBC
# -----------------------------------------------------------------------------

log_info "Installing IB Gateway..."

cd /tmp

# Download IB Gateway
wget -q "https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh" \
    -O ibgateway-installer.sh
chmod +x ibgateway-installer.sh
./ibgateway-installer.sh -q -dir /opt/scp/ibgateway

# Download IBC
IBC_VERSION="3.18.0"
wget -q "https://github.com/IbcAlpha/IBC/releases/download/$IBC_VERSION/IBCLinux-$IBC_VERSION.zip" -O ibc.zip
unzip -q ibc.zip -d /opt/scp/ibc
chmod +x /opt/scp/ibc/*.sh

# Create IBC config (will need manual editing for credentials)
cat > /opt/scp/ibc/config.ini << EOF
# IBC Configuration
# Edit this file with your IB credentials

IbLoginId=$IB_USERNAME
IbPassword=$IB_PASSWORD
TradingMode=$IB_TRADING_MODE
IbDir=/opt/scp/ibgateway
AcceptIncomingConnectionAction=accept
AcceptNonBrokerageAccountWarning=yes
AllowBlindTrading=yes
DismissPasswordExpiryWarning=yes
ExistingSessionDetectedAction=primary
MinimizeMainWindow=yes
EOF

chmod 600 /opt/scp/ibc/config.ini

# -----------------------------------------------------------------------------
# Create Systemd Services
# -----------------------------------------------------------------------------

log_info "Creating systemd services..."

# Xvfb
sudo tee /etc/systemd/system/xvfb.service > /dev/null << 'EOF'
[Unit]
Description=X Virtual Frame Buffer
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/Xvfb :1 -screen 0 1024x768x24
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# x11vnc
sudo tee /etc/systemd/system/x11vnc.service > /dev/null << 'EOF'
[Unit]
Description=VNC Server
After=xvfb.service
Requires=xvfb.service

[Service]
Type=simple
User=root
Environment=DISPLAY=:1
ExecStart=/usr/bin/x11vnc -display :1 -forever -shared -rfbport 5900 -nopw
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# IB Gateway
sudo tee /etc/systemd/system/ibgateway.service > /dev/null << 'EOF'
[Unit]
Description=Interactive Brokers Gateway
After=xvfb.service
Requires=xvfb.service

[Service]
Type=simple
User=root
Environment=DISPLAY=:1
WorkingDirectory=/opt/scp/ibc
ExecStart=/opt/scp/ibc/gatewaystart.sh -g /opt/scp/ibc/config.ini
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

# SCP Docker Compose
sudo tee /etc/systemd/system/scp.service > /dev/null << 'EOF'
[Unit]
Description=SCP Trading System
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/scp/infra
ExecStart=/usr/local/bin/docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.trader-dashboard.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.infra.yml -f docker-compose.services.yml -f docker-compose.trader-dashboard.yml down

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload

# Start Xvfb and VNC (but not IB Gateway yet - needs credential config)
sudo systemctl enable xvfb x11vnc
sudo systemctl start xvfb
sleep 2
sudo systemctl start x11vnc

# -----------------------------------------------------------------------------
# Print Summary
# -----------------------------------------------------------------------------

PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "YOUR_IP")

echo ""
echo "=============================================="
echo -e "${GREEN}SCP Trader Dashboard Setup Complete!${NC}"
echo "=============================================="
echo ""
echo "Next Steps:"
echo ""
echo "1. Edit IB Gateway credentials:"
echo "   sudo nano /opt/scp/ibc/config.ini"
echo ""
echo "2. Copy your SCP repository to /opt/scp/infra/"
echo "   (or clone it if you haven't already)"
echo ""
echo "3. Start Docker services:"
echo "   cd /opt/scp/infra"
echo "   source /opt/scp/.env"
echo "   docker-compose -f docker-compose.infra.yml \\"
echo "     -f docker-compose.services.yml \\"
echo "     -f docker-compose.trader-dashboard.yml up -d"
echo ""
echo "4. Start IB Gateway:"
echo "   sudo systemctl start ibgateway"
echo ""
echo "5. Access Grafana:"
echo "   http://$PUBLIC_IP:3000"
echo "   Login: admin / $GRAFANA_PASSWORD"
echo ""
echo "6. For IB 2FA authentication:"
echo "   ssh -L 5900:localhost:5900 ec2-user@$PUBLIC_IP"
echo "   Then connect VNC client to localhost:5900"
echo ""
echo "=============================================="
echo "Credentials saved to /opt/scp/.env"
echo "PostgreSQL password: $POSTGRES_PASSWORD"
echo "=============================================="
