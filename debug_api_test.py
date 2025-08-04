#!/usr/bin/env python3
"""
Debug script to test all API modules and show max temps for past 7 days
"""

import logging
from datetime import date, timedelta
import pandas as pd

# Import our API modules
from modules.nws_api import NWSAPI
from modules.synoptic_api import SynopticAPI
from modules.ncei_asos import NCEIASOS

# Set up simple logging
logging.basicConfig(level=logging.ERROR)  # Only show errors

def test_api_modules():
    """Test each API module for past 3 weeks with aggressive fetching"""
    
    # Configuration
    station = "KNYC"
    end_date = date(2025, 7, 31)     # July 31st (end of July)
    start_date = end_date - timedelta(days=20)  # Past 3 weeks (21 days)
    
    print(f"🔧 DEBUG: Testing API modules for {station}")
    print(f"📅 Date range: {start_date} to {end_date}")
    print("=" * 80)
    
    # Initialize APIs
    apis = {
        'NWS API': NWSAPI(station),
        'Synoptic API': SynopticAPI(station), 
        'NCEI ASOS': NCEIASOS(station)
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
    
    print("\n" + "=" * 80)
    print("🏆 FINAL RESULTS TABLE - MAX TEMPERATURES BY API")
    print("=" * 80)
    print(df.to_string(index=False))
    print("=" * 80)
    
    # Save to CSV
    df.to_csv('debug_api_results.csv', index=False)
    print(f"📄 Results saved to: debug_api_results.csv")
    
    return df

if __name__ == "__main__":
    test_api_modules()