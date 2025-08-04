#!/usr/bin/env python3
"""
Simple API test to check basic functionality
"""

from datetime import date
from modules.nws_api import NWSAPI
from modules.synoptic_api import SynopticAPI
from modules.ncei_asos import NCEIASOS

def simple_test():
    print("🔧 Simple API Test")
    
    # Test July 1st, 2025
    test_date = date(2025, 7, 1)
    print(f"📅 Testing {test_date}")
    
    # Test ASOS (which we know works)
    try:
        asos = NCEIASOS("KNYC")
        result = asos.get_daily_max_temperature(test_date)
        if result.get('max_temp'):
            print(f"✅ ASOS: {result['max_temp']}°F")
        else:
            print(f"❌ ASOS: {result.get('error', 'No data')}")
    except Exception as e:
        print(f"💥 ASOS Error: {e}")
    
    # Test NWS API
    try:
        nws = NWSAPI("KNYC")
        result = nws.get_daily_max_temperature(test_date)
        if result.get('max_temp'):
            print(f"✅ NWS: {result['max_temp']}°F")
        else:
            print(f"❌ NWS: {result.get('error', 'No data')}")
    except Exception as e:
        print(f"💥 NWS Error: {e}")
    
    # Test Synoptic API
    try:
        synoptic = SynopticAPI("KNYC")
        result = synoptic.get_daily_max_temperature(test_date)
        if result.get('max_temp'):
            print(f"✅ Synoptic: {result['max_temp']}°F")
        else:
            print(f"❌ Synoptic: {result.get('error', 'No data')}")
    except Exception as e:
        print(f"💥 Synoptic Error: {e}")

if __name__ == "__main__":
    simple_test() 