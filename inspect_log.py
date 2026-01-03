import os

LOG_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\live_trader_v4.log"

def inspect_log():
    if not os.path.exists(LOG_FILE):
        print("Log file not found.")
        return

    print("Scanning log for 13:25...")
    with open(LOG_FILE, 'r', errors='ignore') as f:
        for line in f:
            if "13:25:" in line:
                print(line.strip())

if __name__ == "__main__":
    inspect_log()
