"""
Kalshi API Module - For fetching NWS CLI temperature data
Based on legacy_scripts/test.py - fetches NWS Climate products
"""

import requests
import re
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import logging
from .base_api import BaseWeatherAPI


class KalshiAPI(BaseWeatherAPI):
    """Kalshi API for fetching NWS CLI temperature data"""
    
    def __init__(self, station: str = "KNYC", issued_by: str = "NYC"):
        super().__init__("Kalshi_API", station)
        self.issued_by = issued_by
        self.user_agent = {"User-Agent": "kalshi-wsl (weather-data@example.com)"}
        self.logger.info("Kalshi API client initialized (NWS CLI fetcher)")
        
    def _parse_time(self, tok: str) -> str:
        """Parse time string like '207 AM' to '02:07'"""
        if not tok:
            return ""
        m = re.fullmatch(r"\s*(\d{1,4})\s*([AP]M)\s*", tok.upper())
        if not m:
            return ""
        n, ampm = m.groups()
        n = n.zfill(4)  # 207 -> 0207, 57 -> 0057
        hh, mm = int(n[:2]), int(n[2:])
        if ampm == "AM":
            hh = 0 if hh == 12 else hh
        else:
            hh = 12 if hh == 12 else hh + 12
        return f"{hh:02d}:{mm:02d}"
        
    def _extract_cli_data(self, text: str) -> Dict:
        """Extract temperature data from NWS CLI text"""
        # Date line like: "...SUMMARY FOR AUGUST 2 2025..."
        dm = re.search(r"SUMMARY FOR ([A-Z]+ \d{1,2} \d{4})", text)
        d_cli = dm.group(1).title() if dm else ""
        d_iso = ""
        try:
            d_iso = datetime.strptime(d_cli, "%B %d %Y").date().isoformat()
        except:
            pass

        # MAX/MIN with optional times
        mmax = re.search(r"(?m)^\s*MAXIMUM(?: TEMPERATURE \(F\))?\s+(\d{1,3})(?:\s+(\d{1,4}\s+[AP]M))?", text)
        mmin = re.search(r"(?m)^\s*MINIMUM(?: TEMPERATURE \(F\))?\s+(\d{1,3})(?:\s+(\d{1,4}\s+[AP]M))?", text)
        
        tmax = int(mmax.group(1)) if mmax else None
        tmin = int(mmin.group(1)) if mmin else None
        tmax_t = self._parse_time(mmax.group(2)) if (mmax and mmax.group(2)) else ""
        tmin_t = self._parse_time(mmin.group(2)) if (mmin and mmin.group(2)) else ""
        
        return {
            'date': d_iso or d_cli,
            'max_temp': tmax,
            'max_time': tmax_t,
            'min_temp': tmin,
            'min_time': tmin_t
        }
        
    def _fetch_cli(self, version: int) -> str:
        """Fetch NWS CLI product by version number"""
        url = (f"https://forecast.weather.gov/product.php?"
               f"site=NWS&issuedby={self.issued_by}&product=CLI&format=TXT&version={version}&glossary=0")
        r = requests.get(url, headers=self.user_agent, timeout=10)
        r.raise_for_status()
        return r.text
    
    def fetch_cli_data(self, days_back: int = 30) -> List[Dict]:
        """Fetch NWS CLI data for the past N days"""
        rows, seen = [], set()
        
        self.logger.info(f"Fetching NWS CLI data for past {days_back} days...")
        
        # Crawl back through versions to get enough unique days
        for v in range(0, min(120, days_back * 4)):  # More efficient: limit versions
            try:
                text = self._fetch_cli(v)
                data = self._extract_cli_data(text)
                
                if not data['date'] or data['date'] in seen:
                    continue
                    
                seen.add(data['date'])
                rows.append(data)
                
                if len(rows) >= days_back:
                    break
                    
            except requests.HTTPError:
                continue  # skip holes
            except Exception as e:
                self.logger.warning(f"Error fetching version {v}: {e}")
                continue
        
        # Sort chronologically if possible
        try:
            def sort_key(x):
                date_str = x['date']
                if isinstance(date_str, str) and '-' in date_str:
                    try:
                        return datetime.strptime(date_str, '%Y-%m-%d')
                    except:
                        return date_str
                return date_str
            rows.sort(key=sort_key)
        except:
            pass
            
        self.logger.info(f"Fetched {len(rows)} days of CLI data")
        return rows
    
    def get_daily_max_temperature(self, target_date: date) -> Dict:
        """Get daily max temperature for a specific date from NWS CLI data"""
        self.logger.info(f"Getting NWS CLI data for {target_date}")
        
        try:
            # Fetch CLI data for past 30 days to ensure we get the target date
            cli_data = self.fetch_cli_data(days_back=30)
            
            # Find the record for the target date
            target_date_str = target_date.isoformat()
            matching_record = None
            
            for record in cli_data:
                if record['date'] == target_date_str:
                    matching_record = record
                    break
            
            if matching_record and matching_record['max_temp'] is not None:
                max_temp = matching_record['max_temp']
                max_time = matching_record['max_time']
                
                return {
                    'max_temp': max_temp,
                    'max_time': max_time,
                    'count': 1,
                    'error': None,
                    'markets_analyzed': [matching_record]
                }
            else:
                return {
                    'max_temp': None,
                    'max_time': None,
                    'count': 0,
                    'error': f"No CLI data found for {target_date}",
                    'markets_analyzed': None
                }
                
        except Exception as e:
            self.logger.error(f"Error getting CLI data for {target_date}: {e}")
            return {
                'max_temp': None,
                'max_time': None,
                'count': 0,
                'error': str(e),
                'markets_analyzed': None
            } 