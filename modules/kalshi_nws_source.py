"""
Kalshi NWS Source Data Module - Official settlement data for Kalshi temperature markets
Gets data from the same NWS Daily Climate Report that Kalshi uses for settlement
"""

import requests
import re
import pandas as pd
import pytz
from datetime import datetime, date, timedelta
from typing import Dict, Optional
from bs4 import BeautifulSoup
from .base_api import BaseWeatherAPI


class KalshiNWSSource(BaseWeatherAPI):
    """Kalshi NWS Source - Official settlement data from NWS Daily Climate Report"""
    
    def __init__(self, station: str = "KNYC"):
        super().__init__("Kalshi_NWS_Source", station)
        # Map station codes to NWS site codes
        self.station_map = {
            "KNYC": "okx",  # Central Park, NY (Kalshi settlement station)
            "KLGA": "okx",  # LaGuardia
            "KJFK": "okx",  # JFK
            "KEWR": "okx"   # Newark
        }
        self.nws_site = self.station_map.get(station, "okx")
        self.base_url = f"https://www.weather.gov/wrh/climate"
        
    def get_climate_report_url(self, target_date: date) -> str:
        """Get URL for NWS climate report for specific date and station"""
        # NWS climate reports are available the day after
        report_date = target_date + timedelta(days=1)
        
        return (f"{self.base_url}?wfo={self.nws_site}&"
                f"date={report_date.strftime('%m/%d/%Y')}&"
                f"station={self.station}")
    
    def fetch_climate_report(self, target_date: date) -> Optional[str]:
        """Fetch NWS climate report HTML"""
        url = self.get_climate_report_url(target_date)
        
        try:
            self.logger.debug(f"Fetching NWS climate report: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.text
            
        except Exception as e:
            self.logger.error(f"Error fetching NWS climate report: {e}")
            return None
    
    def parse_max_temperature(self, html_content: str, target_date: date) -> Optional[float]:
        """Parse maximum temperature from NWS climate report HTML"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for temperature table or observed weather section
            # The structure may vary, so we'll try multiple approaches
            
            # Method 1: Look for "Yesterday" section in temperature table
            tables = soup.find_all('table')
            for table in tables:
                # Look for temperature-related headers
                headers = table.find_all(['th', 'td'])
                for i, header in enumerate(headers):
                    header_text = header.get_text().strip().lower()
                    if 'maximum' in header_text and 'temperature' in header_text:
                        # Try to find the corresponding value
                        try:
                            value_cell = headers[i + 1] if i + 1 < len(headers) else None
                            if value_cell:
                                temp_text = value_cell.get_text().strip()
                                temp_match = re.search(r'(\d+)', temp_text)
                                if temp_match:
                                    return float(temp_match.group(1))
                        except (IndexError, ValueError):
                            continue
            
            # Method 2: Look for specific patterns in text
            text_content = soup.get_text()
            
            # Pattern for "Maximum: XX" or "Max: XX"
            max_patterns = [
                r'Maximum:?\s*(\d+)',
                r'Max:?\s*(\d+)',
                r'High:?\s*(\d+)',
                r'Yesterday.*?Maximum.*?(\d+)',
                r'(\d+)°?\s*F?\s*Maximum'
            ]
            
            for pattern in max_patterns:
                match = re.search(pattern, text_content, re.IGNORECASE)
                if match:
                    temp = float(match.group(1))
                    if 0 <= temp <= 130:  # Sanity check
                        self.logger.debug(f"Found max temp using pattern '{pattern}': {temp}°F")
                        return temp
            
            # Method 3: Look in observed weather section
            observed_sections = soup.find_all(text=re.compile(r'observed.*weather', re.IGNORECASE))
            for section in observed_sections:
                parent = section.parent
                if parent:
                    section_text = parent.get_text()
                    temp_match = re.search(r'(\d+)°?\s*F?', section_text)
                    if temp_match:
                        temp = float(temp_match.group(1))
                        if 0 <= temp <= 130:
                            return temp
            
            self.logger.warning(f"Could not parse max temperature from NWS climate report for {target_date}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error parsing NWS climate report: {e}")
            return None
    
    def get_daily_max_temperature(self, target_date: date) -> Dict:
        """Get daily maximum temperature from NWS Daily Climate Report (Kalshi source)"""
        self.logger.info(f"Getting Kalshi NWS source data for {target_date}")
        
        # Fetch the climate report
        html_content = self.fetch_climate_report(target_date)
        if not html_content:
            return {
                'max_temp': None,
                'max_time': None,  # Climate report doesn't include time
                'count': 0,
                'source': self.name,
                'station': self.station,
                'error': 'Failed to fetch climate report'
            }
        
        # Parse maximum temperature
        max_temp = self.parse_max_temperature(html_content, target_date)
        
        if max_temp is None:
            return {
                'max_temp': None,
                'max_time': None,
                'count': 0,
                'source': self.name,
                'station': self.station,
                'error': 'Failed to parse temperature from report'
            }
        
        # NWS Daily Climate Report doesn't provide exact time of max temp
        # It's typically reported as a daily summary
        estimated_time = datetime.combine(target_date, datetime.min.time().replace(hour=15)) # Assume 3 PM typical peak
        estimated_time = estimated_time.replace(tzinfo=self.tz)
        
        result = {
            'max_temp': max_temp,
            'max_time': estimated_time,  # Estimated time since climate report doesn't specify
            'count': 1,  # Daily summary, not individual observations
            'source': self.name,
            'station': self.station,
            'report_type': 'daily_climate_summary',
            'is_official_kalshi_source': True
        }
        
        self.logger.info(f"Kalshi NWS source for {target_date}: {max_temp}°F (official settlement data)")
        return result
    
    def get_alternative_source(self, target_date: date) -> Dict:
        """Alternative method using NWS API daily summaries if climate reports fail"""
        try:
            # Use NWS API for daily summaries as backup
            url = f"https://api.weather.gov/stations/{self.station}/observations"
            
            # Get the day's data
            start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=self.tz)
            end_dt = start_dt + timedelta(days=1)
            
            params = {
                "start": start_dt.astimezone(pytz.UTC).isoformat(),
                "end": end_dt.astimezone(pytz.UTC).isoformat(),
                "limit": 500
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            features = data.get("features", [])
            
            if not features:
                return None
            
            # Find max temperature from all observations
            max_temp = None
            max_time = None
            
            for feature in features:
                props = feature["properties"]
                temp_data = props.get("temperature", {})
                temp_c = temp_data.get("value")
                
                if temp_c is not None:
                    temp_f = temp_c * 9/5 + 32
                    if max_temp is None or temp_f > max_temp:
                        max_temp = temp_f
                        max_time = datetime.fromisoformat(props["timestamp"].replace("Z", "+00:00"))
            
            if max_temp is not None:
                return {
                    'max_temp': round(max_temp, 1),
                    'max_time': max_time.astimezone(self.tz),
                    'count': len(features),
                    'source': f"{self.name}_API_Backup",
                    'station': self.station
                }
            
        except Exception as e:
            self.logger.error(f"Error with alternative NWS source: {e}")
        
        return None