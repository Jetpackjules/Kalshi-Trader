#!/bin/bash

echo "============================================"
echo "   Kalshi Granular Logger Deployment"
echo "============================================"

# 1. Stop existing processes
echo "[1/5] Stopping old processes..."
sudo pkill -f granular_logger.py
sudo pkill -f web_server.py

# 2. Clear old logs
echo "[2/5] Ensuring log directory exists..."
# rm -rf market_logs # DISABLED to prevent data loss
mkdir -p market_logs

# 3. Install dependencies
echo "[3/5] Setting up virtual environment..."
# Install venv if missing (try apt-get just in case, though usually pre-installed or needs python3-venv)
# We'll assume python3 -m venv works or try to install it.
# Actually, on some cloud VMs, we might need to just use --break-system-packages if venv fails, 
# but let's try venv first as it's standard.

python3 -m venv venv
source venv/bin/activate

echo "Installing libraries..."
pip install websockets requests cryptography

# 4. Start Logger
echo "[4/5] Starting Granular Logger..."
nohup python -u granular_logger.py > logger.log 2>&1 &
PID_LOGGER=$!
echo "Logger started with PID $PID_LOGGER"

# 5. Start Web Server
echo "[5/5] Starting Web Server..."
# We need sudo to bind port 80, but we need the venv's python.
# sudo forgets the venv, so we point to the absolute path of the venv python.
VENV_PYTHON=$(pwd)/venv/bin/python
nohup sudo $VENV_PYTHON web_server.py > web_server.log 2>&1 &
PID_WEB=$!
echo "Web Server started with PID $PID_WEB"

echo "============================================"
echo "   DEPLOYMENT COMPLETE"
echo "============================================"
echo "Dashboard available at: http://$(curl -s ifconfig.me):8000/dashboard.html"
echo "Logs are being written to: market_logs/"
