import requests
import pandas as pd
from datetime import datetime, timezone
import time
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("weather_collector.log"),
        logging.StreamHandler()
    ]
)

DATA_FILE = "nws_weather_history.csv"
STATION_ID = "KNYC" # Central Park

def fetch_current_weather():
    """Fetches the latest observation from AWC API."""
    # KNYC = Central Park
    url = "https://aviationweather.gov/api/data/metar?ids=KNYC&format=json"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            logging.warning("No data returned from AWC")
            return None
            
        obs = data[0]
        
        # AWC returns 'obsTime' as string? Or int? 
        # In the comparison script it looked like an int/timestamp? 
        # Wait, the comparison script output: Time=1764024660
        # So it is a unix timestamp (int).
        
        timestamp = obs.get('obsTime')
        temp_c = obs.get('temp')
        
        if temp_c is None:
            logging.warning("Temperature value is None")
            return None

        temp_f = (temp_c * 9/5) + 32
        
        # Convert timestamp to ISO format for consistency
        if isinstance(timestamp, int):
            ts_iso = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        else:
            ts_iso = str(timestamp)
        
        return {
            "timestamp": ts_iso,
            "temp_c": temp_c,
            "temp_f": temp_f,
            "source": "AWC",
            "raw_data": str(obs)
        }
        
    except Exception as e:
        logging.error(f"Error fetching weather data: {e}")
        return None


def save_data(data):
    """Appends new data to CSV."""
    if not data:
        return

    df_new = pd.DataFrame([data])
    
    if os.path.exists(DATA_FILE):
        df_existing = pd.read_csv(DATA_FILE)
        # Avoid duplicates based on timestamp
        if data['timestamp'] not in df_existing['timestamp'].values:
            df_new.to_csv(DATA_FILE, mode='a', header=False, index=False)
            logging.info(f"Saved new data point: {data['timestamp']} - {data['temp_f']:.1f}F")
        else:
            logging.info(f"Data point already exists: {data['timestamp']}")
    else:
        df_new.to_csv(DATA_FILE, index=False)
        logging.info(f"Created new data file with: {data['timestamp']} - {data['temp_f']:.1f}F")

def main():
    logging.info("Starting Weather Data Collector...")
    while True:
        data = fetch_current_weather()
        save_data(data)
        
        # NWS updates hourly usually, but sometimes more often. 
        # 15 minutes is a safe polling interval to catch updates without spamming.
        time.sleep(900) 

if __name__ == "__main__":
    main()
