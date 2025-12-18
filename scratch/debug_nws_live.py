import requests
from datetime import datetime, timezone
import pytz
import pandas as pd

def check_nws_freshness():
    url = "https://api.weather.gov/stations/KNYC/observations"
    print(f"Fetching from: {url}")
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        features = data.get('features', [])
        if not features:
            print("No features found.")
            return

        # Get latest observation
        latest = features[0]['properties']
        raw_ts = latest['timestamp']
        temp_c = latest['temperature']['value']
        temp_f = (temp_c * 9/5) + 32 if temp_c is not None else None
        
        print(f"\nRaw Timestamp: {raw_ts}")
        
        # Convert
        dt_utc = pd.to_datetime(raw_ts)
        dt_pst = dt_utc.tz_convert('US/Pacific')
        dt_est = dt_utc.tz_convert('US/Eastern')
        
        print(f"UTC Time: {dt_utc}")
        print(f"ET Time:  {dt_est}")
        print(f"PST Time: {dt_pst}")
        
        now_pst = datetime.now(pytz.timezone('US/Pacific'))
        print(f"\nCurrent System Time (PST): {now_pst}")
        
        diff = now_pst - dt_pst
        print(f"Age: {diff}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_nws_freshness()
