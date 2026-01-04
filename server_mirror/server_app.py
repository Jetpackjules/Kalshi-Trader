from flask import Flask, jsonify, request, send_from_directory
import os
import json
import time

app = Flask(__name__)

# Configuration
LOG_DIR = r"market_logs" # Relative path on server
TRADER_STATUS_FILE = "trader_status.json"
CONTROL_FILE = "trading_enabled.txt"

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/dashboard.html')
def dashboard():
    return send_from_directory('.', 'dashboard.html')

@app.route('/app_log')
def serve_app_log():
    # Serve the newest trader log to keep the dashboard in sync with the
    # currently-running version (v4/v5/v6...).
    candidates = []
    try:
        for name in os.listdir('.'):
            if name.startswith('live_trader_v') and name.endswith('.log'):
                try:
                    candidates.append((os.path.getmtime(name), name))
                except OSError:
                    continue
    except OSError:
        candidates = []

    if not candidates:
        # Keep response simple for the browser.
        return "No live_trader_v*.log found in server directory", 404

    _, latest_name = max(candidates)
    return send_from_directory('.', latest_name)

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        if os.path.exists(TRADER_STATUS_FILE):
            with open(TRADER_STATUS_FILE, 'r') as f:
                data = json.load(f)
            return jsonify(data)
        else:
            return jsonify({"status": "UNKNOWN", "message": "Status file not found"})
    except Exception as e:
        return jsonify({"status": "ERROR", "message": str(e)}), 500

@app.route('/api/control', methods=['POST'])
def control_trader():
    try:
        action = request.json.get('action') # 'start' or 'stop'
        if action == 'start':
            with open(CONTROL_FILE, 'w') as f:
                f.write("true")
            return jsonify({"success": True, "message": "Trading Enabled"})
        elif action == 'stop':
            with open(CONTROL_FILE, 'w') as f:
                f.write("false")
            return jsonify({"success": True, "message": "Trading Disabled"})
        else:
            return jsonify({"success": False, "message": "Invalid action"}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/trades')
def get_trades():
    try:
        trades_file = "trades.csv"
        if not os.path.exists(trades_file):
            return jsonify([])
        
        trades = []
        # Read CSV and get last 10 lines
        with open(trades_file, 'r') as f:
            # Skip header if exists
            lines = f.readlines()
            if len(lines) > 1:
                # Parse headers from first line
                headers = lines[0].strip().split(',')
                # Get last 10 data lines
                last_lines = lines[-10:] if len(lines) > 10 else lines[1:]
                
                for line in reversed(last_lines): # Show newest first
                    parts = line.strip().split(',')
                    if len(parts) == len(headers):
                        trade = dict(zip(headers, parts))
                        trades.append(trade)
        return jsonify(trades)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download_trades')
def download_trades():
    try:
        return send_from_directory('.', 'trades.csv', as_attachment=True)
    except Exception as e:
        return str(e), 404

@app.route('/market_logs/<path:filename>')
def serve_logs(filename):
    return send_from_directory(LOG_DIR, filename)

@app.route('/market_logs/manifest.json')
def serve_manifest():
    # Dynamic manifest generation
    try:
        files = [f for f in os.listdir(LOG_DIR) if f.startswith("market_data_") and f.endswith(".csv")]
        return jsonify({
            "files": sorted(files),
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Ensure log dir exists
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # Run on 0.0.0.0 to be accessible externally
    app.run(host='0.0.0.0', port=80, debug=False)
