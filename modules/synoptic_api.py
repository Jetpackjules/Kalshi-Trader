"""
Synoptic API Module - High-frequency weather data (5-minute granularity)
"""

import requests
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict
from .base_api import BaseWeatherAPI


class SynopticAPI(BaseWeatherAPI):
    """Synoptic API for high-resolution weather data"""
    
    def __init__(self, station: str = "KNYC", token: str = "ee1f7ca7e6ae46aca3bc8693e1205e03"):
        super().__init__("Synoptic_API", station)
        self.token = token
        self.base_url = "https://api.synopticdata.com/v2/stations/timeseries"
        
    def format_datetime(self, dt: datetime) -> str:
        """Format datetime for Synoptic API (YYYYmmddHHMM)"""
        return dt.strftime("%Y%m%d%H%M")
    
    def fetch_synoptic_data(self, start_local: datetime, end_local: datetime) -> pd.DataFrame:
        """Fetch data from Synoptic API"""
        params = {
            "stid": self.station,
            "vars": "air_temp",
            "start": self.format_datetime(start_local),
            "end": self.format_datetime(end_local),
            "units": "temp|F",
            "obtimezone": "local",
            "token": self.token
        }
        
        self.logger.debug(f"Requesting Synoptic data with params: {params}")
        
        try:
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if not data.get("STATION"):
                self.logger.warning("No station data in Synoptic response")
                return pd.DataFrame(columns=["timestamp", "temp_f"])
            
            station_data = data["STATION"][0].get("OBSERVATIONS", {})
            
            # Handle both possible temperature data shapes (from legacy code)
            vals = None
            vobj = station_data.get("air_temp_value_1")
            if isinstance(vobj, dict) and isinstance(vobj.get("value"), list):
                vals = vobj["value"]
            if vals is None and isinstance(station_data.get("air_temp_set_1"), list):
                vals = station_data["air_temp_set_1"]
            
            # Get timestamps - prefer local, fall back to others (from legacy code)
            times = (station_data.get("date_time_local") or 
                    station_data.get("date_time") or 
                    station_data.get("date_time_utc") or [])
            
            if not vals or not times:
                self.logger.warning(f"No valid temperature or time data. Vals: {len(vals) if vals else 0}, Times: {len(times)}")
                return pd.DataFrame(columns=["timestamp", "temp_f"])
            
            # Parse timestamps and temperatures
            observations = []
            for t, v in zip(times, vals):
                if v is None:
                    continue
                try:
                    # Parse timestamp using legacy logic
                    t = str(t).replace(" ", "T")
                    if t.endswith("Z"):
                        dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
                    elif t[-5] in "+-" and len(t) >= 5:  # Handle -0400 format
                        if ":" not in t[-5:]:  # Need to add colon
                            t = t[:-2] + ":" + t[-2:]
                        dt = datetime.fromisoformat(t)
                    else:
                        dt = datetime.fromisoformat(t)
                    
                    ts_local = dt.astimezone(self.tz)
                    temp_f = float(v)
                    
                    # Sanity bounds
                    if -80 < temp_f < 130:
                        observations.append({"timestamp": ts_local, "temp_f": temp_f})
                        
                except Exception as e:
                    self.logger.debug(f"Error parsing timestamp {t} or temp {v}: {e}")
                    continue
            
            if not observations:
                self.logger.warning("No valid observations after parsing")
                return pd.DataFrame(columns=["timestamp", "temp_f"])
            
            df = pd.DataFrame(observations).sort_values("timestamp")
            
            self.logger.info(f"Fetched {len(df)} Synoptic observations")
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching Synoptic data: {e}")
            return pd.DataFrame(columns=["timestamp", "temp_f"])
    
    def get_daily_max_temperature(self, target_date: date) -> Dict:
        """Get daily maximum temperature from Synoptic API"""
        start_local, end_local = self.get_climate_day_window(target_date)
        
        self.logger.info(f"Getting Synoptic data for {target_date} ({start_local} to {end_local})")
        
        df = self.fetch_synoptic_data(start_local, end_local)
        
        # If no data, try with extended window
        if df.empty:
            self.logger.warning(f"No Synoptic data for {target_date}, trying extended window")
            extended_start = start_local - timedelta(hours=6)
            extended_end = end_local + timedelta(hours=6)
            
            self.logger.info(f"Trying extended Synoptic window: {extended_start} to {extended_end}")
            df = self.fetch_synoptic_data(extended_start, extended_end)
            
            # Filter back to original window
            if not df.empty:
                df = df[
                    (df["timestamp"] >= start_local) & 
                    (df["timestamp"] <= end_local)
                ]
        
        if df.empty:
            return {
                'max_temp': None,
                'max_time': None,
                'count': 0,
                'source': self.name,
                'station': self.station,
                'error': f'No Synoptic data available for {target_date}'
            }
        
        result = self.find_daily_peak(df, 'timestamp', 'temp_f')
        result['granularity'] = '5-minute'
        
        self.logger.info(f"Synoptic peak for {target_date}: {result['max_temp']}°F at {result['max_time']}")
        return result