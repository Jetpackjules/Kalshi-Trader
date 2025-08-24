#!/usr/bin/env python3
"""
Simple NWS API script for NYC temperature data.
Gets all temperature observations for a given time range at Central Park (KNYC).
Bare minimum but functional - designed to be copied to other AIs.
"""

import requests
import json
from datetime import datetime, timedelta
import pandas as pd

def get_nyc_temperature_data(start_date, end_date):
    """
    Get all temperature observations from NWS API for Central Park NYC.
    
    Args:
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
    
    Returns:
        list: All temperature observations with timestamps
    """
    
    # NWS API endpoints - NO KEYS NEEDED!
    STATION_ID = "KNYC"  # Central Park, NYC (same as Kalshi uses)
    BASE_URL = "https://api.weather.gov"
    
    # Convert dates to ISO format for API
    start_iso = f"{start_date}T00:00:00Z"
    end_iso = f"{end_date}T23:59:59Z"
    
    # NWS API URL for observations
    url = f"{BASE_URL}/stations/{STATION_ID}/observations"
    
    headers = {
        'User-Agent': 'TemperatureBot/1.0 (contact@example.com)'  # NWS requires User-Agent
    }
    
    params = {
        'start': start_iso,
        'end': end_iso
    }
    
    print(f"🌡️  Getting NYC temperature data from {start_date} to {end_date}")
    print(f"📡 URL: {url}")
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        observations = data.get('features', [])
        
        print(f"✅ Got {len(observations)} temperature observations")
        
        # Extract temperature data
        temp_data = []
        for obs in observations:
            props = obs.get('properties', {})
            
            # Get timestamp
            timestamp = props.get('timestamp')
            if not timestamp:
                continue
                
            # Get temperature (in Celsius, convert to Fahrenheit)
            temp_c = props.get('temperature', {})
            if temp_c and temp_c.get('value') is not None:
                temp_f = (temp_c['value'] * 9/5) + 32
                
                temp_data.append({
                    'timestamp': timestamp,
                    'temperature_f': round(temp_f, 1),
                    'temperature_c': round(temp_c['value'], 1)
                })
        
        # Sort by timestamp
        temp_data.sort(key=lambda x: x['timestamp'])
        
        return temp_data
        
    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
        return []
    except Exception as e:
        print(f"❌ Error processing data: {e}")
        return []

def find_daily_max_temperature(temp_data, target_date):
    """
    Find the maximum temperature for a specific date.
    
    Args:
        temp_data (list): Temperature observations from get_nyc_temperature_data()
        target_date (str): Date in 'YYYY-MM-DD' format
    
    Returns:
        dict: Max temperature info for the day
    """
    
    daily_temps = []
    
    for obs in temp_data:
        # Extract date from timestamp
        obs_date = obs['timestamp'][:10]  # YYYY-MM-DD part
        
        if obs_date == target_date:
            daily_temps.append(obs)
    
    if not daily_temps:
        return {'date': target_date, 'max_temp_f': None, 'max_temp_time': None}
    
    # Find maximum temperature
    max_obs = max(daily_temps, key=lambda x: x['temperature_f'])
    
    return {
        'date': target_date,
        'max_temp_f': max_obs['temperature_f'],
        'max_temp_time': max_obs['timestamp'],
        'total_observations': len(daily_temps)
    }

# EXAMPLE USAGE
if __name__ == "__main__":
    
    # Example: Get last 7 days of data
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    print("🚀 SIMPLE NWS API FOR NYC TEMPERATURE DATA")
    print("=" * 50)
    
    # Get all temperature data
    temp_data = get_nyc_temperature_data(start_date, end_date)
    
    if temp_data:
        print(f"\n📊 Sample of data (first 5 observations):")
        for i, obs in enumerate(temp_data[:5]):
            print(f"  {obs['timestamp']}: {obs['temperature_f']}°F")
        
        print(f"\n🌡️  Daily maximum temperatures:")
        
        # Calculate daily maxes
        current_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        
        while current_date <= end_date_obj:
            date_str = current_date.strftime('%Y-%m-%d')
            daily_max = find_daily_max_temperature(temp_data, date_str)
            
            if daily_max['max_temp_f']:
                print(f"  {date_str}: {daily_max['max_temp_f']}°F at {daily_max['max_temp_time'][11:16]} ({daily_max['total_observations']} obs)")
            else:
                print(f"  {date_str}: No data")
            
            current_date += timedelta(days=1)
        
        # Save to CSV for other AI
        df = pd.DataFrame(temp_data)
        csv_file = f"nyc_temps_{start_date}_to_{end_date}.csv"
        df.to_csv(csv_file, index=False)
        print(f"\n💾 Data saved to: {csv_file}")
        
    else:
        print("❌ No data retrieved")
    
    print(f"\n🔧 HOW TO USE THIS SCRIPT:")
    print("1. Change start_date and end_date variables")
    print("2. Run: python3 simple_nws_api.py")
    print("3. Data saved to CSV file automatically")
    print("4. No API keys needed - NWS API is free!")
    print("5. Station: KNYC (Central Park) - same as Kalshi settlements")