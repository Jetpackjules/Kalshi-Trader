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
    files_to_upload = []
    
    # Helper to recursively add files from a directory
    def add_directory(local_dir, remote_prefix):
        if not os.path.exists(local_dir):
            print(f"WARNING: Directory {local_dir} not found. Skipping.")
            return

        for root, dirs, files in os.walk(local_dir):
            for file in files:
                if file.endswith(".py") or file.endswith(".json") or file.endswith(".txt"):
                    local_path = os.path.join(root, file)
                    # remote path needs to be relative to the expected structure on server
                    # local_dir = server_mirror/unified_engine
                    # remote_prefix = unified_engine
                    rel_path = os.path.relpath(local_path, start=local_dir)
                    remote_file_path = os.path.join(remote_prefix, rel_path).replace("\\", "/")
                    files_to_upload.append((local_path, remote_file_path))

    # Add all files from unified_engine
    add_directory("server_mirror/unified_engine", "unified_engine")
    
    # Add all files from backtesting/strategies
    add_directory("server_mirror/backtesting/strategies", "backtesting/strategies")

    # Add specific files
    files_to_upload.append(("server_mirror/backtesting/engine.py", "backtesting/engine.py"))
    files_to_upload.append(("run_bot.sh", "run_bot.sh"))
    
    # Ensure remote directory exists
    # We might need to make subdirectories if the structure is deep
    # For now, let's just make the base dirs and hope scp handles it or we pre-create
    # Actually scp fails if dir doesn't exist. We should collect all remote dirs and mkdir them.
    remote_dirs = set()
    for _, remote_rel in files_to_upload:
        remote_dirs.add(os.path.dirname(remote_rel))
    
    mkdir_chain = " ".join([f'"{d}"' for d in remote_dirs if d])
    if mkdir_chain:
        mkdir_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "mkdir -p {mkdir_chain}"'
        run_command(mkdir_cmd, "Creating remote directories")

    for local_rel, remote_rel in files_to_upload:
        local_path = local_rel # Relative to CWD
        remote_path = f"{REMOTE_HOME}/{remote_rel}"
        
        if not os.path.exists(local_path):
            print(f"WARNING: {local_path} not found. Skipping.")
            continue
            
        scp_cmd = f'scp -i {KEY_PATH} -o StrictHostKeyChecking=no {local_path} {SERVER_ADDR}:{remote_path}'
        run_command(scp_cmd, f"Uploading {os.path.basename(local_path)}")

    # 2b. Reset output log on fresh deploy so each run starts clean
    reset_log_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "truncate -s 0 ~/output.log"'
    run_command(reset_log_cmd, "Resetting output.log")

    # 2c. Reset trade_debug log on fresh deploy
    reset_trade_debug_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "mkdir -p ~/unified_engine_out && truncate -s 0 ~/unified_engine_out/trade_debug.csv"'
    run_command(reset_trade_debug_cmd, "Resetting trade_debug.csv")

    # 2d. Reset fills log on fresh deploy
    reset_fills_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "mkdir -p ~/unified_engine_out && truncate -s 0 ~/unified_engine_out/fills.csv"'
    run_command(reset_fills_cmd, "Resetting fills.csv")

    # 3. Start the Unified Engine
    # Using run_bot.sh to handle quoting and startup
    start_cmd = f'ssh -i {KEY_PATH} -o StrictHostKeyChecking=no {SERVER_ADDR} "chmod +x ~/run_bot.sh && ~/run_bot.sh"'
    run_command(start_cmd, "Starting Unified Engine (run_bot.sh)")

    print("=== Deployment Complete ===")
    print("Unified Engine has been restarted on the server.")
    print("(Granular Logger was NOT touched)")

if __name__ == "__main__":
    main()
