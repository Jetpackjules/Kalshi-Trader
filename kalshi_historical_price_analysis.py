#!/usr/bin/env python3
"""
Kalshi Historical Price Analysis

Gets historical candlestick data for temperature markets before they closed
and compares pre-close prices to actual outcomes.

This answers: "What were market prices X hours before close, and how accurate were they?"
"""

import pandas as pd
import requests
import json
from datetime import datetime, timedelta, timezone
import time
from typing import Dict, List, Optional
import logging
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import base64
import os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KalshiHistoricalAnalyzer:
    def __init__(self, api_base: str = "https://api.elections.kalshi.com/trade-api/v2"):
        self.api_base = api_base
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'kalshi-historical-analyzer/1.0',
            'Accept': 'application/json'
        })
        
        # Set up authentication
        self.api_key = os.getenv('KALSHI_API_KEY', '8adbb05c-01ca-42cf-af00-f05e551f0c25')
        self.private_key_file = os.getenv('KALSHI_PRIVATE_KEY_FILE', '/home/jetpackjules/kalshi-wsl/kalshi_private_key.pem')
        self.private_key = self.load_private_key()
        
        logger.info("🕰️ Kalshi Historical Price Analyzer initialized")
        
    def load_private_key(self):
        """Load private key from file"""
        try:
            with open(self.private_key_file, 'r') as f:
                private_key_pem = f.read()
            return serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        except Exception as e:
            logger.error(f"❌ Error loading private key: {e}")
            return None
            
    def generate_auth_headers(self, method: str, path: str) -> Dict[str, str]:
        """Generate authentication headers for Kalshi API"""
        if not self.private_key:
            return {}
            
        timestamp = str(int(time.time() * 1000))
        message = timestamp + method.upper() + path
        
        try:
            signature = self.private_key.sign(
                message.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            signature_b64 = base64.b64encode(signature).decode()
            
            return {
                'KALSHI-ACCESS-KEY': self.api_key,
                'KALSHI-ACCESS-TIMESTAMP': timestamp,
                'KALSHI-ACCESS-SIGNATURE': signature_b64
            }
        except Exception as e:
            logger.error(f"❌ Error generating auth headers: {e}")
            return {}
        
    def get_market_candlesticks(self, series_ticker: str, ticker: str, start_ts: int, end_ts: int, 
                               period_interval: int = 60) -> List[Dict]:
        """Get historical candlestick data for a market"""
        try:
            path = f"/series/{series_ticker}/markets/{ticker}/candlesticks"
            url = f"{self.api_base}{path}"
            params = {
                'start_ts': start_ts,
                'end_ts': end_ts,
                'period_interval': period_interval  # 1=1min, 60=1hr, 1440=1day
            }
            
            # Add authentication headers
            auth_headers = self.generate_auth_headers("GET", path)
            headers = {**self.session.headers, **auth_headers}
            
            response = self.session.get(url, params=params, headers=headers)
            
            if response.status_code == 401:
                logger.warning("🔐 API requires authentication for candlestick data")
                return []
            elif response.status_code == 404:
                logger.warning(f"❌ Market {ticker} not found or no candlestick data available")
                return []
                
            response.raise_for_status()
            data = response.json()
            
            candlesticks = data.get('candlesticks', [])
            logger.info(f"📊 Retrieved {len(candlesticks)} candlesticks for {ticker}")
            return candlesticks
            
        except Exception as e:
            logger.error(f"❌ Error getting candlesticks for {ticker}: {e}")
            return []
            
    def analyze_market_timing(self, market_data: Dict, hours_before_close: List[int] = [1, 2, 4, 8, 12, 24]) -> Dict:
        """Analyze market prices at different times before close"""
        
        ticker = market_data.get('market_ticker', market_data.get('ticker', ''))
        series_ticker = market_data.get('event_ticker', ticker.split('-')[0] if ticker else '')
        close_time_str = market_data.get('close_time', '')
        
        if not close_time_str:
            logger.warning(f"⚠️ No close time for {ticker}")
            return {}
            
        try:
            # Parse close time
            close_time = datetime.fromisoformat(close_time_str.replace('Z', '+00:00'))
            
            results = {
                'ticker': ticker,
                'series_ticker': series_ticker,
                'close_time': close_time_str,
                'final_result': market_data.get('result', 'unknown'),
                'settlement_value': market_data.get('settlement_value'),
                'subtitle': market_data.get('subtitle', ''),
                'prices_before_close': {}
            }
            
            # Get prices at different times before close
            for hours in hours_before_close:
                snapshot_time = close_time - timedelta(hours=hours)
                start_ts = int(snapshot_time.timestamp())
                end_ts = int((snapshot_time + timedelta(minutes=30)).timestamp())  # 30min window
                
                candlesticks = self.get_market_candlesticks(series_ticker, ticker, start_ts, end_ts, period_interval=60)
                
                if candlesticks:
                    # Get the last available price in the window
                    last_candle = candlesticks[-1]
                    price = last_candle.get('close') or last_candle.get('open')
                    
                    if price is not None:
                        results['prices_before_close'][f'{hours}h_before'] = {
                            'price': price,
                            'timestamp': last_candle.get('ts'),
                            'volume': last_candle.get('volume', 0)
                        }
                        
                        logger.info(f"📈 {ticker}: {hours}h before close = ${price:.2f}")
                    else:
                        logger.warning(f"⚠️ No valid price in candlestick for {ticker} {hours}h before close")
                else:
                    logger.warning(f"⚠️ No price data {hours}h before close for {ticker}")
                    
            return results
            
        except Exception as e:
            logger.error(f"❌ Error analyzing {ticker}: {e}")
            return {}
            
    def load_historical_markets(self, csv_path: str = "kxhighny_markets_history.csv") -> pd.DataFrame:
        """Load historical market data from CSV"""
        try:
            df = pd.read_csv(csv_path)
            logger.info(f"📁 Loaded {len(df)} historical markets from {csv_path}")
            
            # Filter for settled markets with results
            settled_df = df[
                (df['status'] == 'finalized') & 
                (df['result'].notna()) &
                (df['close_time'].notna())
            ].copy()
            
            logger.info(f"🎯 Found {len(settled_df)} settled markets for analysis")
            return settled_df
            
        except Exception as e:
            logger.error(f"❌ Error loading market data: {e}")
            return pd.DataFrame()
            
    def run_historical_analysis(self, max_markets: int = 20):
        """Run full historical price analysis"""
        logger.info("🚀 Starting historical price analysis...")
        
        # Load market data
        markets_df = self.load_historical_markets()
        if markets_df.empty:
            logger.error("❌ No market data loaded")
            return
            
        # Sample recent markets for analysis
        recent_markets = markets_df.sort_values('close_time', ascending=False).head(max_markets)
        
        results = []
        for idx, market in recent_markets.iterrows():
            ticker = market.get('market_ticker', market.get('ticker', 'unknown'))
            logger.info(f"🔍 Analyzing {ticker} ({idx+1}/{len(recent_markets)})")
            
            market_analysis = self.analyze_market_timing(market.to_dict())
            if market_analysis:
                results.append(market_analysis)
                
            # Rate limiting
            time.sleep(0.5)
            
        # Save results
        self.save_analysis_results(results)
        self.create_visualizations(results)
        
        logger.info(f"✅ Analysis complete! Processed {len(results)} markets")
        
    def save_analysis_results(self, results: List[Dict]):
        """Save analysis results to CSV"""
        if not results:
            return
            
        # Flatten results for CSV
        flattened = []
        for result in results:
            base_data = {
                'ticker': result['ticker'],
                'close_time': result['close_time'],
                'final_result': result['final_result'],
                'settlement_value': result['settlement_value'],
                'subtitle': result['subtitle']
            }
            
            for time_key, price_data in result['prices_before_close'].items():
                row = base_data.copy()
                row['hours_before'] = time_key
                row['price'] = price_data['price']
                row['timestamp'] = price_data['timestamp']
                row['volume'] = price_data['volume']
                flattened.append(row)
                
        df = pd.DataFrame(flattened)
        filename = f"kalshi_historical_prices_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        df.to_csv(filename, index=False)
        
        logger.info(f"💾 Saved results to {filename}")
        
    def create_visualizations(self, results: List[Dict]):
        """Create visualizations of price evolution"""
        if not results:
            return
            
        # Create price evolution plots
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Kalshi Market Price Evolution Before Close', fontsize=16, fontweight='bold')
        
        # Prepare data
        plot_data = []
        for result in results:
            for time_key, price_data in result['prices_before_close'].items():
                hours = int(time_key.split('h')[0])
                plot_data.append({
                    'ticker': result['ticker'],
                    'hours_before': hours,
                    'price': price_data['price'],
                    'final_result': result['final_result'],
                    'subtitle': result['subtitle']
                })
                
        if not plot_data:
            logger.warning("⚠️ No price data for visualizations")
            return
            
        plot_df = pd.DataFrame(plot_data)
        
        # Plot 1: Price vs Hours Before Close
        ax1 = axes[0, 0]
        for ticker in plot_df['ticker'].unique()[:5]:  # Limit to 5 markets for clarity
            market_data = plot_df[plot_df['ticker'] == ticker]
            ax1.plot(market_data['hours_before'], market_data['price'], 
                    marker='o', label=ticker, alpha=0.7)
        ax1.set_xlabel('Hours Before Close')
        ax1.set_ylabel('Market Price ($)')
        ax1.set_title('Price Evolution by Market')
        ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Average Price by Hours Before
        ax2 = axes[0, 1]
        avg_prices = plot_df.groupby('hours_before')['price'].agg(['mean', 'std']).reset_index()
        ax2.errorbar(avg_prices['hours_before'], avg_prices['mean'], 
                    yerr=avg_prices['std'], marker='o', capsize=5)
        ax2.set_xlabel('Hours Before Close')
        ax2.set_ylabel('Average Market Price ($)')
        ax2.set_title('Average Price Evolution')
        ax2.grid(True, alpha=0.3)
        
        # Plot 3: Price Distribution by Result
        ax3 = axes[1, 0]
        for result in ['yes', 'no']:
            result_data = plot_df[plot_df['final_result'] == result]
            if not result_data.empty:
                ax3.hist(result_data['price'], alpha=0.6, label=f'Result: {result}', bins=20)
        ax3.set_xlabel('Market Price ($)')
        ax3.set_ylabel('Frequency')
        ax3.set_title('Price Distribution by Final Result')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # Plot 4: Accuracy Analysis
        ax4 = axes[1, 1]
        # Calculate prediction accuracy at different times
        accuracy_data = []
        for hours in sorted(plot_df['hours_before'].unique()):
            hour_data = plot_df[plot_df['hours_before'] == hours]
            if not hour_data.empty:
                # Simple accuracy: price > 0.5 predicts 'yes'
                predictions = (hour_data['price'] > 0.5).astype(str).replace({True: 'yes', False: 'no'})
                accuracy = (predictions == hour_data['final_result']).mean()
                accuracy_data.append({'hours_before': hours, 'accuracy': accuracy})
                
        if accuracy_data:
            acc_df = pd.DataFrame(accuracy_data)
            ax4.plot(acc_df['hours_before'], acc_df['accuracy'], marker='o', linewidth=2)
            ax4.set_xlabel('Hours Before Close')
            ax4.set_ylabel('Prediction Accuracy')
            ax4.set_title('Market Prediction Accuracy Over Time')
            ax4.set_ylim(0, 1)
            ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        filename = f"kalshi_price_evolution_{datetime.now().strftime('%Y%m%d_%H%M')}.png"
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.show()
        
        logger.info(f"📊 Saved visualization to {filename}")

def main():
    """Main entry point"""
    print("🕰️ Kalshi Historical Price Analysis")
    print("=" * 50)
    
    analyzer = KalshiHistoricalAnalyzer()
    
    try:
        # Run analysis on recent markets
        analyzer.run_historical_analysis(max_markets=10)
        
    except KeyboardInterrupt:
        print("\n🛑 Analysis stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()