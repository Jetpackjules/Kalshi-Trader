import time
import subprocess
import threading
import os
from server_mirror.server_app import app

def sync_data():
    # Ensure directories exist
    if not os.path.exists("unified_engine_out"):
        os.makedirs("unified_engine_out")
        
    while True:
        try:
            print("--- Syncing data from server ---")
            
            # Sync trader_status.json (For Market Gaps & Status)
            subprocess.run([
                "scp", "-i", "keys/gcp_key", 
                "-o", "StrictHostKeyChecking=no", 
                "jetpackjules@34.56.193.18:~/trader_status.json", 
                "."
            ], check=True, capture_output=True)
            
            # Sync trades.csv (For Recent Trades)
            subprocess.run([
                "scp", "-i", "keys/gcp_key", 
                "-o", "StrictHostKeyChecking=no", 
                "jetpackjules@34.56.193.18:~/unified_engine_out/trades.csv", 
                "unified_engine_out/"
            ], check=False, capture_output=True) # Don't fail if trades.csv missing
            
            print("Sync complete.")
        except subprocess.CalledProcessError as e:
            print(f"Sync failed: {e}")
        except Exception as e:
            print(f"Sync error: {e}")
            
        time.sleep(5)

if __name__ == "__main__":
    # Start Sync Thread
    t = threading.Thread(target=sync_data, daemon=True)
    t.start()
    
    print("Starting Real Dashboard Server on http://localhost:8080")
    # Run Flask
    app.run(host='0.0.0.0', port=8080)
