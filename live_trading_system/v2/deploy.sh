#!/bin/bash

# Configuration
SERVER_IP="34.56.193.18"
USER="jetpackjules"
REMOTE_DIR="~" # Deploying to home dir as per existing setup
KEY_PATH="c:/Users/jetpa/OneDrive - UW/Google_Grav_Onedrive/kalshi_weather_data/gcp_key"

echo "Deploying to $SERVER_IP..."

# 1. Upload Files
echo "Uploading files..."
scp -i "$KEY_PATH" -o StrictHostKeyChecking=no live_trader_v3.py $USER@$SERVER_IP:$REMOTE_DIR/
scp -i "$KEY_PATH" -o StrictHostKeyChecking=no server_app.py $USER@$SERVER_IP:$REMOTE_DIR/
scp -i "$KEY_PATH" -o StrictHostKeyChecking=no dashboard_v2.html $USER@$SERVER_IP:$REMOTE_DIR/dashboard.html

echo "Deployment Complete!"
echo "To start the new system:"
echo "1. SSH in:"
echo "   ssh -i \"$KEY_PATH\" $USER@$SERVER_IP"
echo ""
echo "2. Stop the old web server:"
echo "   pkill -f web_server.py"
echo ""
echo "3. Install Flask (if needed):"
echo "   source venv/bin/activate"
echo "   pip install flask"
echo ""
echo "4. Start the new Brain:"
echo "   nohup python3 server_app.py > server.log 2>&1 &"
echo ""
echo "5. Start the Trader:"
echo "   nohup python3 live_trader_v3.py > trader.log 2>&1 &"

