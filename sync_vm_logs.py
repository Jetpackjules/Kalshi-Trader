import subprocess
import os
import sys
from datetime import datetime, timedelta
import re

# Configuration
VM_USER = "jetpackjules"
VM_IP = "34.56.193.18"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(SCRIPT_DIR, "keys", "gcp_key")  # Absolute path to SSH key
LOCAL_LOG_DIR = "vm_logs"
LOCAL_MIRROR_DIR = "server_mirror"

def sync_logs():
    """Downloads logger.log and market_logs from the VM."""
    
    # Ensure local log directory exists
    if not os.path.exists(LOCAL_LOG_DIR):
        print(f"Creating local directory: {LOCAL_LOG_DIR}")
        os.makedirs(LOCAL_LOG_DIR)

    print(f"Syncing logs from {VM_IP}...")

    # 1. Download logger.log
    print("Downloading logger.log...")
    cmd_logger = [
        "scp",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/logger.log",
        f"{LOCAL_LOG_DIR}/"
    ]
    
    try:
        subprocess.run(cmd_logger, check=True)
        print("Successfully downloaded logger.log")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading logger.log: {e}")

    # 1a. Download output.log into server_mirror/ for live status parsing
    if not os.path.exists(LOCAL_MIRROR_DIR):
        os.makedirs(LOCAL_MIRROR_DIR)
    print("Downloading output.log...")
    cmd_output = [
        "scp",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/output.log",
        f"{LOCAL_MIRROR_DIR}/"
    ]

    try:
        subprocess.run(cmd_output, check=True)
        print("Successfully downloaded output.log")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading output.log: {e}")

    # 1b. Download trades.csv
    print("Downloading trades.csv...")
    cmd_trades = [
        "scp",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/trades.csv",
        f"{LOCAL_LOG_DIR}/"
    ]
    
    try:
        subprocess.run(cmd_trades, check=True)
        print("Successfully downloaded trades.csv")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading trades.csv: {e}")

    # 1c. Download trader_status.json
    print("Downloading trader_status.json...")
    cmd_status = [
        "scp",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/trader_status.json",
        f"{LOCAL_LOG_DIR}/"
    ]
    
    try:
        subprocess.run(cmd_status, check=True)
        print("Successfully downloaded trader_status.json")
        
        # Versioning: Save a copy to snapshots/ folder
        import json
        import shutil
        
        local_status_path = os.path.join(LOCAL_LOG_DIR, "trader_status.json")
        snapshots_dir = os.path.join(LOCAL_LOG_DIR, "snapshots")
        
        if not os.path.exists(snapshots_dir):
            os.makedirs(snapshots_dir)
            
        try:
            with open(local_status_path, 'r') as f:
                data = json.load(f)
                last_update = data.get("last_update", "unknown").replace(":", "-").replace(" ", "_")
                
            snapshot_filename = f"trader_status_{last_update}.json"
            snapshot_path = os.path.join(snapshots_dir, snapshot_filename)
            
            shutil.copy2(local_status_path, snapshot_path)
            print(f"  Saved snapshot to: {snapshot_path}")
            
        except Exception as e:
            print(f"  Warning: Could not version snapshot: {e}")
            
    except subprocess.CalledProcessError as e:
        print(f"Error downloading trader_status.json: {e}")

    # 1d. Download live_trader_v4.log
    print("Downloading live_trader_v4.log...")
    cmd_trader_log = [
        "scp",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/live_trader_v4.log",
        f"{LOCAL_LOG_DIR}/"
    ]
    
    try:
        subprocess.run(cmd_trader_log, check=True)
        print("Successfully downloaded live_trader_v4.log")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading live_trader_v4.log: {e}")

    # 1e. Download unified_engine.log
    print("Downloading unified_engine.log...")
    cmd_unified_log = [
        "scp",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/unified_engine.log",
        f"{LOCAL_LOG_DIR}/"
    ]

    try:
        subprocess.run(cmd_unified_log, check=True)
        print("Successfully downloaded unified_engine.log")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading unified_engine.log: {e}")

    # 1f. Download unified_engine_out outputs
    print("Downloading unified_engine_out outputs...")
    unified_out_dir = os.path.join(LOCAL_LOG_DIR, "unified_engine_out")
    if not os.path.exists(unified_out_dir):
        os.makedirs(unified_out_dir)

    unified_files = [
        "unified_positions.json",
        "trades.csv",
        "decision_intents.csv",
        "unified_orders.csv",
        "trade_debug.csv",
        "tick_ingest_log.csv",
    ]

    for filename in unified_files:
        cmd_unified_out = [
            "scp",
            "-i", KEY_FILE,
            "-o", "StrictHostKeyChecking=no",
            f"{VM_USER}@{VM_IP}:~/unified_engine_out/{filename}",
            f"{unified_out_dir}/"
        ]
        try:
            subprocess.run(cmd_unified_out, check=True)
            print(f"Successfully downloaded {filename}")
        except subprocess.CalledProcessError as e:
            print(f"Error downloading {filename}: {e}")

    # 1g. Download snapshots (unified + daily)
    print("Downloading snapshots...")
    snapshots_dir = os.path.join(LOCAL_LOG_DIR, "snapshots")
    if not os.path.exists(snapshots_dir):
        os.makedirs(snapshots_dir)

    cmd_unified_snaps = [
        "scp",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/snapshots/snapshot_unified_*.json",
        f"{snapshots_dir}/"
    ]

    try:
        subprocess.run(cmd_unified_snaps, check=True)
        print("Successfully downloaded unified snapshots")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading unified snapshots: {e}")

    cmd_daily_snaps = [
        "scp",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/snapshots/snapshot_*.json",
        f"{snapshots_dir}/"
    ]

    try:
        subprocess.run(cmd_daily_snaps, check=True)
        print("Successfully downloaded daily snapshots")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading daily snapshots: {e}")

    # 2. Download market_logs directory (selective)
    print("\nSyncing market_logs/...")
    
    # Ensure local market_logs directory exists
    local_market_dir = os.path.join(LOCAL_LOG_DIR, "market_logs")
    if not os.path.exists(local_market_dir):
        os.makedirs(local_market_dir)

    # Get list of files on VM
    cmd_list_vm = [
        "ssh",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}",
        "ls ~/market_logs"
    ]
    
    try:
        result = subprocess.run(cmd_list_vm, capture_output=True, text=True, check=True)
        vm_files = result.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print(f"Error listing files on VM: {e}")
        return

    # Get list of local files
    local_files = os.listdir(local_market_dir)
    
    # Date threshold: 2 days ago
    threshold_date = datetime.now() - timedelta(days=2)
    
    files_to_download = []
    
    # Regex to extract date from filename (e.g., market_data_KXHIGHNY-25DEC22.csv)
    date_pattern = re.compile(r'-(\d{2}[A-Z]{3}\d{2})\.csv')

    for filename in vm_files:
        if filename == "manifest.json":
            files_to_download.append(filename)
            continue
            
        is_missing = filename not in local_files
        
        # Check if it's a recent file
        match = date_pattern.search(filename)
        is_recent = False
        if match:
            date_str = match.group(1)
            try:
                # Format: 25DEC22
                file_date = datetime.strptime(date_str, "%y%b%d")
                if file_date >= threshold_date:
                    is_recent = True
            except ValueError:
                pass
        
        if is_missing or is_recent:
            files_to_download.append(filename)
            reason = "missing" if is_missing else "recent"
            print(f"  Queuing {filename} ({reason})")

    if not files_to_download:
        print("No new or recent files to download.")
    else:
        print(f"Downloading {len(files_to_download)} files...")
        # Download files individually to avoid complex scp patterns
        for filename in files_to_download:
            cmd_scp = [
                "scp",
                "-i", KEY_FILE,
                "-o", "StrictHostKeyChecking=no",
                f"{VM_USER}@{VM_IP}:~/market_logs/{filename}",
                f"{local_market_dir}/"
            ]
            try:
                subprocess.run(cmd_scp, check=True, capture_output=True)
                # print(f"  Downloaded {filename}")
            except subprocess.CalledProcessError as e:
                print(f"  Error downloading {filename}: {e}")

    print("\nSync complete! Logs are in the 'vm_logs' folder.")

if __name__ == "__main__":
    # Change to the directory of the script to ensure relative paths work
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sync_logs()
