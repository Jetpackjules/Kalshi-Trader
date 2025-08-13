#!/usr/bin/env python3
"""
Kalshi vs Weather APIs Comparison
Compare betting market results with actual weather data
"""

import logging
from datetime import date, timedelta
import pandas as pd

# Import our API modules
from modules.nws_api import NWSAPI
from modules.synoptic_api import SynopticAPI
from modules.ncei_asos import NCEIASOS
from modules.kalshi_api import KalshiAPI

# Set up logging
logging.basicConfig(level=logging.ERROR)  # Only show errors

def compare_kalshi_vs_weather():
    """Compare Kalshi betting results with actual weather data"""
    
    # Configuration
    station = "KNYC"
    end_date = date(2025, 7, 31)     # July 31st (end of July)
    start_date = end_date - timedelta(days=20)  # Past 3 weeks (21 days)
    
    print(f"🔧 Weather APIs Comparison (including NWS CLI)")
    print(f"📅 Date range: {start_date} to {end_date}")
    print("=" * 100)
    
    # Initialize APIs
    apis = {
        'NWS API': NWSAPI(station),
        'Synoptic API': SynopticAPI(station), 
        'NCEI ASOS': NCEIASOS(station),
        'NWS CLI': KalshiAPI(station)  # This is actually NWS CLI data, not betting
    }
    
    print("ℹ️  Note: 'NWS CLI' is actually NWS Climate data (not betting markets)")
    print("   This provides official NWS daily temperature summaries for NYC Central Park")
    print()
    
    # Collect data for each day
    results = []
    
    current_date = start_date
    while current_date <= end_date:
        print(f"\n📅 Testing {current_date}:")
        
        row = {'Date': current_date.strftime('%Y-%m-%d')}
        
        for api_name, api_instance in apis.items():
            try:
                result = api_instance.get_daily_max_temperature(current_date)
                
                if result.get('max_temp'):
                    max_temp = result['max_temp']
                    max_time = result.get('max_time')
                    count = result.get('count', 0)
                    
                    if max_time:
                        time_str = max_time.strftime('%H:%M')
                        row[api_name] = f"{max_temp:.1f}°F ({time_str})"
                        print(f"  ✅ {api_name}: {max_temp:.1f}°F at {time_str} ({count} obs)")
                    else:
                        row[api_name] = f"{max_temp:.1f}°F"
                        print(f"  ✅ {api_name}: {max_temp:.1f}°F ({count} obs)")
                else:
                    row[api_name] = "No data"
                    error = result.get('error', 'Unknown error')
                    print(f"  ❌ {api_name}: No data - {error}")
                    
            except Exception as e:
                row[api_name] = f"Error: {str(e)[:30]}..."
                print(f"  💥 {api_name}: Exception - {e}")
        
        results.append(row)
        current_date += timedelta(days=1)
    
    # Create and display results table
    df = pd.DataFrame(results)
    
    print("\n" + "=" * 100)
    print("🏆 FINAL COMPARISON TABLE - WEATHER APIS")
    print("=" * 100)
    print(df.to_string(index=False))
    print("=" * 100)
    
    # Calculate differences between weather APIs
    print("\n📊 WEATHER API COMPARISON ANALYSIS:")
    print("=" * 100)
    
    for index, row in df.iterrows():
        date_str = row['Date']
        
        # Get temperatures from each API
        temps = {}
        for api_name in ['NWS API', 'Synoptic API', 'NCEI ASOS', 'NWS CLI']:
            temp_str = row[api_name]
            if temp_str != "No data" and "Error" not in temp_str:
                try:
                    temp_value = float(temp_str.split('°F')[0])
                    temps[api_name] = temp_value
                except:
                    temps[api_name] = None
            else:
                temps[api_name] = None
        
        # Show comparison if we have at least 2 valid temperatures
        valid_temps = {k: v for k, v in temps.items() if v is not None}
        if len(valid_temps) >= 2:
            print(f"📅 {date_str}:")
            for api_name, temp in valid_temps.items():
                print(f"    {api_name}: {temp:.1f}°F")
            
            # Calculate differences
            if len(valid_temps) >= 2:
                temp_values = list(valid_temps.values())
                max_temp = max(temp_values)
                min_temp = min(temp_values)
                diff = max_temp - min_temp
                print(f"    Range: {diff:.1f}°F (Max: {max_temp:.1f}°F, Min: {min_temp:.1f}°F)")
                
                # Highlight if NWS CLI is the outlier
                if 'NWS CLI' in valid_temps:
                    cli_temp = valid_temps['NWS CLI']
                    other_temps = [v for k, v in valid_temps.items() if k != 'NWS CLI']
                    if other_temps:
                        avg_other = sum(other_temps) / len(other_temps)
                        cli_diff = abs(cli_temp - avg_other)
                        if cli_diff > 2.0:  # More than 2°F difference
                            print(f"    ⚠️  NWS CLI differs by {cli_diff:.1f}°F from average ({avg_other:.1f}°F)")
            print()
    
    # Save to CSV
    df.to_csv('weather_apis_comparison.csv', index=False)
    print(f"📄 Results saved to: weather_apis_comparison.csv")
    
    return df

if __name__ == "__main__":
    compare_kalshi_vs_weather() 