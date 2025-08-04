"""
NWS API Module - Official National Weather Service observations
"""

import requests
import pandas as pd
from datetime import datetime, timedelta, date
from typing import Dict, List
import zoneinfo
from .base_api import BaseWeatherAPI


class NWSAPI(BaseWeatherAPI):
    """NWS API for weather observations"""
    
    def __init__(self, station: str = "KNYC"):
        super().__init__("NWS_API", station)
        self.base_url = "https://api.weather.gov/stations"
        self.headers = {"User-Agent": "nyc-temp-check (you@example.com)"}
        
    def fetch_observations(self, start_utc: datetime, end_utc: datetime) -> List[Dict]:
        """Fetch observations from NWS API"""
        url = f"{self.base_url}/{self.station}/observations"
        params = {
            "start": start_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "end": end_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "limit": 500
        }
        
        observations = []
        
        while True:
            try:
                self.logger.debug(f"Requesting NWS data: {url} with params {params}")
                response = requests.get(url, params=params, headers=self.headers, timeout=20)
                response.raise_for_status()
                
                data = response.json()
                features = data.get("features", [])
                
                for feature in features:
                    props = feature["properties"]
                    temp_data = props.get("temperature", {})
                    temp_c = temp_data.get("value")
                    qc = str(temp_data.get("qualityControl", "V"))
                    
                    # Only accept valid or corrected data
                    if temp_c is None or qc not in ("V", "C"):
                        continue
                    
                    timestamp_str = props["timestamp"]
                    timestamp_utc = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    temp_f = temp_c * 9/5 + 32
                    
                    # Basic sanity check
                    if -80 <= temp_f <= 130:
                        observations.append({
                            "timestamp_utc": timestamp_utc,
                            "temp_f": temp_f,
                            "quality": qc
                        })
                
                # Handle pagination
                links = response.links or {}
                next_link = links.get("next", {}).get("url")
                if not next_link:
                    break
                    
                url, params = next_link, {}
                
            except Exception as e:
                self.logger.error(f"Error fetching NWS data: {e}")
                break
        
        self.logger.info(f"Fetched {len(observations)} NWS observations")
        return observations
    
    def fetch_observations_no_qc(self, start_utc: datetime, end_utc: datetime) -> List[Dict]:
        """Fetch observations without quality control filtering (fallback)"""
        url = f"{self.base_url}/{self.station}/observations"
        params = {
            "start": start_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "end": end_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "limit": 500
        }
        
        observations = []
        
        try:
            self.logger.info(f"Trying NWS fallback (no QC filter) for {self.station}")
            response = requests.get(url, params=params, headers=self.headers, timeout=20)
            response.raise_for_status()
            
            data = response.json()
            features = data.get("features", [])
            
            for feature in features:
                props = feature["properties"]
                temp_data = props.get("temperature", {})
                temp_c = temp_data.get("value")
                
                # Accept any temperature data (no QC filter)
                if temp_c is None:
                    continue
                
                timestamp_str = props["timestamp"]
                timestamp_utc = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                temp_f = temp_c * 9/5 + 32
                
                # Basic sanity check
                if -80 <= temp_f <= 130:
                    observations.append({
                        "timestamp_utc": timestamp_utc,
                        "temp_f": temp_f,
                        "quality": "U"  # Unknown quality
                    })
            
            self.logger.info(f"Fetched {len(observations)} NWS observations (no QC)")
            
        except Exception as e:
            self.logger.error(f"Error in NWS fallback fetch: {e}")
        
        return observations
    
    def get_daily_max_temperature(self, target_date: date) -> Dict:
        """Get daily maximum temperature from NWS API"""
        start_local, end_local = self.get_climate_day_window(target_date)
        start_utc = start_local.astimezone(zoneinfo.ZoneInfo("UTC"))
        end_utc = end_local.astimezone(zoneinfo.ZoneInfo("UTC"))
        
        self.logger.info(f"Getting NWS data for {target_date} ({start_local} to {end_local})")
        
        observations = self.fetch_observations(start_utc, end_utc)
        
        # If no data found, try extending the search window
        if not observations:
            self.logger.warning(f"No NWS data found for {target_date}, trying extended time window")
            
            # Try extending backward/forward by 12 hours
            extended_start = start_utc - timedelta(hours=12)
            extended_end = end_utc + timedelta(hours=12)
            
            self.logger.info(f"Trying extended NWS window: {extended_start} to {extended_end}")
            observations = self.fetch_observations(extended_start, extended_end)
            
            # Filter to original date range after fetching
            if observations:
                df_temp = pd.DataFrame(observations)
                df_temp['timestamp_local'] = df_temp['timestamp_utc'].dt.tz_convert(self.tz)
                df_temp = df_temp[
                    (df_temp['timestamp_local'] >= start_local) & 
                    (df_temp['timestamp_local'] <= end_local)
                ]
                observations = df_temp.to_dict('records')
        
        # If still no data, try alternative station endpoints
        if not observations:
            self.logger.warning(f"Still no NWS data, trying alternative approaches for {target_date}")
            
            # Try without quality control filter
            observations = self.fetch_observations_no_qc(start_utc, end_utc)
        
        if not observations:
            return {
                'max_temp': None,
                'max_time': None,
                'count': 0,
                'source': self.name,
                'station': self.station,
                'error': f'No NWS data available for {target_date}'
            }
        
        # Convert to DataFrame and find peak
        df = pd.DataFrame(observations)
        df['timestamp'] = df['timestamp_utc'].dt.tz_convert(self.tz)
        
        result = self.find_daily_peak(df, 'timestamp', 'temp_f')
        result['quality_flags'] = df['quality'].unique().tolist()
        
        self.logger.info(f"NWS peak for {target_date}: {result['max_temp']}°F at {result['max_time']}")
        return result