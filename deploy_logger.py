import subprocess
import os
import time

# Configuration
KEY_PATH = os.path.join("keys", "gcp_key")
SERVER_USER = "jetpackjules"
SERVER_IP = "34.56.193.18"
SERVER_ADDR = f"{SERVER_USER}@{SERVER_IP}"
LOCAL_FILE = "server_mirror/granular_logger.py"
REMOTE_FILE = "granular_logger.py" # In home dir
REMOTE_HOME = "~"

def run_command(cmd, description):
    print(f"--- {description} ---")
    print(f"Running: {cmd}")
    try:
        subprocess.check_call(cmd, shell=True)
        print("OK\n")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {e}\n")
        if "pkill" in cmd:
            print("(Process might not have been running; continuing.)")
            return
        else:
            raise e

def main():
    # 1. Kill running Logger
    kill_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "pkill -f granular_logger.py"'
    run_command(kill_cmd, "Killing running Granular Logger")

    # 2. Upload New Script
    if not os.path.exists(LOCAL_FILE):
        print(f"ERROR: Local file {LOCAL_FILE} not found!")
        return

    scp_cmd = f'scp -i {KEY_PATH} -o StrictHostKeyChecking=no {LOCAL_FILE} {SERVER_ADDR}:{REMOTE_FILE}'
    run_command(scp_cmd, "Uploading granular_logger.py")

    # 3. Start the Logger
    # We use nohup to keep it running after disconnect
    # We assume keys are already on the server in the home dir
    start_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "nohup python3 {REMOTE_FILE} > logger.log 2>&1 &"'
    run_command(start_cmd, "Starting Granular Logger")

    print("=== Deployment Complete ===")
    print("Logger updated and restarted.")
    print("Check logs with: ssh ... 'tail -f logger.log'")

if __name__ == "__main__":
    main()
