import re
import os

LOG_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\live_trader_v4.log"

def extract_failed_orders():
    if not os.path.exists(LOG_FILE):
        print(f"Log file not found: {LOG_FILE}")
        return

    failed_orders = []
    current_time = "Unknown Time"
    last_signal = ""

    print(f"Scanning {LOG_FILE}...")
    
    with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            
            # Track Time from Status updates
            # Example: --- Status @ 15:55:07 ---
            time_match = re.search(r"--- Status @ (\d{2}:\d{2}:\d{2}) ---", line)
            if time_match:
                current_time = time_match.group(1)
                continue

            # Track Signal details
            # Example: SIGNAL KXHIGHNY-26JAN03-B29.5 1 | SIGNAL BUY_NO 1 @ 86
            if line.startswith("SIGNAL"):
                last_signal = line
                continue

            # Detect Failed Placement Intent
            # Example: NEW KXHIGHNY-26JAN03-B29.5 unsatisfied=1 (will place)
            if "(will place)" in line:
                # Extract Ticker from the line
                # NEW <ticker> ...
                parts = line.split()
                if len(parts) > 1:
                    ticker = parts[1]
                    
                    # Parse details from last_signal if it matches ticker
                    details = "Details not found"
                    if ticker in last_signal:
                        # Extract "BUY_NO 1 @ 86" part
                        if "|" in last_signal:
                            details = last_signal.split("|")[1].strip()
                    
                    failed_orders.append({
                        "time": current_time,
                        "ticker": ticker,
                        "details": details
                    })

    # Print Results
    print(f"\nFound {len(failed_orders)} attempted (but failed) orders.")
    print(f"{'TIME':<10} | {'TICKER':<25} | {'DETAILS'}")
    print("-" * 60)
    
    # Show last 20 for brevity
    for order in failed_orders[-20:]:
        print(f"{order['time']:<10} | {order['ticker']:<25} | {order['details']}")

if __name__ == "__main__":
    extract_failed_orders()
