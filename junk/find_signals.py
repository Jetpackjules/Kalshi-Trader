import os

LOG_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\live_trader_v4.log"

def find_buy_signals():
    if not os.path.exists(LOG_FILE):
        print("Log file not found.")
        return

    print("Scanning log for 'SIGNAL' and 'BUY'...")
    count = 0
    with open(LOG_FILE, 'r', errors='ignore') as f:
        for line in f:
            if "SIGNAL" in line and "BUY" in line:
                print(line.strip())
                count += 1
                if count > 20:
                    print("... (limit reached)")
                    break

if __name__ == "__main__":
    find_buy_signals()
