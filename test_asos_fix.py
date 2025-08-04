#!/usr/bin/env python3
"""Test the fixed ASOS module"""

import logging
from datetime import date
from modules.ncei_asos import NCEIASOS

# Set up logging to see debug info
logging.basicConfig(level=logging.INFO)

def test_asos_fix():
    print("🔧 Testing Fixed ASOS Module")
    
    asos = NCEIASOS("KNYC")
    
    # Test July 1st and July 30th (which exist in the file)
    for test_date in [date(2025, 7, 1), date(2025, 7, 30)]:
        print(f"\n📅 Testing {test_date}")
        result = asos.get_daily_max_temperature(test_date)
        
        if result.get('max_temp'):
            print(f"✅ {test_date}: {result['max_temp']}°F at {result.get('max_time')} ({result.get('count')} obs)")
        else:
            print(f"❌ {test_date}: {result.get('error', 'No data found')}")

if __name__ == "__main__":
    test_asos_fix()