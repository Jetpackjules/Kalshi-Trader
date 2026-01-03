import os

LOG_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\live_trader_v4.log"

def check_log_range():
    if not os.path.exists(LOG_FILE):
        print("Log file not found.")
        return

    first_line = None
    last_line = None
    
    with open(LOG_FILE, 'r', errors='ignore') as f:
        # Read first line
        first_line = f.readline().strip()
        
        # Read last line
        f.seek(0, os.SEEK_END)
        pos = f.tell() - 2
        while pos > 0 and f.read(1) != "\n":
            pos -= 1
            f.seek(pos, os.SEEK_SET)
        last_line = f.readline().strip()
        
    print(f"First Line: {first_line}")
    print(f"Last Line: {last_line}")
    
    # Scan for dates
    print("Scanning for dates...")
    dates = set()
    import re
    with open(LOG_FILE, 'r', errors='ignore') as f:
        for line in f:
            match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
            if match:
                dates.add(match.group(1))
    
    print("Dates found in log:")
    for d in sorted(dates):
        print(d)

if __name__ == "__main__":
    check_log_range()
