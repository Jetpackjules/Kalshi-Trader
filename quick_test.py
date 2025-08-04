#!/usr/bin/env python3
"""
Quick test - ASOS only
"""

from datetime import date
from modules.ncei_asos import NCEIASOS

def quick_test():
    print("🔧 Quick ASOS Test")
    
    test_date = date(2025, 7, 1)
    print(f"📅 Testing {test_date}")
    
    asos = NCEIASOS("KNYC")
    result = asos.get_daily_max_temperature(test_date)
    
    if result.get('max_temp'):
        print(f"✅ ASOS: {result['max_temp']}°F at {result.get('max_time')}")
    else:
        print(f"❌ ASOS: {result.get('error', 'No data')}")

if __name__ == "__main__":
    quick_test() 