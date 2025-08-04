"""
Kalshi API Module - For fetching betting market data
"""

import kalshi_python
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import logging
from .base_api import BaseWeatherAPI


class KalshiAPI(BaseWeatherAPI):
    """Kalshi API for betting market data"""
    
    def __init__(self, station: str = "KNYC", api_key_id: str = None, private_key: str = None):
        super().__init__("Kalshi_API", station)
        self.api_key_id = api_key_id
        self.private_key = private_key
        self.market_api = None
        self.exchange_api = None
        self._initialize_client()
        
    def _initialize_client(self):
        """Initialize the Kalshi API client"""
        try:
            # Create configuration
            configuration = kalshi_python.Configuration()
            configuration.host = "https://api.elections.kalshi.com/trade-api/v2"
            
            # Create API client
            api_client = kalshi_python.ApiClient(configuration)
            
            # Create API instances
            self.exchange_api = kalshi_python.ExchangeApi(api_client)
            self.market_api = kalshi_python.MarketApi(api_client)
            
            self.logger.info("Kalshi API client initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Kalshi client: {e}")
            self.market_api = None
            self.exchange_api = None
    
    def search_nhigh_markets(self) -> Dict:
        """Search for NHIGH (NYC High temperature) markets"""
        if not self.exchange_api:
            return {"events": [], "markets": []}
        
        try:
            self.logger.info("Searching for NHIGH markets...")
            
            # Get events for NHIGH series
            events_response = self.exchange_api.get_events(series_ticker="NHIGH")
            events = events_response.events if hasattr(events_response, 'events') else []
            
            if not events:
                self.logger.warning("No NHIGH events found")
                return {"events": [], "markets": []}
            
            self.logger.info(f"Found {len(events)} NHIGH events")
            
            # Get markets for each event
            all_markets = []
            for event in events:
                try:
                    event_ticker = event.get('event_ticker') if hasattr(event, 'get') else event.event_ticker
                    markets_response = self.exchange_api.get_markets(event_ticker=event_ticker)
                    markets = markets_response.markets if hasattr(markets_response, 'markets') else []
                    
                    for market in markets:
                        market_dict = market.to_dict() if hasattr(market, 'to_dict') else market
                        market_dict['parent_event'] = event.to_dict() if hasattr(event, 'to_dict') else event
                        all_markets.append(market_dict)
                        
                except Exception as e:
                    self.logger.error(f"Error getting markets for {event_ticker}: {e}")
            
            return {"events": events, "markets": all_markets}
            
        except Exception as e:
            self.logger.error(f"Error searching for NHIGH markets: {e}")
            return {"events": [], "markets": []}
    
    def get_settled_markets(self, markets: List[Dict]) -> pd.DataFrame:
        """Get settled/closed markets with results"""
        if not markets:
            return pd.DataFrame()
        
        results = []
        for market in markets:
            result_data = {
                'market_ticker': market.get('ticker', ''),
                'subtitle': market.get('subtitle', ''),
                'status': market.get('status', ''),
                'result': market.get('result', ''),
                'last_price': market.get('last_price'),
                'volume': market.get('volume', 0),
                'close_time': market.get('close_time', ''),
                'event_ticker': market.get('parent_event', {}).get('event_ticker', ''),
                'event_title': market.get('parent_event', {}).get('title', ''),
                'category': market.get('parent_event', {}).get('category', '')
            }
            results.append(result_data)
        
        df = pd.DataFrame(results)
        
        # Filter for settled markets
        if not df.empty:
            settled_df = df[df['status'].isin(['settled', 'closed', 'finalized'])]
            return settled_df
        
        return df
    
    def extract_temperature_from_market(self, market: Dict) -> Optional[float]:
        """Extract temperature value from market subtitle/result"""
        subtitle = market.get('subtitle', '').lower()
        result = market.get('result', '').lower()
        
        # Look for temperature patterns like "> 85°F", "85°F", "85 degrees"
        import re
        
        # Try to find temperature in subtitle or result
        text_to_search = f"{subtitle} {result}"
        
        # Pattern for temperatures like "85°F", "85 F", "85 degrees"
        temp_patterns = [
            r'(\d+(?:\.\d+)?)\s*°?[Ff]',  # 85°F, 85F
            r'(\d+(?:\.\d+)?)\s*degrees?\s*[Ff]',  # 85 degrees F
            r'(\d+(?:\.\d+)?)\s*[Ff]',  # 85 F
        ]
        
        for pattern in temp_patterns:
            match = re.search(pattern, text_to_search)
            if match:
                try:
                    temp = float(match.group(1))
                    return temp
                except ValueError:
                    continue
        
        return None
    
    def get_daily_max_temperature(self, target_date: date) -> Dict:
        """Get daily maximum temperature from Kalshi betting results"""
        self.logger.info(f"Getting Kalshi betting data for {target_date}")
        
        # Search for NHIGH markets
        nhigh_data = self.search_nhigh_markets()
        
        if not nhigh_data["markets"]:
            return {
                'max_temp': None,
                'max_time': None,
                'count': 0,
                'source': self.name,
                'station': self.station,
                'error': 'No NHIGH markets found'
            }
        
        # Get settled markets
        settled_df = self.get_settled_markets(nhigh_data["markets"])
        
        if settled_df.empty:
            return {
                'max_temp': None,
                'max_time': None,
                'count': 0,
                'source': self.name,
                'station': self.station,
                'error': 'No settled NHIGH markets found'
            }
        
        # Extract temperatures from market results
        temperatures = []
        for _, market in settled_df.iterrows():
            temp = self.extract_temperature_from_market(market.to_dict())
            if temp is not None:
                temperatures.append(temp)
        
        if not temperatures:
            return {
                'max_temp': None,
                'max_time': None,
                'count': 0,
                'source': self.name,
                'station': self.station,
                'error': 'No temperature data found in settled markets'
            }
        
        # Find the maximum temperature
        max_temp = max(temperatures)
        
        return {
            'max_temp': max_temp,
            'max_time': None,  # Kalshi doesn't provide exact timestamps
            'count': len(temperatures),
            'source': self.name,
            'station': self.station,
            'granularity': 'settled_market',
            'markets_analyzed': len(settled_df)
        } 