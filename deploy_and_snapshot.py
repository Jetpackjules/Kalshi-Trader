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
        print("OK\n")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {e}\n")
        # Don't exit immediately, try to continue if possible, or raise?
        # For killing process, failure might mean no process running.
        if "pkill" in cmd:
            print("(Process might not have been running; continuing.)")
            return
        else:
            raise e

def main():
    # Ensure snapshot dir exists
    if not os.path.exists(SNAPSHOT_LOCAL_DIR):
        os.makedirs(SNAPSHOT_LOCAL_DIR)

    # 1. Kill running Unified Engine processes (module + script)
    kill_cmd_module = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "pkill -f unified_engine.runner"'
    run_command(kill_cmd_module, "Killing running Unified Engine (module)")

    kill_cmd_script = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "pkill -f runner.py"'
    run_command(kill_cmd_script, "Killing running Unified Engine (runner.py)")

    # 2. Upload Files
    # Upload unified_engine sources
    files_to_upload = [
        ("server_mirror/unified_engine/runner.py", "unified_engine/runner.py"),
        ("server_mirror/unified_engine/adapters.py", "unified_engine/adapters.py"),
        ("server_mirror/unified_engine/engine.py", "unified_engine/engine.py"),
        ("server_mirror/unified_engine/tick_sources.py", "unified_engine/tick_sources.py"),
        ("server_mirror/backtesting/strategies/v3_variants.py", "backtesting/strategies/v3_variants.py"),
        ("server_mirror/backtesting/strategies/simple_market_maker.py", "backtesting/strategies/simple_market_maker.py"),
        ("server_mirror/backtesting/engine.py", "backtesting/engine.py"),
        ("run_bot.sh", "run_bot.sh"),
    ]
    
    # Ensure remote directory exists
    mkdir_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "mkdir -p unified_engine backtesting/strategies"'
    run_command(mkdir_cmd, "Creating remote unified_engine directory")

    for local_rel, remote_rel in files_to_upload:
        local_path = local_rel # Relative to CWD
        remote_path = f"{REMOTE_HOME}/{remote_rel}"
        
        if not os.path.exists(local_path):
            print(f"WARNING: {local_path} not found. Skipping.")
            continue
            
        scp_cmd = f'scp -i {KEY_PATH} -o StrictHostKeyChecking=no {local_path} {SERVER_ADDR}:{remote_path}'
        run_command(scp_cmd, f"Uploading {os.path.basename(local_path)}")

    # 3. Start the Unified Engine
    # Using run_bot.sh to handle quoting and startup
    start_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "chmod +x ~/run_bot.sh && ~/run_bot.sh"'
    run_command(start_cmd, "Starting Unified Engine (run_bot.sh)")

    print("=== Deployment Complete ===")
    print("Unified Engine has been restarted on the server.")
    print("(Granular Logger was NOT touched)")

if __name__ == "__main__":
    main()
