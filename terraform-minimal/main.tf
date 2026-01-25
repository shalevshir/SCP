# =============================================================================
# SCP Trading System - Minimal Single EC2 Deployment
# =============================================================================
# 
# Cost-optimized setup for Trader Dashboard stage (~$25-40/month)
# Everything runs on a single EC2 instance with Docker Compose
#
# Usage:
#   terraform init
#   terraform apply -var-file="terraform.tfvars"

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "scp-trading"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "aws_region" {
  default = "us-east-1"
}

variable "environment" {
  default = "dashboard"
}

variable "instance_type" {
  description = "EC2 instance type (t3.small=2GB, t3.medium=4GB)"
  default     = "t3.small"  # $15/month - upgrade to t3.medium if needed
}

variable "use_spot" {
  description = "Use spot instance for ~70% cost savings (can be interrupted)"
  type        = bool
  default     = false
}

variable "allowed_cidrs" {
  description = "Your IP address(es) for SSH/Grafana access"
  type        = list(string)
  # Find your IP: curl -s https://ifconfig.me
}

variable "ssh_public_key" {
  description = "SSH public key for EC2 access"
  type        = string
  default     = ""  # Will use ~/.ssh/id_rsa.pub if empty
}

variable "ib_username" {
  description = "Interactive Brokers username"
  type        = string
  sensitive   = true
}

variable "ib_password" {
  description = "Interactive Brokers password"
  type        = string
  sensitive   = true
}

variable "ib_trading_mode" {
  description = "paper or live"
  default     = "paper"
}

variable "grafana_password" {
  description = "Grafana admin password"
  type        = string
  sensitive   = true
  default     = "admin"  # Change this!
}

variable "postgres_password" {
  description = "PostgreSQL password"
  type        = string
  sensitive   = true
  default     = ""  # Will generate random if empty
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

# Latest Amazon Linux 2023
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Generate random password if not provided
resource "random_password" "postgres" {
  count   = var.postgres_password == "" ? 1 : 0
  length  = 24
  special = false
}

locals {
  postgres_password = var.postgres_password != "" ? var.postgres_password : random_password.postgres[0].result
}

# -----------------------------------------------------------------------------
# Networking (Minimal - Default VPC)
# -----------------------------------------------------------------------------

# Use default VPC to avoid NAT Gateway costs
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  filter {
    name   = "availability-zone"
    values = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c", "${var.aws_region}d", "${var.aws_region}f"]
  }
}

# Security Group
resource "aws_security_group" "scp" {
  name_prefix = "scp-${var.environment}-"
  description = "SCP Trading System"
  vpc_id      = data.aws_vpc.default.id

  # SSH
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }

  # VNC (for IB Gateway 2FA)
  ingress {
    description = "VNC"
    from_port   = 5900
    to_port     = 5900
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }

  # Grafana
  ingress {
    description = "Grafana"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }

  # Prometheus (optional - for remote access)
  ingress {
    description = "Prometheus"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }

  # All outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "scp-${var.environment}"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# -----------------------------------------------------------------------------
# SSH Key
# -----------------------------------------------------------------------------

resource "aws_key_pair" "scp" {
  key_name   = "scp-${var.environment}"
  public_key = var.ssh_public_key != "" ? var.ssh_public_key : file(pathexpand("~/.ssh/id_rsa.pub"))
}

# -----------------------------------------------------------------------------
# EC2 Instance
# -----------------------------------------------------------------------------

resource "aws_instance" "scp" {
  count = var.use_spot ? 0 : 1

  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.scp.key_name
  vpc_security_group_ids = [aws_security_group.scp.id]
  subnet_id              = data.aws_subnets.default.ids[0]

  associate_public_ip_address = true

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    delete_on_termination = true
  }

  user_data = base64encode(local.user_data_script)

  tags = {
    Name = "scp-${var.environment}"
  }
}

# Spot Instance (optional - for cost savings)
resource "aws_spot_instance_request" "scp" {
  count = var.use_spot ? 1 : 0

  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.scp.key_name
  vpc_security_group_ids = [aws_security_group.scp.id]
  subnet_id              = data.aws_subnets.default.ids[0]

  associate_public_ip_address = true
  wait_for_fulfillment        = true
  spot_type                   = "persistent"

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    delete_on_termination = true
  }

  user_data = base64encode(local.user_data_script)

  tags = {
    Name = "scp-${var.environment}-spot"
  }
}

# Elastic IP for stable address
resource "aws_eip" "scp" {
  instance = var.use_spot ? aws_spot_instance_request.scp[0].spot_instance_id : aws_instance.scp[0].id
  domain   = "vpc"

  tags = {
    Name = "scp-${var.environment}"
  }
}

# -----------------------------------------------------------------------------
# User Data Script
# -----------------------------------------------------------------------------

locals {
  user_data_script = <<-EOF
    #!/bin/bash
    set -e
    
    # Logging
    exec > >(tee /var/log/scp-setup.log) 2>&1
    echo "Starting SCP setup at $(date)"
    
    # Update system
    dnf update -y
    
    # Install Docker
    dnf install -y docker git
    systemctl enable docker
    systemctl start docker
    
    # Install Docker Compose
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
      -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    
    # Install Java for IB Gateway
    dnf install -y java-11-amazon-corretto-headless
    
    # Install Xvfb and VNC for headless IB Gateway
    dnf install -y xorg-x11-server-Xvfb x11vnc unzip
    
    # Create user
    useradd -m -G docker scp || true
    
    # Create directories
    mkdir -p /opt/scp/{infra,services,config}
    mkdir -p /opt/scp/data/{postgres,redis,grafana,prometheus}
    chown -R scp:scp /opt/scp
    
    # Create environment file
    cat > /opt/scp/.env << 'ENVFILE'
    POSTGRES_PASSWORD=${local.postgres_password}
    GRAFANA_PASSWORD=${var.grafana_password}
    SERVICE_MODE=dashboard
    IB_USERNAME=${var.ib_username}
    IB_PASSWORD=${var.ib_password}
    IB_TRADING_MODE=${var.ib_trading_mode}
    ENVFILE
    chmod 600 /opt/scp/.env
    
    # Download IB Gateway
    cd /tmp
    wget -q "https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh" \
      -O ibgateway-installer.sh
    chmod +x ibgateway-installer.sh
    ./ibgateway-installer.sh -q -dir /opt/scp/ibgateway
    
    # Download IBC
    IBC_VERSION="3.18.0"
    wget -q "https://github.com/IbcAlpha/IBC/releases/download/$IBC_VERSION/IBCLinux-$IBC_VERSION.zip" -O ibc.zip
    unzip -q ibc.zip -d /opt/scp/ibc
    chmod +x /opt/scp/ibc/*.sh
    
    # Create IBC config
    cat > /opt/scp/ibc/config.ini << 'IBCCONFIG'
    IbLoginId=${var.ib_username}
    IbPassword=${var.ib_password}
    TradingMode=${var.ib_trading_mode}
    IbDir=/opt/scp/ibgateway
    AcceptIncomingConnectionAction=accept
    AcceptNonBrokerageAccountWarning=yes
    AllowBlindTrading=yes
    DismissPasswordExpiryWarning=yes
    ExistingSessionDetectedAction=primary
    MinimizeMainWindow=yes
    IBCCONFIG
    chmod 600 /opt/scp/ibc/config.ini
    
    # Create systemd services for Xvfb, VNC, IB Gateway
    cat > /etc/systemd/system/xvfb.service << 'XVFB'
    [Unit]
    Description=X Virtual Frame Buffer
    After=network.target
    [Service]
    Type=simple
    User=scp
    ExecStart=/usr/bin/Xvfb :1 -screen 0 1024x768x24
    Restart=always
    [Install]
    WantedBy=multi-user.target
    XVFB
    
    cat > /etc/systemd/system/x11vnc.service << 'VNC'
    [Unit]
    Description=VNC Server
    After=xvfb.service
    Requires=xvfb.service
    [Service]
    Type=simple
    User=scp
    Environment=DISPLAY=:1
    ExecStart=/usr/bin/x11vnc -display :1 -forever -shared -rfbport 5900 -nopw
    Restart=always
    [Install]
    WantedBy=multi-user.target
    VNC
    
    cat > /etc/systemd/system/ibgateway.service << 'IBGW'
    [Unit]
    Description=IB Gateway
    After=xvfb.service
    Requires=xvfb.service
    [Service]
    Type=simple
    User=scp
    Environment=DISPLAY=:1
    WorkingDirectory=/opt/scp/ibc
    ExecStart=/opt/scp/ibc/gatewaystart.sh -g /opt/scp/ibc/config.ini
    Restart=always
    RestartSec=30
    [Install]
    WantedBy=multi-user.target
    IBGW
    
    # Enable services
    systemctl daemon-reload
    systemctl enable xvfb x11vnc ibgateway
    systemctl start xvfb
    sleep 2
    systemctl start x11vnc
    
    # Fix permissions
    chown -R scp:scp /opt/scp
    
    echo "Setup complete! Clone your repo to /opt/scp and run docker-compose"
    echo "Then start IB Gateway: systemctl start ibgateway"
  EOF
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "public_ip" {
  description = "Public IP address"
  value       = aws_eip.scp.public_ip
}

output "ssh_command" {
  description = "SSH command"
  value       = "ssh -i ~/.ssh/id_rsa ec2-user@${aws_eip.scp.public_ip}"
}

output "vnc_tunnel" {
  description = "VNC tunnel command (for IB 2FA)"
  value       = "ssh -L 5900:localhost:5900 -i ~/.ssh/id_rsa ec2-user@${aws_eip.scp.public_ip}"
}

output "grafana_url" {
  description = "Grafana URL"
  value       = "http://${aws_eip.scp.public_ip}:3000"
}

output "next_steps" {
  sensitive = true
  value     = <<-EOT
    
    ========================================
    SCP Trader Dashboard - Setup Complete!
    ========================================
    
    Cost: ~$${var.use_spot ? "10-15" : "22-37"}/month
    
    1. SSH to the server:
       ssh -i ~/.ssh/id_rsa ec2-user@${aws_eip.scp.public_ip}

    2. Clone your repository:
       cd /opt/scp
       git clone <your-repo> .
    
    3. Start services:
       cd /opt/scp/infra
       docker-compose -f docker-compose.infra.yml \\
         -f docker-compose.services.yml \\
         -f docker-compose.trader-dashboard.yml up -d
    
    4. Start IB Gateway:
       sudo systemctl start ibgateway
    
    5. Access Grafana:
       http://${aws_eip.scp.public_ip}:3000
       Login: admin / ${var.grafana_password}
    
    6. For IB 2FA (weekly):
       ssh -L 5900:localhost:5900 -i ~/.ssh/id_rsa ec2-user@${aws_eip.scp.public_ip}
       Then connect VNC to localhost:5900
    
    ========================================
  EOT
}
