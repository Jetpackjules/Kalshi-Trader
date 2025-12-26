import subprocess
import os
import sys
from datetime import datetime, timedelta
import re

# Configuration
VM_USER = "jetpackjules"
VM_IP = "34.56.193.18"
KEY_FILE = "../gcp_key"  # Relative to this script
LOCAL_LOG_DIR = "vm_logs"

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
