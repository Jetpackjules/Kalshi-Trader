import pandas as pd
import os
import re
from datetime import datetime, timedelta

# Paths
VM_LOGS_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs"
TRADER_LOG = os.path.join(VM_LOGS_DIR, "live_trader_v4.log")

def extract_equity():
    print("Parsing trader log for equity curve...")
    equity_history = []
    
    current_date = datetime(2025, 12, 22).date() # Start looking from Dec 22
    last_time = None
    
    if os.path.exists(TRADER_LOG):
        with open(TRADER_LOG, 'r', errors='ignore') as f:
            for line in f:
                # Look for TICK lines to update current_date
                tick_match = re.search(r'TICK \S+ (\d{4}-\d{2}-\d{2})', line)
                if tick_match:
                    new_date = datetime.strptime(tick_match.group(1), "%Y-%m-%d").date()
                    if new_date > current_date:
                        current_date = new_date

                # Look for "--- Status @ HH:MM:SS ---"
                time_match = re.search(r'--- Status @ (\d{2}:\d{2}:\d{2}) ---', line)
                if time_match:
                    time_str = time_match.group(1)
                    t = datetime.strptime(time_str, "%H:%M:%S").time()
                    
                    # Detect date rollover (simple heuristic)
                    if last_time and t < last_time:
                         if (datetime.combine(datetime.min, last_time) - datetime.combine(datetime.min, t)).total_seconds() > 3600:
                            current_date += timedelta(days=1)
                    last_time = t
                    
                    # Read next line for Equity
                    try:
                        next_line = next(f)
                        equity_match = re.search(r'Equity: \$([\d\.]+)', next_line)
                        if equity_match:
                            equity = float(equity_match.group(1))
                            if current_date >= datetime(2025, 12, 23).date():
                                dt = datetime.combine(current_date, t)
                                equity_history.append({'timestamp': dt, 'date': current_date, 'equity': equity})
                    except StopIteration:
                        break
    
    if not equity_history:
        print("No equity data found.")
        return

    df = pd.DataFrame(equity_history)
    
    # Get last equity per day
    daily_equity = df.groupby('date')['equity'].last()
    
    print("\n=== REAL PORTFOLIO EQUITY CSV ===")
    print("Date,Equity")
    for date, equity in daily_equity.items():
        print(f"{date},{equity}")

if __name__ == "__main__":
    extract_equity()
