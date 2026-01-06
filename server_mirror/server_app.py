from flask import Flask, jsonify, request, send_from_directory
import os
import json
import time
from datetime import datetime

app = Flask(__name__)

# Configuration
LOG_DIR = r"market_logs" # Relative path on server
TRADER_STATUS_FILE = "trader_status.json"
CONTROL_FILE = "trading_enabled.txt"

def _latest_trader_log():
    if os.path.exists("output.log"):
        return "output.log"
    candidates = []
    for name in os.listdir("."):
        if name.startswith("live_trader_v") and name.endswith(".log"):
            try:
                candidates.append((os.path.getmtime(name), name))
            except OSError:
                continue
    if not candidates:
        return None
    _, latest_name = max(candidates)
    return latest_name


def _file_status(path: str, max_age_s: float) -> dict:
    if not path or not os.path.exists(path):
        return {"state": "missing", "age_s": None, "last_modified": None, "path": path}
    mtime = os.path.getmtime(path)
    age_s = time.time() - mtime
    state = "ok" if age_s <= max_age_s else "stale"
    return {
        "state": state,
        "age_s": round(age_s, 1),
        "last_modified": datetime.fromtimestamp(mtime).isoformat(),
        "path": path,
    }

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/dashboard.html')
def dashboard():
    return send_from_directory('.', 'dashboard.html')

@app.route('/output.log')
def serve_output_log():
    if os.path.exists('output.log'):
        return send_from_directory('.', 'output.log')
    return "output.log not found in server directory", 404

@app.route('/app_log')
def serve_app_log():
    # Prefer output.log since the deploy/start flow commonly runs:
    #   nohup ...live_trader_v6.py > output.log 2>&1 &
    # Fall back to the newest live_trader_v*.log to keep backward compatibility.
    if os.path.exists('output.log'):
        return send_from_directory('.', 'output.log')

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
        return "No output.log or live_trader_v*.log found in server directory", 404

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

@app.route('/api/trades', methods=['GET'])
def get_trades():
    try:
        trades_file = os.path.join("unified_engine_out", "trades.csv")
        if not os.path.exists(trades_file):
            # Fallback to root trades.csv if not found in subfolder
            trades_file = "trades.csv"
            
        if not os.path.exists(trades_file):
            return jsonify([])

        trades = []
        with open(trades_file, 'r') as f:
            lines = f.readlines()
            if len(lines) > 1:
                headers = lines[0].strip().split(',')
                # Map 'time' to 'timestamp' for frontend compatibility
                
                for line in reversed(lines[1:]): # Show newest first
                    parts = line.strip().split(',')
                    if len(parts) == len(headers):
                        trade = dict(zip(headers, parts))
                        if 'time' in trade:
                            trade['timestamp'] = trade['time']
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

@app.route('/api/health')
def get_health():
    max_age_s = float(request.args.get("max_age_s", 30))
    trader_log = _latest_trader_log()

    # Prefer the newest market_data_*.csv mtime for logger health.
    logger_target = None
    try:
        if os.path.isdir(LOG_DIR):
            csv_candidates = [
                os.path.join(LOG_DIR, name)
                for name in os.listdir(LOG_DIR)
                if name.startswith("market_data_") and name.endswith(".csv")
            ]
            if csv_candidates:
                logger_target = max(csv_candidates, key=os.path.getmtime)
    except OSError:
        logger_target = None

    if not logger_target:
        logger_target = "logger.log" if os.path.exists("logger.log") else os.path.join(LOG_DIR, "manifest.json")

    return jsonify({
        "max_age_s": max_age_s,
        "checks": {
            "logger": _file_status(logger_target, max_age_s),
            "live_trader": _file_status(trader_log or "", max_age_s),
            "shadow": _file_status("unified_engine.log", max_age_s),
            "observer": _file_status("observer_status.json", max_age_s),
        }
    })

@app.route('/unified_engine.log')
def serve_unified_log():
    if os.path.exists('unified_engine.log'):
        return send_from_directory('.', 'unified_engine.log')
    return "unified_engine.log not found in server directory", 404

@app.route('/observer_status.json')
def serve_observer_status():
    if os.path.exists('observer_status.json'):
        return send_from_directory('.', 'observer_status.json')
    return "observer_status.json not found in server directory", 404

@app.route('/unified_engine_out/<path:filename>')
def serve_unified_outputs(filename):
    out_dir = "unified_engine_out"
    return send_from_directory(out_dir, filename)

if __name__ == '__main__':
    # Ensure log dir exists
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # Run on 0.0.0.0 to be accessible externally
    app.run(host='0.0.0.0', port=80, debug=False)
