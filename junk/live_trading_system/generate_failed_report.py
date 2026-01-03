import re
import os

LOG_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\live_trader_v4.log"
REPORT_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\failed_report.md"

def generate_report():
    if not os.path.exists(LOG_FILE):
        print(f"Log file not found: {LOG_FILE}")
        return

    failed_orders = []
    current_time = "Unknown"
    last_signal = ""
    
    with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            
            # Time
            time_match = re.search(r"--- Status @ (\d{2}:\d{2}:\d{2}) ---", line)
            if time_match:
                current_time = time_match.group(1)
                continue

            # Signal
            if line.startswith("SIGNAL"):
                last_signal = line
                continue

            # Failure Intent
            if "(will place)" in line:
                parts = line.split()
                if len(parts) > 1:
                    ticker = parts[1]
                    details = "N/A"
                    if ticker in last_signal:
                        if "|" in last_signal:
                            details = last_signal.split("|")[1].strip()
                    
                    failed_orders.append({
                        "time": current_time,
                        "ticker": ticker,
                        "details": details
                    })

    # Write Report
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"### Failed Order Attempts (Ghost Orders)\n\n")
        f.write(f"**Total Attempts:** {len(failed_orders)}\n\n")
        f.write("| Time | Ticker | Signal Details |\n")
        f.write("|---|---|---|\n")
        
        # Show last 15
        for order in failed_orders[-15:]:
            f.write(f"| {order['time']} | `{order['ticker']}` | {order['details']} |\n")
            
    print(f"Report generated at {REPORT_FILE}")

if __name__ == "__main__":
    generate_report()
