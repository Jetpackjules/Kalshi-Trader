import requests
import pandas as pd
from datetime import datetime
import pytz
import time
import os
import sys

# Configuration
STATION_ID = "KNYC"
URL = f"https://aviationweather.gov/api/data/metar?ids={STATION_ID}&format=json"
LOG_FILE = "nws_latency_log.csv"
POLL_INTERVAL = 1 # seconds

def get_pst_time():
    return datetime.now(pytz.timezone('US/Pacific'))

def fetch_nws_data():
    try:
        response = requests.get(URL)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list) and len(data) > 0:
                return data[0]
    except Exception as e:
        print(f"Error fetching NWS data: {e}")
    return None

def main():
    print(f"📡 Starting NWS Latency Monitor for {STATION_ID}...")
    print(f"Logging to: {os.path.abspath(LOG_FILE)}")
    print("Press Ctrl+C to stop.\n")
    
    # Initialize CSV if not exists
    if not os.path.exists(LOG_FILE):
        df = pd.DataFrame(columns=['fetch_time_pst', 'nws_timestamp_pst', 'delay_minutes', 'temperature_f', 'raw_timestamp'])
        df.to_csv(LOG_FILE, index=False)
    
    last_nws_ts = None
    
    try:
        while True:
            fetch_time = get_pst_time()
            data = fetch_nws_data()
            
            if data:
                raw_ts = data['obsTime']
                temp_c = data['temp']
                temp_f = (temp_c * 9/5) + 32 if temp_c is not None else None
                
                # Convert NWS timestamp to PST
                # Handle Unix timestamp (int or string) or ISO string
                try:
                    # Try as unix timestamp first if it looks numeric
                    if isinstance(raw_ts, (int, float)) or (isinstance(raw_ts, str) and raw_ts.replace('.', '', 1).isdigit()):
                        nws_dt_utc = pd.to_datetime(raw_ts, unit='s', utc=True)
                    else:
                        nws_dt_utc = pd.to_datetime(raw_ts)
                        if nws_dt_utc.tz is None:
                            nws_dt_utc = nws_dt_utc.tz_localize('UTC')
                except Exception as e:
                    print(f"Error parsing timestamp {raw_ts}: {e}")
                    continue

                nws_dt_pst = nws_dt_utc.tz_convert('US/Pacific')
                
                # Calculate Delay
                delay = fetch_time - nws_dt_pst
                delay_minutes = delay.total_seconds() / 60
                
                # Log if it's a new timestamp OR just periodically to show we are alive?
                # User wants to "continually refresh... and then save".
                # Let's log every unique timestamp we see.
                # AND maybe log duplicates every 10 mins?
                # For now, let's log EVERY fetch so the user can see the "waiting" period.
                # But that fills the CSV.
                # Let's log ONLY when the timestamp CHANGES from what we last saw.
                # This captures the "Arrival Time".
                
                if raw_ts != last_nws_ts:
                    print(f"[{fetch_time.strftime('%H:%M:%S')}] 🆕 NEW DATA! NWS Time: {nws_dt_pst.strftime('%H:%M:%S')} | Temp: {temp_f:.1f}F | Delay: {delay_minutes:.1f} min")
                    
                    new_row = {
                        'fetch_time_pst': fetch_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'nws_timestamp_pst': nws_dt_pst.strftime('%Y-%m-%d %H:%M:%S'),
                        'delay_minutes': round(delay_minutes, 2),
                        'temperature_f': temp_f,
                        'raw_timestamp': raw_ts
                    }
                    
                    # Append to CSV
                    pd.DataFrame([new_row]).to_csv(LOG_FILE, mode='a', header=False, index=False)
                    last_nws_ts = raw_ts
                else:
                    # Optional: Print heartbeat
                    print(f"[{fetch_time.strftime('%H:%M:%S')}] ... No change. Latest: {nws_dt_pst.strftime('%H:%M')} ({delay_minutes:.1f} min old)")
            
            else:
                print(f"[{fetch_time.strftime('%H:%M:%S')}] ❌ Failed to fetch data.")
            
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitor stopped.")

if __name__ == "__main__":
    main()
