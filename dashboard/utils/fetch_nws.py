import requests
import pandas as pd
from datetime import datetime, timedelta
import time

USER_AGENT = "(kalshi-weather-dashboard, contact@example.com)"

def get_nws_history(start_date: datetime, end_date: datetime, station="KNYC"):
    """
    Fetch historical observations from NWS API for a specific station.
    Note: NWS API only keeps ~7 days of history on the /observations endpoint.
    For older data, we might need a different source, but for "recent" markets this works.
    """
    url = f"https://api.weather.gov/stations/{station}/observations"
    headers = {"User-Agent": USER_AGENT}
    
    # NWS pagination is by 'limit' (default 500, usually enough for 7 days)
    # or we can filter by start/end time in the URL if supported, 
    # but /observations usually returns the last N records.
    # Let's try fetching the last 7 days (max usually available) and filtering locally.
    
    params = {
        "start": start_date.isoformat() + "Z",
        "end": end_date.isoformat() + "Z",
    }
    
    # The API often ignores start/end on this endpoint and just gives recent.
    # We'll fetch recent and filter.
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        features = data.get('features', [])
        observations = []
        
        for feature in features:
            props = feature.get('properties', {})
            timestamp = props.get('timestamp')
            temp_c = props.get('temperature', {}).get('value')
            
            if timestamp and temp_c is not None:
                # Convert C to F
                temp_f = (temp_c * 9/5) + 32
                observations.append({
                    "timestamp": timestamp,
                    "temp_f": temp_f
                })
                
        df = pd.DataFrame(observations)
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            # Filter by requested range
            # Ensure timezone awareness compatibility
            start_date = pd.Timestamp(start_date).tz_localize('UTC') if start_date.tzinfo is None else start_date
            end_date = pd.Timestamp(end_date).tz_localize('UTC') if end_date.tzinfo is None else end_date
            
            mask = (df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)
            return df.loc[mask]
            
        return pd.DataFrame()
        
    except Exception as e:
        print(f"Error fetching NWS data: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    # Test
    end = datetime.utcnow()
    start = end - timedelta(days=3)
    df = get_nws_history(start, end)
    print(df.head())
    print(f"Found {len(df)} observations")
