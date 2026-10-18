#!/usr/bin/env bash
# ==============================================================================
# OFFICIALUM1 — High-Speed Cloud VPS Installer & Optimizer (Ubuntu 22.04/24.04)
# Configures: 2GB Swap Memory, Port 53 Freeing, UFW Firewall, Systemd 24/7 Engine
# ==============================================================================

set -e

echo ""
echo "=================================================================="
echo "    OFFICIALUM1 — 1-CLICK CLOUD VPS SETUP (142.93.19.40)          "
echo "=================================================================="
echo ""

# 1. 2GB Swap Setup (Prevents OOM Crashes on 1GB RAM)
if [ ! -f /swapfile ]; then
    echo "[1/6] Allocating 2GB Swap Memory for 1GB RAM stability..."
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo "       [OK] Swapfile active (2GB)."
else
    echo "[1/6] Swapfile already exists."
fi

# 2. Release Ubuntu Port 53 (systemd-resolved stub listener)
echo "[2/6] Configuring systemd-resolved to release Port 53..."
if [ -f /etc/systemd/resolved.conf ]; then
    sed -i 's/#*DNSStubListener=yes/DNSStubListener=no/' /etc/systemd/resolved.conf
    sed -i 's/#*DNSStubListener=no/DNSStubListener=no/' /etc/systemd/resolved.conf
    systemctl restart systemd-resolved || true
fi
# Ensure symlink /etc/resolv.conf points to real upstream DNS if needed
if [ -f /run/systemd/resolve/resolv.conf ]; then
    ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
fi
echo "       [OK] Port 53 is now free for OFFICIALUM1 DNS Firewall."

# 3. System Packages & Python Environment
echo "[3/6] Installing required system tools & Python3..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git curl ufw

# 4. Configure UFW Firewall
echo "[4/6] Setting up UFW Firewall rules..."
ufw allow 22/tcp comment 'SSH'
ufw allow 53 comment 'DNS UDP and TCP'
ufw allow 8088/tcp comment 'OFFICIALUM1 Web Dashboard'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
echo "       [OK] Ports 22, 53, 80, 443, 8088 opened."

# 5. Project Directory & Virtualenv Setup
APP_DIR="/opt/firwallum1"
echo "[5/6] Preparing Application in ${APP_DIR}..."
mkdir -p "${APP_DIR}"

# If repo not yet present in /opt, copy from current directory or clone
if [ ! -f "${APP_DIR}/server.py" ]; then
    cp -r ./* "${APP_DIR}/" || true
fi

cd "${APP_DIR}"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 6. Create Systemd Service for 24/7 Autostart
echo "[6/6] Creating systemd background service (firwallum1.service)..."
cat << 'EOF' > /etc/systemd/system/firwallum1.service
[Unit]
Description=OFFICIALUM1 Cloud DNS Firewall & Security Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/firwallum1
Environment=PORT=8088
Environment=HUB_IP=142.93.19.40
ExecStart=/opt/firwallum1/venv/bin/python server.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable firwallum1.service
systemctl restart firwallum1.service

echo ""
echo "=================================================================="
echo "    [SUCCESS] OFFICIALUM1 CLOUD HUB IS NOW RUNNING 24/7!          "
echo "=================================================================="
echo "  * Web Dashboard:  http://142.93.19.40:8088"
echo "  * Router Primary DNS: 142.93.19.40"
echo "  * Router Secondary DNS: 1.1.1.1"
echo "  * Status Check:   systemctl status firwallum1"
echo "=================================================================="
echo ""
