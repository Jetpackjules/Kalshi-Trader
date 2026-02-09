
import os
import subprocess
import time

VM_IP = "34.56.193.18"
KEY_FILE = "keys/gcp_key"
REMOTE_DIR = "kalshi_weather_data/market_logs"
LOCAL_DIR = "market_analysis_data"

def sync_market_logs():
    if not os.path.exists(LOCAL_DIR):
        os.makedirs(LOCAL_DIR)

    print(f"Syncing market data logs from {VM_IP}...")
    
    # Use scp since rsync is missing on Windows
    # Recursive copy (-r) for the directory content or just specific files
    # scp user@host:remote_path/*.csv local_path/
    
    # We need to construct the scp command carefully for Windows
    # scp -i key_file json_user@IP:path/market_data_*.csv local_path/
    # Note: scp doesn't support wildcards on remote side easily without shell expansion.
    # So we'll fetch the whole directory content or list files first?
    # Simpler: just fetch the directory recursively? No, that fetches everything.
    # Let's try fetching specific files by iterating or using a wildcard if supported by the server's shell.
    # Defaulting to copying the whole directory content (filtered by manual list if needed, but here let's try wildcard).
    
    cmd = [
        "scp", "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"json_user@{VM_IP}:{REMOTE_DIR}/market_data_*.csv",
        f"{LOCAL_DIR}/"
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("Sync complete!")
    except subprocess.CalledProcessError as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    sync_market_logs()
