import subprocess
import os
import sys

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

    # 2. Download market_logs directory (recursive)
    print("Downloading market_logs/...")
    cmd_market = [
        "scp",
        "-r",
        "-i", KEY_FILE,
        "-o", "StrictHostKeyChecking=no",
        f"{VM_USER}@{VM_IP}:~/market_logs",
        f"{LOCAL_LOG_DIR}/"
    ]

    try:
        subprocess.run(cmd_market, check=True)
        print("Successfully downloaded market_logs/")
    except subprocess.CalledProcessError as e:
        print(f"Error downloading market_logs: {e}")

    print("\nSync complete! Logs are in the 'vm_logs' folder.")

if __name__ == "__main__":
    # Change to the directory of the script to ensure relative paths work
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sync_logs()
