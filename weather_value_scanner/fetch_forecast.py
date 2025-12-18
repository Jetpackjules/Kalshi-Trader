import requests
import json
from datetime import datetime

USER_AGENT = "(kalshi-weather-scanner, contact@example.com)"
KNYC_LAT = 40.7829
KNYC_LON = -73.9654

def get_gridpoint_url(lat, lon):
    url = f"https://api.weather.gov/points/{lat},{lon}"
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data['properties']['forecast']
    except Exception as e:
        print(f"Error getting gridpoint: {e}")
        return None

def get_nws_forecast():
    """
    Fetches the 7-day forecast for Central Park (KNYC).
    Returns a list of daily high temperatures.
    """
    # 1. Get Forecast URL (Cache this in production, but for now fetch it)
    # For KNYC (Central Park), the gridpoint is usually OKX/33,37
    # But best to fetch dynamically or hardcode if stable.
    
    # Hardcoding known KNYC gridpoint to save a call if possible, 
    # but let's be robust and fetch it first.
    forecast_url = get_gridpoint_url(KNYC_LAT, KNYC_LON)
    if not forecast_url:
        return []

    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(forecast_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        periods = data['properties']['periods']
        
        forecasts = {}
        for period in periods:
            # We want daily highs.
            # "isDaytime": true usually indicates the high for the day.
            if period['isDaytime']:
                # Parse startTime: "2025-12-06T13:00:00-05:00"
                dt_str = period['startTime']
                # We only care about the date part for matching
                # Handle timezone if needed, but for matching "NOV26" date is usually enough.
                # Python 3.7+ handles isoformat.
                dt = datetime.fromisoformat(dt_str)
                date_key = dt.date() # datetime.date object
                
                forecasts[date_key] = {
                    'name': period['name'],
                    'temp': period['temperature'],
                    'detailed': period['detailedForecast']
                }
        return forecasts
    except Exception as e:
        print(f"Error fetching forecast: {e}")
        return {}

if __name__ == "__main__":
    print("Fetching NWS Forecast for Central Park...")
    forecasts = get_nws_forecast()
    for date, data in forecasts.items():
        print(f"{date} ({data['name']}): {data['temp']} F")
