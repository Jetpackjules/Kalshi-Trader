"""
Base API module for weather data collection
Provides common functionality for all weather APIs
"""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
import zoneinfo
import pandas as pd

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class BaseWeatherAPI:
    """Base class for all weather APIs"""
    
    def __init__(self, name: str, station: str = "KNYC"):
        self.name = name
        self.station = station
        self.tz = zoneinfo.ZoneInfo("America/New_York")
        self.logger = logging.getLogger(f"WeatherAPI.{name}")
        
    def get_climate_day_window(self, target_date: date) -> Tuple[datetime, datetime]:
        """
        Get climate day window (00:00 LST to next 00:00 LST)
        During DST, climate day ends at 01:00 local clock time
        """
        start_local = datetime(target_date.year, target_date.month, target_date.day, 0, 0, tzinfo=self.tz)
        end_local = start_local + timedelta(days=1)
        
        # During DST, add an hour to maintain 24-hour period
        if start_local.dst():
            end_local += timedelta(hours=1)
            
        return start_local, end_local
    
    def find_daily_peak(self, data: pd.DataFrame, date_col: str = 'timestamp', temp_col: str = 'temp_f') -> Dict:
        """Find daily temperature peak from DataFrame"""
        if data.empty:
            return {
                'max_temp': None,
                'max_time': None,
                'count': 0,
                'source': self.name,
                'station': self.station
            }
        
        # Find peak
        idx = data[temp_col].idxmax()
        max_temp = float(data.loc[idx, temp_col])
        max_time = data.loc[idx, date_col]
        
        return {
            'max_temp': round(max_temp, 1),
            'max_time': max_time,
            'count': len(data),
            'source': self.name,
            'station': self.station
        }
    
    def get_daily_max_temperature(self, target_date: date) -> Dict:
        """Get daily maximum temperature - to be implemented by subclasses"""
        raise NotImplementedError("Subclasses must implement get_daily_max_temperature")
    
    def get_date_range_data(self, start_date: date, end_date: date) -> List[Dict]:
        """Get temperature data for a date range"""
        results = []
        current_date = start_date
        
        self.logger.info(f"Getting data from {start_date} to {end_date} for {self.station}")
        
        while current_date <= end_date:
            self.logger.debug(f"Processing {current_date}")
            try:
                daily_data = self.get_daily_max_temperature(current_date)
                daily_data['date'] = current_date
                results.append(daily_data)
            except Exception as e:
                self.logger.error(f"Error getting data for {current_date}: {e}")
                results.append({
                    'date': current_date,
                    'max_temp': None,
                    'max_time': None,
                    'count': 0,
                    'source': self.name,
                    'station': self.station,
                    'error': str(e)
                })
            
            current_date += timedelta(days=1)
        
        self.logger.info(f"Completed data collection: {len(results)} days processed")
        return results