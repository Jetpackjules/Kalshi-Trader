"""
NCEI ASOS Module - Historical 5-minute ASOS data from NOAA archive
"""

import os
import re
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List
import pytz
from .base_api import BaseWeatherAPI


class NCEIASOS(BaseWeatherAPI):
    """NCEI ASOS for historical 5-minute data"""
    
    def __init__(self, station: str = "KNYC", data_dir: str = "asos_5min_data"):
        super().__init__("NCEI_ASOS", station)
        self.data_dir = data_dir
        self.base_url = "https://www.ncei.noaa.gov/data/automated-surface-observing-system-five-minute/access"
        os.makedirs(data_dir, exist_ok=True)
        
    def download_asos_file(self, year: int, month: int, force_redownload: bool = False) -> str:
        """Download ASOS data file for given year/month"""
        filename = f"asos-5min-{self.station}-{year:04d}{month:02d}.dat"
        local_path = os.path.join(self.data_dir, filename)
        
        # Check if we should re-download
        should_download = force_redownload or not os.path.exists(local_path)
        
        if os.path.exists(local_path) and not force_redownload:
            # Check if file is complete by looking at the last few lines
            try:
                with open(local_path, 'r') as f:
                    content = f.read()
                    # Count records for the last day of the month
                    from calendar import monthrange
                    last_day = monthrange(year, month)[1]
                    last_day_pattern = f"{month:02d}/{last_day:02d}/{str(year)[-2:]}"
                    last_day_count = content.count(last_day_pattern)
                    
                    # If we have less than 100 records for the last day, file is likely incomplete
                    if last_day_count < 100:
                        self.logger.warning(f"ASOS file {filename} appears incomplete ({last_day_count} records for last day). Re-downloading...")
                        should_download = True
                    else:
                        self.logger.debug(f"ASOS file already exists and appears complete: {filename}")
                        return local_path
            except Exception as e:
                self.logger.warning(f"Error checking ASOS file completeness: {e}. Re-downloading...")
                should_download = True
        
        if not should_download:
            return local_path
        
        url = f"{self.base_url}/{year}/{month:02d}/{filename}"
        
        try:
            self.logger.info(f"Downloading ASOS file: {filename} from {url}")
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            # Remove old file if it exists
            if os.path.exists(local_path):
                os.remove(local_path)
            
            with open(local_path, 'wb') as f:
                f.write(response.content)
            
            # Verify download
            file_size = len(response.content)
            self.logger.info(f"Downloaded ASOS file: {filename} ({file_size} bytes)")
            
            # Quick validation check
            if file_size < 1000:  # Very small file is suspicious
                self.logger.warning(f"Downloaded ASOS file {filename} is suspiciously small ({file_size} bytes)")
            
            return local_path
            
        except Exception as e:
            self.logger.error(f"Error downloading ASOS file {filename}: {e}")
            # Try alternative month format (sometimes files are delayed)
            if month > 1:
                self.logger.info(f"Trying previous month for missing data...")
                return self.download_asos_file(year, month - 1, force_redownload=True)
            return None
    
    def parse_asos_file(self, file_path: str, target_date: date) -> List[Dict]:
        """Parse ASOS data file and extract observations for target date"""
        if not os.path.exists(file_path):
            return []
        
        observations = []
        
        try:
            with open(file_path, 'r') as f:
                content = f.read().strip()
            
            # Split by station identifier
            records = re.split(r'(94728' + self.station + ')', content)
            records = [records[i] + records[i+1] for i in range(1, len(records) - 1, 2)]
            
            self.logger.debug(f"Found {len(records)} potential ASOS records")
            
            record_count = 0
            failed_count = 0
            
            for record in records:
                try:
                    if not record.startswith('94728' + self.station):
                        continue
                    
                    # Extract date (MM/DD/YY format)
                    date_match = re.search(r'(\d{2}/\d{2}/\d{2})', record[10:])
                    if not date_match:
                        continue
                    date_str = date_match.group(1)
                    
                    # Extract time (HH:MM:SS format)
                    time_match = re.search(r'(\d{2}:\d{2}:\d{2})', record[date_match.end()+10:])
                    if not time_match:
                        continue
                    time_str = time_match.group(1)
                    
                    # Find temperature after 'AUTO'
                    auto_index = record.find(' AUTO ')
                    if auto_index == -1:
                        continue
                    
                    remainder = record[auto_index + len(' AUTO '):].strip()
                    values = remainder.split()
                    
                    temp_dew_str = None
                    for val in values:
                        if '/' in val and len(val.split('/')) == 2:
                            temp_dew_str = val
                            break
                    
                    if not temp_dew_str:
                        continue
                    
                    # Parse datetime - ASOS timestamps are in UTC
                    year_part = f"20{date_str.split('/')[-1]}"
                    month_day_part = '/'.join(date_str.split('/')[:2])
                    full_date_str = f"{month_day_part}/{year_part}"
                    datetime_str = f"{full_date_str} {time_str}"
                    
                    timestamp_utc = pd.to_datetime(datetime_str, format='%m/%d/%Y %H:%M:%S', errors='coerce')
                    if pd.isna(timestamp_utc):
                        continue
                    
                    timestamp_utc = timestamp_utc.replace(tzinfo=pytz.UTC)
                    timestamp_local = timestamp_utc.astimezone(self.tz)
                    
                    # Use climate day window but applied to UTC timestamp
                    # For ASOS data, we need to use UTC bounds that correspond to the local climate day
                    # Local climate day: target_date 00:00 local to target_date+1 00:00 local
                    local_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, tzinfo=self.tz)
                    local_end = local_start + timedelta(days=1)
                    
                    # During DST, climate day ends at 01:00 local (next day)
                    if local_start.dst():
                        local_end += timedelta(hours=1)
                        
                    # Convert to UTC bounds - FIXED: Use proper timezone conversion
                    # The issue was that we need to convert local time to UTC properly
                    utc_start = local_start.astimezone(pytz.UTC)
                    utc_end = local_end.astimezone(pytz.UTC)
                    
                    # FIXED: ASOS data is in UTC, so we need to adjust bounds to match UTC data
                    # The ASOS data starts at 00:00 UTC for each day, not at the local time converted to UTC
                    # So we need to use UTC day bounds (00:00 UTC to 24:00 UTC) instead of local climate day bounds
                    utc_start = datetime(target_date.year, target_date.month, target_date.day, 0, 0, tzinfo=pytz.UTC)
                    utc_end = utc_start + timedelta(days=1)
                    
                    # Debug first few records
                    if failed_count == 0:
                        self.logger.info(f"UTC bounds: {utc_start} to {utc_end}")
                        self.logger.info(f"Sample UTC timestamp: {timestamp_utc}")
                        self.logger.info(f"Sample date string: {date_str}")
                        self.logger.info(f"Sample full datetime: {datetime_str}")
                        self.logger.info(f"Sample timestamp: {timestamp_local}")
                    
                    if not (utc_start <= timestamp_utc < utc_end):
                        failed_count += 1
                        continue
                    
                    record_count += 1
                    
                    # Extract temperature
                    temperature_str = temp_dew_str.split('/')[0]
                    if not temperature_str:
                        continue
                    
                    temp_c = float(temperature_str)
                    temp_f = temp_c * 9/5 + 32
                    
                    # Sanity check
                    if -80 <= temp_f <= 130:
                        observations.append({
                            'timestamp': timestamp_local,
                            'temp_f': temp_f,
                            'source_record': record[:100] + '...' if len(record) > 100 else record
                        })
                        
                except Exception as e:
                    self.logger.debug(f"Error parsing ASOS record: {e}")
                    continue
            
            self.logger.info(f"Parsed {len(observations)} ASOS observations for {target_date} (processed {record_count}, filtered out {failed_count})")
            return observations
            
        except Exception as e:
            self.logger.error(f"Error reading ASOS file {file_path}: {e}")
            return []
    
    def get_daily_max_temperature(self, target_date: date) -> Dict:
        """Get daily maximum temperature from NCEI ASOS data"""
        self.logger.info(f"Getting NCEI ASOS data for {target_date}")
        
        # Download file for this month if needed
        file_path = self.download_asos_file(target_date.year, target_date.month)
        if not file_path:
            # Try force re-download
            self.logger.warning(f"Initial download failed, forcing re-download for {target_date.year}-{target_date.month:02d}")
            file_path = self.download_asos_file(target_date.year, target_date.month, force_redownload=True)
            
            if not file_path:
                return {
                    'max_temp': None,
                    'max_time': None,
                    'count': 0,
                    'source': self.name,
                    'station': self.station,
                    'error': 'File download failed'
                }
        
        # Parse observations for target date
        observations = self.parse_asos_file(file_path, target_date)
        
        if not observations:
            # If no data found, try force re-downloading the file
            self.logger.warning(f"No observations found for {target_date}, forcing file re-download")
            file_path = self.download_asos_file(target_date.year, target_date.month, force_redownload=True)
            if file_path:
                observations = self.parse_asos_file(file_path, target_date)
            
            if not observations:
                return {
                    'max_temp': None,
                    'max_time': None,
                    'count': 0,
                    'source': self.name,
                    'station': self.station,
                    'error': f'No data found for {target_date}'
                }
        
        # Convert to DataFrame and find peak
        df = pd.DataFrame(observations)
        result = self.find_daily_peak(df, 'timestamp', 'temp_f')
        result['granularity'] = '5-minute'
        result['file_source'] = os.path.basename(file_path)
        
        self.logger.info(f"NCEI ASOS peak for {target_date}: {result['max_temp']}°F at {result['max_time']}")
        return result