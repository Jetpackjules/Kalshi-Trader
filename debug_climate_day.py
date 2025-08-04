#!/usr/bin/env python3
"""Debug climate day logic"""

import zoneinfo
from datetime import datetime, date, timedelta
import pytz

def debug_climate_day():
    print("🔧 DEBUG: Climate Day Logic")
    
    target_date = date(2025, 7, 30)
    tz = zoneinfo.ZoneInfo("America/New_York")
    
    print(f"📅 Target date: {target_date}")
    
    # Test the climate day window logic
    target_start = tz.localize(datetime(target_date.year, target_date.month, target_date.day, 0, 0))
    target_end = target_start + timedelta(days=1)
    
    # During DST, climate day ends at 01:00 local (next day)
    if target_start.dst():
        target_end += timedelta(hours=1)
    
    print(f"🔍 Climate day window: {target_start} to {target_end}")
    
    # Test a sample UTC timestamp from the file
    sample_utc_str = "07/30/2025 00:00:31"
    timestamp_utc = datetime.strptime(sample_utc_str, '%m/%d/%Y %H:%M:%S')
    timestamp_utc = timestamp_utc.replace(tzinfo=pytz.UTC)
    timestamp_local = timestamp_utc.astimezone(tz)
    
    print(f"🔍 Sample UTC time: {timestamp_utc}")
    print(f"🔍 Sample local time: {timestamp_local}")
    print(f"🔍 In climate window: {target_start <= timestamp_local < target_end}")
    
    # Test another timestamp later in the day
    sample_utc_str2 = "07/30/2025 12:00:31"
    timestamp_utc2 = datetime.strptime(sample_utc_str2, '%m/%d/%Y %H:%M:%S')
    timestamp_utc2 = timestamp_utc2.replace(tzinfo=pytz.UTC)
    timestamp_local2 = timestamp_utc2.astimezone(tz)
    
    print(f"🔍 Sample UTC time 2: {timestamp_utc2}")
    print(f"🔍 Sample local time 2: {timestamp_local2}")
    print(f"🔍 In climate window 2: {target_start <= timestamp_local2 < target_end}")

if __name__ == "__main__":
    debug_climate_day()