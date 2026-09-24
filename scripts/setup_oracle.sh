#!/usr/bin/env bash
# ==============================================================================
# NEXUS QUANT TRADING WORKSTATION - ORACLE CLOUD AUTOMATED SETUP
# ==============================================================================
# Engineered for Ubuntu 22.04 / 24.04 LTS on Oracle Cloud Infrastructure (OCI).
# Handles firewall unblocking, Node.js 20, Python venv, Next.js build,
# PM2 process daemonization, and Nginx reverse proxy in 1-Click.
# ==============================================================================

set -e

echo ""
echo "===================================================================="
echo "   NEXUS QUANT // Autonomous Trading Platform - OCI Setup"
echo "===================================================================="
echo ""

# Ensure script is run with sudo or as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run with sudo: sudo bash scripts/setup_oracle.sh"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTUAL_USER="${SUDO_USER:-$USER}"
USER_HOME=$(eval echo ~$ACTUAL_USER)

echo "[1/7] Configuring Oracle Cloud OS Firewall (iptables)..."
# Oracle Cloud Ubuntu images drop incoming traffic by default
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 3000 -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport 3000 -j ACCEPT

# Save iptables rules persistently
DEBIAN_FRONTEND=noninteractive apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iptables-persistent netfilter-persistent
netfilter-persistent save

echo "[2/7] Checking Swap memory (Essential for low-RAM instances)..."
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
if [ "$TOTAL_RAM_KB" -lt 4000000 ] && [ ! -f /swapfile ]; then
    echo "    -> Low RAM detected (<4GB). Creating 2GB swap space for compilation safety..."
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
    fi
fi

echo "[3/7] Installing System Dependencies, Python 3, Node.js 20, and Nginx..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    git curl wget build-essential python3 python3-pip python3-venv python3-dev \
    nginx jq htop

# Install Node.js 20 LTS if not present or older than v20
NODE_INSTALLED=false
if command -v node >/dev/null 2>&1; then
    NODE_MAJOR=$(node -v | cut -d'.' -f1 | tr -d 'v')
    if [ "$NODE_MAJOR" -ge 20 ]; then
        NODE_INSTALLED=true
    fi
fi

if [ "$NODE_INSTALLED" = false ]; then
    echo "    -> Installing Node.js 20 LTS from NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
fi

# Install PM2 globally
npm install -g pm2 --silent

echo "[4/7] Setting up Python Virtual Environment..."
cd "$PROJECT_DIR"
mkdir -p data logs execution

if [ ! -d "venv" ]; then
    sudo -u "$ACTUAL_USER" python3 -m venv venv
fi

# Upgrade pip & install python requirements
sudo -u "$ACTUAL_USER" "$PROJECT_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u "$ACTUAL_USER" "$PROJECT_DIR/venv/bin/pip" install -r requirements.txt -q

# Initialize default .env if not exists
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
    else
        cat << 'EOF' > .env
TRADING_MODE=PAPER
EXCHANGE_API_KEY=
EXCHANGE_API_SECRET=
EOF
    fi
    chown "$ACTUAL_USER:$ACTUAL_USER" .env
fi

echo "[5/7] Building Next.js Quantitative Workstation..."
cd "$PROJECT_DIR/frontend"
sudo -u "$ACTUAL_USER" npm install --silent
sudo -u "$ACTUAL_USER" npm run build
cd "$PROJECT_DIR"

echo "[6/7] Configuring Nginx Reverse Proxy (Port 80 -> 3000)..."
cat << 'EOF' > /etc/nginx/sites-available/nexus
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 20M;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
EOF

ln -sf /etc/nginx/sites-available/nexus /etc/nginx/sites-enabled/nexus
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo "[7/7] Launching 24/7 Daemons via PM2..."
# Make sure permissions are correct for actual user
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$PROJECT_DIR"

# Launch Frontend and Trading Daemon as actual user
sudo -u "$ACTUAL_USER" bash << EOF
cd "$PROJECT_DIR"
pm2 delete nexus-frontend nexus-bot 2>/dev/null || true

# Start Frontend
cd "$PROJECT_DIR/frontend"
pm2 start npm --name "nexus-frontend" -- start

# Start Trading Bot (Defaults to Paper simulation mode with live exchange sync)
cd "$PROJECT_DIR"
pm2 start execution/live_momentum_daemon.py --name "nexus-bot" --interpreter ./venv/bin/python3

pm2 save
EOF

# Setup PM2 boot persistence
env PATH=$PATH:/usr/bin pm2 startup systemd -u "$ACTUAL_USER" --hp "$USER_HOME" || true

# Make CLI controller executable
chmod +x "$PROJECT_DIR/nexus.sh" 2>/dev/null || true
ln -sf "$PROJECT_DIR/nexus.sh" /usr/local/bin/nexus 2>/dev/null || true

PUBLIC_IP=$(curl -s https://api.ipify.org || echo "<YOUR_SERVER_IP>")

echo ""
echo "===================================================================="
echo "   🎉 NEXUS QUANT WORKSTATION IS LIVE ON ORACLE CLOUD!"
echo "===================================================================="
echo ""
echo "  [+] Live Web Workstation:  http://$PUBLIC_IP"
echo "  [+] Trading Mode:          AUTONOMOUS PAPER SIMULATION (Live Feeds)"
echo "  [+] Management Tool:       type 'nexus' or './nexus.sh'"
echo ""
echo "  Quick Commands:"
echo "    nexus status    -> Check live wallet, open trades & PM2 services"
echo "    nexus logs      -> View live trading signals and terminal stream"
echo "    nexus restart   -> Restart trading engine and UI"
echo "    nexus update    -> Pull latest git updates & rebuild"
echo ""
echo "===================================================================="
