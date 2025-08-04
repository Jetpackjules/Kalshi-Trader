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
    
    print(f"🔧 Kalshi vs Weather APIs Comparison")
    print(f"📅 Date range: {start_date} to {end_date}")
    print("=" * 100)
    
    # Initialize APIs
    apis = {
        'NWS API': NWSAPI(station),
        'Synoptic API': SynopticAPI(station), 
        'NCEI ASOS': NCEIASOS(station),
        'Kalshi Betting': KalshiAPI(station)
    }
    
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
    print("🏆 FINAL COMPARISON TABLE - KALSHI vs WEATHER APIS")
    print("=" * 100)
    print(df.to_string(index=False))
    print("=" * 100)
    
    # Calculate differences between Kalshi and weather APIs
    print("\n📊 TEMPERATURE DIFFERENCES ANALYSIS:")
    print("=" * 100)
    
    for index, row in df.iterrows():
        date_str = row['Date']
        kalshi_temp = row['Kalshi Betting']
        
        if kalshi_temp != "No data" and "Error" not in kalshi_temp:
            # Extract temperature from Kalshi result
            try:
                kalshi_value = float(kalshi_temp.split('°F')[0])
                
                # Compare with each weather API
                weather_apis = ['NWS API', 'Synoptic API', 'NCEI ASOS']
                differences = []
                
                for api_name in weather_apis:
                    weather_temp = row[api_name]
                    if weather_temp != "No data" and "Error" not in weather_temp:
                        try:
                            weather_value = float(weather_temp.split('°F')[0])
                            diff = kalshi_value - weather_value
                            differences.append(f"{api_name}: {diff:+.1f}°F")
                        except:
                            differences.append(f"{api_name}: N/A")
                    else:
                        differences.append(f"{api_name}: No data")
                
                print(f"📅 {date_str}: Kalshi {kalshi_value:.1f}°F")
                for diff in differences:
                    print(f"    vs {diff}")
                print()
                
            except ValueError:
                print(f"📅 {date_str}: Could not parse Kalshi temperature")
                print()
    
    # Save to CSV
    df.to_csv('kalshi_vs_weather_comparison.csv', index=False)
    print(f"📄 Results saved to: kalshi_vs_weather_comparison.csv")
    
    return df

if __name__ == "__main__":
    compare_kalshi_vs_weather() 