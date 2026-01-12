import sys
import os
from datetime import datetime
sys.path.append(os.getcwd())
from server_mirror.unified_engine.tick_sources import iter_ticks_from_market_logs

log_dir = "vm_logs/market_logs"
target_ticker = "KXHIGHNY-26JAN09-B49.5"
target_time = datetime.fromisoformat("2026-01-09T05:05:26.601875")

print(f"Scanning for {target_ticker} at {target_time}...")

ticks = iter_ticks_from_market_logs(log_dir)
found = False
count = 0

for tick in ticks:
    if tick['ticker'] == target_ticker:
        count += 1
        # Check if time matches exactly or is very close
        if tick['time'] == target_time:
            print("FOUND TICK!")
            print(tick)
            found = True
            break
        
        # If we passed the time, stop
        if tick['time'] > target_time:
            print(f"Passed target time. Last tick: {tick['time']}")
            break

if not found:
    print("Tick NOT found in iterator output.")
else:
    print("Tick found.")
