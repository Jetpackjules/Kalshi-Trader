import subprocess
import os
import sys
import shutil
import time
from datetime import datetime

# --- Configuration ---
# Paths relative to this script (live_trading_system/v2/)
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LIVE_SYSTEM_DIR = os.path.join(ROOT_DIR, 'live_trading_system')
SYNC_SCRIPT = os.path.join(LIVE_SYSTEM_DIR, 'sync_vm_logs.py')
LOGGER_SCRIPT = os.path.join(LIVE_SYSTEM_DIR, 'logger.py')
TRADER_SCRIPT = os.path.join(os.path.dirname(__file__), 'live_trader_v3.py')
LOG_DIR = os.path.join(LIVE_SYSTEM_DIR, 'vm_logs', 'market_logs')

import threading
import ctypes
import atexit

# --- Sleep Prevention ---
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

def prevent_sleep():
    """Prevents the system from entering sleep mode."""
    print("💤 Preventing System Sleep...")
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    )

def restore_sleep():
    """Restores normal sleep behavior."""
    print("💤 Restoring Sleep Behavior...")
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

atexit.register(restore_sleep)

def run_sim():
    print("=== Starting Local Simulation (Hybrid Mode) ===")
    prevent_sleep()
    
    # 1. Sync Logs from Server (ONCE)
    print("\n[Step 1] Syncing logs from server...")
    try:
        subprocess.run([sys.executable, SYNC_SCRIPT], check=True, cwd=LIVE_SYSTEM_DIR)
    except Exception as e:
        print(f"Error syncing logs: {e}")
        
    # 2. Start Local Logger (Background)
    print("\n[Step 2] Starting Local Logger (Auto-Restart Mode)...")
    logger_process = subprocess.Popen([sys.executable, LOGGER_SCRIPT], cwd=LIVE_SYSTEM_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)
    print(f"Logger started (PID: {logger_process.pid})")
    
    # 3. Start Live Trader V3 (Background)
    print("\n[Step 3] Starting Live Trader V3...")
    trader_process = subprocess.Popen([sys.executable, TRADER_SCRIPT], cwd=os.path.dirname(__file__))
    
    # 4. Watchdog Loop
    try:
        while True:
            # Check Logger
            if logger_process.poll() is not None:
                print(f"\n⚠️ Logger (PID: {logger_process.pid}) died! Restarting...")
                logger_process = subprocess.Popen([sys.executable, LOGGER_SCRIPT], cwd=LIVE_SYSTEM_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)
                print(f"✅ Logger restarted (PID: {logger_process.pid})")
                
            # Check Trader
            if trader_process.poll() is not None:
                print(f"\n❌ Trader died! Exiting simulation.")
                break
                
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nStopping Simulation...")
    finally:
        print("Terminating processes...")
        if logger_process.poll() is None: logger_process.terminate()
        if trader_process.poll() is None: trader_process.terminate()
        
if __name__ == "__main__":
    run_sim()
