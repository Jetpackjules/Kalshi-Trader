
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from unified_engine.tick_sources import iter_ticks_from_market_logs

def main():
    log_dir = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\vm_logs\market_logs"
    print(f"Reading ticks from {log_dir}...")
    
    ticks = iter_ticks_from_market_logs(log_dir)
    
    target_time_str = "2026-01-09T05:05:26"
    target_time = datetime.fromisoformat(target_time_str)
    
    found = False
    with open("reproduce_output.txt", "w") as f:
        for tick in ticks:
            if tick["time"] >= target_time:
                # Print ticks for the next few seconds
                if (tick["time"] - target_time).total_seconds() > 2:
                    break
                    
                f.write(f"Tick: {tick['time']} {tick['ticker']} Row: {tick['source_row']}\n")
                ms = tick['market_state']
                yes_bid = ms.get('yes_bid')
                yes_ask = ms.get('yes_ask')
                f.write(f"  Bid: {yes_bid}, Ask: {yes_ask}\n")
                if yes_bid is not None and yes_ask is not None:
                    mid = (yes_bid + yes_ask) / 2.0
                    f.write(f"  Mid: {mid}\n")
                f.write("-" * 20 + "\n")
                found = True

        if not found:
            f.write("Target time not reached.\n")

if __name__ == "__main__":
    main()
