#!/usr/bin/env python3
"""
Kalshi Temperature Market Monitor

Continuously monitors ALL temperature markets on Kalshi and saves snapshots to CSV.
Runs every 30 seconds to capture market data before expiration.

Usage:
    python kalshi_temperature_monitor.py

Data saved to: data/kalshi_temp_markets_YYYYMMDD.csv
"""

import requests
import pandas as pd
import time
import json
from datetime import datetime, timezone
from pathlib import Path
import logging
from typing import Dict, List, Optional
import signal
import sys
from auth_config import get_kalshi_api_credentials, api_credentials_available, generate_kalshi_headers

class KalshiTempMonitor:
    def __init__(self, api_base: str = "https://trading-api.kalshi.com/trade-api/v2"):
        self.api_base = api_base
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'kalshi-temp-monitor/1.0 (temperature-analysis@example.com)',
            'Accept': 'application/json'
        })
        
        # Store API credentials
        self.api_key = None
        self.private_key = None
        self.setup_api_credentials()
        
        # Setup data directory
        self.data_dir = Path(__file__).parent / "data"
        self.data_dir.mkdir(exist_ok=True)
        
        # Setup logging
        self.setup_logging()
        
        # Track running state
        self.running = True
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.logger.info("🌡️ Kalshi Temperature Monitor initialized")
        
    def setup_api_credentials(self):
        """Setup Kalshi API credentials"""
        if not api_credentials_available():
            self.logger.error("❌ No Kalshi API credentials found!")
            self.logger.error("Please set KALSHI_API_KEY and KALSHI_PRIVATE_KEY environment variables")
            self.logger.error("Or create a .env file with your API credentials")
            self.logger.error("Get credentials at: https://kalshi.com/account/profile")
            return False
            
        self.api_key, self.private_key = get_kalshi_api_credentials()
        self.logger.info("✅ Kalshi API credentials loaded")
        return True
        
    def add_auth_headers(self, method: str, path: str):
        """Add authentication headers to session"""
        if not self.api_key or not self.private_key:
            return
            
        try:
            auth_headers = generate_kalshi_headers(method, path, self.api_key, self.private_key)
            self.session.headers.update(auth_headers)
        except Exception as e:
            self.logger.error(f"❌ Failed to generate auth headers: {e}")
        
    def setup_logging(self):
        """Setup logging configuration"""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(self.data_dir / 'monitor.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"🛑 Received signal {signum}, shutting down gracefully...")
        self.running = False
        
    def get_temperature_markets(self) -> List[Dict]:
        """Fetch all temperature-related markets from Kalshi"""
        try:
            # Use events endpoint with proper auth
            path = "/events"
            self.add_auth_headers("GET", path)
            
            url = f"{self.api_base}{path}"
            params = {
                'limit': 1000,
                'status': 'open'
            }
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract markets from events data structure
            all_markets = []
            events = data.get('events', [])
            
            for event in events:
                markets = event.get('markets', [])
                for market in markets:
                    # Add event info to market
                    market['event_ticker'] = event.get('event_ticker', '')
                    market['event_title'] = event.get('title', '')
                    all_markets.extend([market])
            
            # Filter for temperature markets (HIGH, LOW, TEMP in ticker)
            temp_markets = []
            temp_keywords = ['HIGH', 'LOW', 'TEMP', 'KXHIGH', 'KXLOW']
            
            for market in all_markets:
                ticker = market.get('ticker', '').upper()
                event_ticker = market.get('event_ticker', '').upper()
                if any(keyword in ticker for keyword in temp_keywords) or any(keyword in event_ticker for keyword in temp_keywords):
                    temp_markets.append(market)
                    
            self.logger.info(f"📊 Found {len(temp_markets)} temperature markets out of {len(all_markets)} total")
            return temp_markets
            
        except Exception as e:
            self.logger.error(f"❌ Error fetching markets: {e}")
            return []
            
    def scrape_public_markets(self) -> List[Dict]:
        """Fallback: scrape public Kalshi market data"""
        try:
            self.logger.info("🕸️ Attempting to scrape public market data...")
            
            # Try to get market data from public pages
            url = "https://kalshi.com/markets"
            response = self.session.get(url)
            
            if response.status_code != 200:
                self.logger.error(f"❌ Failed to access public markets page: {response.status_code}")
                return []
                
            # For now, return empty list - would need more complex parsing
            self.logger.warning("⚠️ Web scraping not fully implemented - manual API access required")
            return []
            
        except Exception as e:
            self.logger.error(f"❌ Error scraping markets: {e}")
            return []
            
    def extract_market_data(self, market: Dict) -> Dict:
        """Extract relevant data from market object"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Extract basic market info
        data = {
            'timestamp': timestamp,
            'ticker': market.get('ticker', ''),
            'title': market.get('title', ''),
            'subtitle': market.get('subtitle', ''),
            'event_ticker': market.get('event_ticker', ''),
            'status': market.get('status', ''),
            'close_time': market.get('close_time', ''),
            'expiration_time': market.get('expiration_time', '')
        }
        
        # Extract pricing data
        data['last_price'] = market.get('last_price')
        data['yes_ask'] = market.get('yes_ask')
        data['yes_bid'] = market.get('yes_bid')
        data['no_ask'] = market.get('no_ask')
        data['no_bid'] = market.get('no_bid')
        
        # Extract volume and open interest
        data['volume'] = market.get('volume')
        data['volume_24h'] = market.get('volume_24h')
        data['open_interest'] = market.get('open_interest')
        
        # Extract market metrics
        data['liquidity'] = market.get('liquidity')
        data['dollar_volume_24h'] = market.get('dollar_volume_24h')
        
        # Extract settlement info if available
        data['result'] = market.get('result')
        data['settlement_value'] = market.get('settlement_value')
        
        return data
        
    def save_to_csv(self, market_data: List[Dict]):
        """Save market data to daily CSV file"""
        if not market_data:
            return
            
        # Create filename with current date
        today = datetime.now().strftime("%Y%m%d")
        filename = f"kalshi_temp_markets_{today}.csv"
        filepath = self.data_dir / filename
        
        # Convert to DataFrame
        df = pd.DataFrame(market_data)
        
        # Append to file if it exists, otherwise create new
        if filepath.exists():
            df.to_csv(filepath, mode='a', header=False, index=False)
        else:
            df.to_csv(filepath, index=False)
            self.logger.info(f"📁 Created new data file: {filename}")
            
        self.logger.info(f"💾 Saved {len(market_data)} market snapshots to {filename}")
        
    def run_monitoring_cycle(self):
        """Single monitoring cycle - fetch and save data"""
        self.logger.info("🔄 Starting monitoring cycle...")
        
        # Fetch temperature markets
        markets = self.get_temperature_markets()
        if not markets:
            self.logger.warning("⚠️ No temperature markets found")
            return
            
        # Extract data from each market
        market_data = []
        for market in markets:
            data = self.extract_market_data(market)
            market_data.append(data)
            
        # Save to CSV
        self.save_to_csv(market_data)
        
        # Log summary
        active_markets = len([m for m in markets if m.get('status') == 'open'])
        avg_price = sum([float(m.get('last_price', 0) or 0) for m in markets]) / len(markets) if markets else 0
        
        self.logger.info(f"📈 Cycle complete: {active_markets} active markets, avg price: ${avg_price:.2f}")
        
    def run(self, interval_seconds: int = 30):
        """Main monitoring loop"""
        self.logger.info(f"🚀 Starting Kalshi temperature monitoring (every {interval_seconds}s)")
        self.logger.info(f"📂 Data will be saved to: {self.data_dir.absolute()}")
        self.logger.info("🛑 Press Ctrl+C to stop")
        
        while self.running:
            try:
                start_time = time.time()
                
                # Run monitoring cycle
                self.run_monitoring_cycle()
                
                # Calculate sleep time
                cycle_time = time.time() - start_time
                sleep_time = max(0, interval_seconds - cycle_time)
                
                if sleep_time > 0:
                    self.logger.info(f"⏱️ Cycle took {cycle_time:.1f}s, sleeping {sleep_time:.1f}s...")
                    time.sleep(sleep_time)
                else:
                    self.logger.warning(f"⚠️ Cycle took {cycle_time:.1f}s (longer than {interval_seconds}s interval)")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"❌ Error in monitoring cycle: {e}")
                self.logger.info(f"😴 Sleeping {interval_seconds}s before retry...")
                time.sleep(interval_seconds)
                
        self.logger.info("🛑 Monitoring stopped")

def main():
    """Main entry point"""
    print("🌡️ Kalshi Temperature Market Monitor")
    print("=" * 50)
    
    monitor = KalshiTempMonitor()
    
    try:
        # Run with 30-second intervals
        monitor.run(interval_seconds=30)
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())