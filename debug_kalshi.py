#!/usr/bin/env python3
"""
Debug Kalshi API module individually
"""

import logging
from datetime import date
from modules.kalshi_api import KalshiAPI

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)

def debug_kalshi():
    print("🔧 Debugging Kalshi API Module (NWS CLI)")
    
    # Test the Kalshi API
    try:
        kalshi = KalshiAPI("KNYC")
        print("✅ Kalshi API initialized")
        
        # Test fetching CLI data
        print("\n🔍 Testing CLI data fetch...")
        cli_data = kalshi.fetch_cli_data(days_back=10)
        print(f"📊 Fetched {len(cli_data)} days of CLI data")
        
        if cli_data:
            print("\n📋 Sample CLI data:")
            for record in cli_data[:3]:
                print(f"  - {record['date']}: Max {record['max_temp']}°F at {record['max_time']}, Min {record['min_temp']}°F at {record['min_time']}")
        
        # Test the get_daily_max_temperature method
        print("\n🔍 Testing get_daily_max_temperature...")
        test_date = date(2025, 7, 29)  # Use a recent date
        result = kalshi.get_daily_max_temperature(test_date)
        
        print(f"📅 Result for {test_date}:")
        print(f"  - Max temp: {result.get('max_temp')}°F")
        print(f"  - Max time: {result.get('max_time')}")
        print(f"  - Count: {result.get('count')}")
        print(f"  - Error: {result.get('error')}")
        print(f"  - Markets analyzed: {result.get('markets_analyzed')}")
        
    except Exception as e:
        print(f"💥 Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_kalshi() 