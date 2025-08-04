#!/usr/bin/env python3
"""Debug ASOS parsing logic"""

import re
import logging
from datetime import date, timedelta, datetime
from modules.ncei_asos import NCEIASOS

# Set up logging to see debug info
logging.basicConfig(level=logging.DEBUG)

def debug_asos_parsing():
    print("🔍 Debugging ASOS Parsing Logic - Bounds Calculation")
    
    # Test both July 1st and July 30th to understand the bounds issue
    test_dates = [date(2025, 7, 1), date(2025, 7, 30)]
    
    for test_date in test_dates:
        print(f"\n📅 Testing bounds for {test_date}")
        
        # Calculate bounds manually
        import zoneinfo
        import pytz
        
        tz = zoneinfo.ZoneInfo("America/New_York")
        
        # Local climate day bounds
        local_start = datetime(test_date.year, test_date.month, test_date.day, 0, 0, tzinfo=tz)
        local_end = local_start + timedelta(days=1)
        
        # During DST, climate day ends at 01:00 local (next day)
        if local_start.dst():
            local_end += timedelta(hours=1)
        
        # Convert to UTC
        utc_start = local_start.astimezone(pytz.UTC)
        utc_end = local_end.astimezone(pytz.UTC)
        
        print(f"🔍 Local bounds: {local_start} to {local_end}")
        print(f"🔍 UTC bounds: {utc_start} to {utc_end}")
        print(f"🔍 Local timezone: {tz}")
        print(f"🔍 DST active: {local_start.dst()}")
        
        # Test with a sample record from that date
        if test_date == date(2025, 7, 1):
            sample_record = "94728KNYC NYC20250701000011907/01/25 00:00:31  5-MIN KNYC 010500Z AUTO 00000KT 9SM FEW019 SCT120 26/22 A2993 150 79 1500 000/00 RMK AO2 T02560217 $"
            expected_date_str = "07/01/25"
        else:
            sample_record = "94728KNYC NYC20250730000009907/30/25 00:00:31  5-MIN KNYC 300500Z AUTO 10SM CLR 29/21 A3000 90 60 1800 M /M RMK AO2 T02940211 $"
            expected_date_str = "07/30/25"
        
        # Parse the sample record
        date_match = re.search(r'(\d{2}/\d{2}/\d{2})', sample_record[10:])
        time_match = re.search(r'(\d{2}:\d{2}:\d{2})', sample_record[date_match.end()+10:])
        
        date_str = date_match.group(1)
        time_str = time_match.group(1)
        
        # Parse datetime
        year_part = f"20{date_str.split('/')[-1]}"
        month_day_part = '/'.join(date_str.split('/')[:2])
        full_date_str = f"{month_day_part}/{year_part}"
        datetime_str = f"{full_date_str} {time_str}"
        
        import pandas as pd
        timestamp_utc = pd.to_datetime(datetime_str, format='%m/%d/%Y %H:%M:%S', errors='coerce')
        timestamp_utc = timestamp_utc.replace(tzinfo=pytz.UTC)
        timestamp_local = timestamp_utc.astimezone(tz)
        
        print(f"🔍 Record datetime: {datetime_str}")
        print(f"🔍 Record UTC: {timestamp_utc}")
        print(f"🔍 Record local: {timestamp_local}")
        print(f"🔍 In bounds: {utc_start <= timestamp_utc < utc_end}")
        
        if utc_start <= timestamp_utc < utc_end:
            print("✅ Record would be accepted!")
        else:
            print("❌ Record would be filtered out!")
            
            # Show the time difference
            if timestamp_utc < utc_start:
                diff = utc_start - timestamp_utc
                print(f"🔍 Record is {diff} before start bound")
            else:
                diff = timestamp_utc - utc_end
                print(f"🔍 Record is {diff} after end bound")

if __name__ == "__main__":
    debug_asos_parsing()