import subprocess
import os
import datetime
import time

# Configuration
KEY_PATH = os.path.join("keys", "gcp_key")
SERVER_USER = "jetpackjules"
SERVER_IP = "34.56.193.18"
SERVER_ADDR = f"{SERVER_USER}@{SERVER_IP}"
LOCAL_MIRROR_DIR = "server_mirror"
REMOTE_HOME = "~"
SNAPSHOT_LOCAL_DIR = os.path.join("vm_logs", "snapshots")

def run_command(cmd, description):
    print(f"--- {description} ---")
    print(f"Running: {cmd}")
    try:
        # Use shell=True for Windows to handle paths/commands correctly if needed, 
        # but list of args is usually safer. However, for scp/ssh with complex args, string might be easier.
        subprocess.check_call(cmd, shell=True)
        print("✅ Success\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}\n")
        # Don't exit immediately, try to continue if possible, or raise?
        # For killing process, failure might mean no process running.
        if "pkill" in cmd:
            print("(Process might not have been running, continuing...)")
        else:
            raise e

def main():
    # Ensure snapshot dir exists
    if not os.path.exists(SNAPSHOT_LOCAL_DIR):
        os.makedirs(SNAPSHOT_LOCAL_DIR)

    # 1. Kill running live_trader processes (but NOT logger)
    # We use pkill -f live_trader_v to match live_trader_v4.py, live_trader_v6.py, etc.
    # Logger is usually logger.py or granular_logger.py, so it won't match.
    kill_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "pkill -f live_trader_v"'
    run_command(kill_cmd, "Killing running live_trader processes")

    # 2. Upload Files
    files_to_upload = ["live_trader_v4.py", "live_trader_v6.py"]
    for filename in files_to_upload:
        local_path = os.path.join(LOCAL_MIRROR_DIR, filename)
        remote_path = f"{REMOTE_HOME}/{filename}"
        # Check if local file exists
        if not os.path.exists(local_path):
            print(f"⚠️ Warning: {local_path} not found. Skipping.")
            continue
            
        scp_cmd = f'scp -i {KEY_PATH} -o StrictHostKeyChecking=no {local_path} {SERVER_ADDR}:{remote_path}'
        run_command(scp_cmd, f"Uploading {filename}")

    # 3. Generate Snapshot
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    snapshot_filename = f"snapshot_{timestamp}.json"
    remote_snapshot_path = f"{REMOTE_HOME}/{snapshot_filename}"
    
    # Using v6 to take snapshot as requested/implied by instructions
    snapshot_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "~/venv/bin/python ~/live_trader_v6.py --snapshot --snapshot-out {remote_snapshot_path}"'
    run_command(snapshot_cmd, "Generating Snapshot on VM")

    # 4. Download Snapshot
    local_snapshot_path = os.path.join(SNAPSHOT_LOCAL_DIR, snapshot_filename)
    download_cmd = f'scp -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR}:{remote_snapshot_path} {local_snapshot_path}'
    run_command(download_cmd, "Downloading Snapshot")

    # 5. Start the Trader
    # Using nohup to keep it running after disconnect
    # We use v6 as it's the latest uploaded version
    start_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "nohup ~/venv/bin/python -u ~/live_trader_v6.py > ~/output.log 2>&1 &"'
    run_command(start_cmd, "Starting Live Trader V6")

    print("=== Deployment and Snapshot Complete ===")
    print(f"Snapshot saved to: {local_snapshot_path}")
    print("Trader V6 has been started on the server.")

if __name__ == "__main__":
    main()
