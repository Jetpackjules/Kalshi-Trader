#!/usr/bin/env python3
"""
Test Seasonal Arbitrage Strategy - July 2025
Uses REAL historical temperature data and market prices to validate the strategy.
"""

import pandas as pd
import numpy as np
import json
import sys
import os
from datetime import datetime, timedelta, date
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

try:
    from modules.nws_api import NWSAPI
    from modules.ncei_asos import NCEIASOS
    from modules.kalshi_nws_source import KalshiNWSSource
    logger.info("Successfully imported weather APIs")
except ImportError as e:
    logger.error(f"Failed to import weather APIs: {e}")
    sys.exit(1)

class SeasonalArbitrageValidator:
    def __init__(self):
        self.candlestick_data = None
        self.weather_apis = {
            'nws': NWSAPI(),
            'asos': NCEIASOS(),
            'kalshi_official': KalshiNWSSource()
        }
        self.july_results = []
        
    def load_market_data(self):
        """Load candlestick market data."""
        csv_paths = [
            "BACKLOG!/data/candles/KXHIGHNY_candles_5m.csv",  # Try BACKLOG first (has July data)
            "data/candles/KXHIGHNY_candles_5m.csv"
        ]
        
        for csv_path in csv_paths:
            if os.path.exists(csv_path):
                self.candlestick_data = pd.read_csv(csv_path)
                logger.info(f"Loaded data from: {csv_path}")
                break
                
        if self.candlestick_data is None:
            raise FileNotFoundError("No candlestick data found")
            
        # Process data
        self.candlestick_data['start'] = pd.to_datetime(self.candlestick_data['start'])
        
        # Extract contract info
        strike_temp_series = self.candlestick_data['ticker'].str.extract(r'[BT](\d+(?:\.\d+)?)', expand=False)
        self.candlestick_data['strike_temp'] = pd.to_numeric(strike_temp_series, errors='coerce')
        
        contract_type_series = self.candlestick_data['ticker'].str.extract(r'-([BT])', expand=False)
        self.candlestick_data['contract_type'] = contract_type_series
        
        logger.info(f"Loaded {len(self.candlestick_data)} market data records")
        return self.candlestick_data
        
    def parse_contract_date(self, ticker):
        """Parse contract date from ticker."""
        try:
            parts = ticker.split('-')
            date_str = parts[1]  # 25JUL19
            year = 2000 + int(date_str[:2])
            month_str = date_str[2:5]
            day = int(date_str[5:])
            
            month_map = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            
            return datetime(year, month_map[month_str], day).date()
        except Exception as e:
            logger.warning(f"Failed to parse date from {ticker}: {e}")
            return None

    def get_actual_temperature(self, target_date):
        """Get actual temperature from multiple APIs for validation."""
        logger.info(f"Getting actual temperature for {target_date}")
        
        temps = {}
        
        # Try each API
        for api_name, api_obj in self.weather_apis.items():
            try:
                logger.info(f"Trying {api_name} for {target_date}")
                result = api_obj.get_daily_max_temperature(target_date)
                
                if result and 'peak_temp' in result:
                    temps[api_name] = result['peak_temp']
                    logger.info(f"{api_name}: {result['peak_temp']}°F")
                else:
                    logger.warning(f"{api_name}: No temperature data")
                    
            except Exception as e:
                logger.error(f"Error getting {api_name} data for {target_date}: {e}")
        
        if temps:
            # Use official Kalshi source if available, otherwise average
            if 'kalshi_official' in temps:
                official_temp = temps['kalshi_official']
                logger.info(f"Using official Kalshi settlement: {official_temp}°F")
                return official_temp, temps
            else:
                avg_temp = np.mean(list(temps.values()))
                logger.info(f"Using average temperature: {avg_temp:.1f}°F")
                return avg_temp, temps
        
        logger.warning(f"No temperature data available for {target_date}")
        return None, {}

    def calculate_seasonal_expectation(self, contract_date, strike_temp, contract_type):
        """Calculate expected probability based on NYC July temperature patterns."""
        
        # July NYC temperature patterns (historical averages)
        # Based on 30+ years of Central Park data
        july_temp_stats = {
            'mean': 76.4,
            'std': 6.8,
            'p10': 67,  # 10th percentile
            'p25': 72,  # 25th percentile  
            'p75': 82,  # 75th percentile
            'p90': 86,  # 90th percentile
            'min_recorded': 58,
            'max_recorded': 106
        }
        
        # Only process July contracts for this test
        if contract_date.month != 7:
            return None
            
        # Calculate probability using historical distribution
        if contract_type == 'B':  # Below strike
            if strike_temp <= july_temp_stats['min_recorded']:
                prob = 0.01  # Almost impossible
            elif strike_temp >= july_temp_stats['max_recorded']:
                prob = 0.99  # Almost certain
            elif strike_temp <= july_temp_stats['p10']:
                prob = 0.10
            elif strike_temp <= july_temp_stats['p25']:
                prob = 0.25
            elif strike_temp <= july_temp_stats['mean']:
                prob = 0.50
            elif strike_temp <= july_temp_stats['p75']:
                prob = 0.75
            elif strike_temp <= july_temp_stats['p90']:
                prob = 0.90
            else:
                prob = 0.98
        else:  # Above strike (T contracts)
            if strike_temp <= july_temp_stats['min_recorded']:
                prob = 0.99  # Almost certain to be above
            elif strike_temp >= july_temp_stats['max_recorded']:
                prob = 0.01  # Almost impossible to be above
            elif strike_temp <= july_temp_stats['p10']:
                prob = 0.90
            elif strike_temp <= july_temp_stats['p25']:
                prob = 0.75
            elif strike_temp <= july_temp_stats['mean']:
                prob = 0.50
            elif strike_temp <= july_temp_stats['p75']:
                prob = 0.25
            elif strike_temp <= july_temp_stats['p90']:
                prob = 0.10
            else:
                prob = 0.02
                
        return prob

    def test_july_contracts(self):
        """Test seasonal arbitrage on all July 2025 contracts."""
        logger.info("=" * 80)
        logger.info("TESTING SEASONAL ARBITRAGE - JULY 2025")
        logger.info("=" * 80)
        
        # Filter for July contracts
        july_tickers = []
        for ticker in self.candlestick_data['ticker'].unique():
            contract_date = self.parse_contract_date(ticker)
            if contract_date and contract_date.month == 7 and contract_date.year == 2025:
                july_tickers.append(ticker)
        
        logger.info(f"Found {len(july_tickers)} July 2025 contracts")
        
        if not july_tickers:
            logger.error("No July contracts found!")
            return []
        
        results = []
        
        for ticker in july_tickers:
            logger.info(f"\n--- Analyzing {ticker} ---")
            
            # Get contract details
            ticker_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            ticker_data = ticker_data.sort_values('start')
            
            if len(ticker_data) == 0:
                continue
                
            contract_date = self.parse_contract_date(ticker)
            strike_temp = ticker_data['strike_temp'].iloc[0]
            contract_type = ticker_data['contract_type'].iloc[0]
            
            if pd.isna(strike_temp) or not contract_date:
                logger.warning(f"Invalid contract data for {ticker}")
                continue
                
            logger.info(f"Contract: {contract_date}, Strike: {strike_temp}°F, Type: {contract_type}")
            
            # Get seasonal expectation
            expected_prob = self.calculate_seasonal_expectation(contract_date, strike_temp, contract_type)
            if expected_prob is None:
                continue
                
            # Get first available market price (earliest trading opportunity)
            first_candle = ticker_data.iloc[0]
            market_price = first_candle['close']
            implied_prob = market_price / 100
            
            edge = expected_prob - implied_prob
            
            logger.info(f"Expected prob: {expected_prob:.1%}, Market prob: {implied_prob:.1%}, Edge: {edge:+.1%}")
            
            # Check if we would trade (need significant edge)
            min_edge = 0.15  # 15% minimum edge
            
            if abs(edge) >= min_edge:
                # Determine trade
                if edge > 0:
                    side = 'YES'
                    entry_price = market_price
                else:
                    side = 'NO'
                    entry_price = 100 - market_price
                
                logger.info(f"TRADE SIGNAL: Buy {side} at {entry_price:.1f}¢")
                
                # Get actual temperature outcome
                actual_temp, all_temps = self.get_actual_temperature(contract_date)
                
                if actual_temp is not None:
                    # Determine actual settlement
                    if contract_type == 'B':
                        settled_yes = actual_temp < strike_temp
                    else:
                        settled_yes = actual_temp >= strike_temp
                    
                    # Calculate P&L
                    if (side == 'YES' and settled_yes) or (side == 'NO' and not settled_yes):
                        pnl = 100 - entry_price
                        outcome = 'WIN'
                    else:
                        pnl = -entry_price
                        outcome = 'LOSS'
                    
                    logger.info(f"Actual temp: {actual_temp:.1f}°F, Settled: {'YES' if settled_yes else 'NO'}")
                    logger.info(f"Result: {outcome}, P&L: {pnl:+.1f}¢")
                    
                    results.append({
                        'ticker': ticker,
                        'contract_date': contract_date,
                        'strike_temp': strike_temp,
                        'contract_type': contract_type,
                        'expected_prob': expected_prob,
                        'market_price': market_price,
                        'implied_prob': implied_prob,
                        'edge': edge,
                        'side': side,
                        'entry_price': entry_price,
                        'actual_temp': actual_temp,
                        'settled_yes': settled_yes,
                        'outcome': outcome,
                        'pnl': pnl,
                        'all_temps': all_temps
                    })
                else:
                    logger.warning(f"Could not get actual temperature for {contract_date}")
            else:
                logger.info(f"No trade - edge too small: {edge:+.1%}")
        
        return results

    def analyze_results(self, results):
        """Analyze the trading results."""
        if not results:
            logger.error("No results to analyze!")
            return
            
        logger.info("\n" + "=" * 80)
        logger.info("SEASONAL ARBITRAGE RESULTS ANALYSIS")
        logger.info("=" * 80)
        
        df = pd.DataFrame(results)
        
        # Basic stats
        total_trades = len(results)
        wins = len([r for r in results if r['pnl'] > 0])
        losses = len([r for r in results if r['pnl'] < 0])
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        total_invested = sum(r['entry_price'] for r in results)
        total_pnl = sum(r['pnl'] for r in results)
        roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0
        
        logger.info(f"Total Trades: {total_trades}")
        logger.info(f"Wins: {wins}, Losses: {losses}")
        logger.info(f"Win Rate: {win_rate:.1%}")
        logger.info(f"Total Invested: {total_invested:.0f}¢")
        logger.info(f"Total P&L: {total_pnl:+.0f}¢")
        logger.info(f"ROI: {roi:+.1f}%")
        
        if total_trades > 0:
            avg_edge = np.mean([r['edge'] for r in results])
            avg_pnl = total_pnl / total_trades
            logger.info(f"Average Edge: {avg_edge:+.1%}")
            logger.info(f"Average P&L per trade: {avg_pnl:+.1f}¢")
        
        # Detailed trade breakdown
        logger.info(f"\n--- TRADE DETAILS ---")
        for i, trade in enumerate(results, 1):
            logger.info(f"{i:2d}. {trade['ticker']}")
            logger.info(f"    Strike: {trade['strike_temp']:.1f}°F ({trade['contract_type']}), "
                       f"Actual: {trade['actual_temp']:.1f}°F")
            logger.info(f"    Edge: {trade['edge']:+.1%}, Side: {trade['side']}, "
                       f"P&L: {trade['pnl']:+.1f}¢ ({trade['outcome']})")
        
        # Save detailed results
        output_file = f"seasonal_arbitrage_july_test_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(output_file, 'w') as f:
            # Convert dates to strings for JSON serialization
            serializable_results = []
            for result in results:
                serializable_result = result.copy()
                serializable_result['contract_date'] = str(result['contract_date'])
                serializable_results.append(serializable_result)
            
            json.dump({
                'summary': {
                    'total_trades': total_trades,
                    'wins': wins,
                    'losses': losses,
                    'win_rate': win_rate,
                    'total_invested': total_invested,
                    'total_pnl': total_pnl,
                    'roi_percent': roi,
                    'avg_edge': avg_edge if total_trades > 0 else 0
                },
                'trades': serializable_results
            }, f, indent=2)
        
        logger.info(f"\nDetailed results saved to: {output_file}")
        
        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'roi_percent': roi,
            'total_pnl': total_pnl
        }

    def run_test(self):
        """Run the complete seasonal arbitrage test."""
        try:
            # Load market data
            self.load_market_data()
            
            # Test July contracts
            results = self.test_july_contracts()
            
            # Analyze results
            summary = self.analyze_results(results)
            
            return summary
            
        except Exception as e:
            logger.error(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
            return None

def main():
    """Main execution function."""
    logger.info("Starting Seasonal Arbitrage July 2025 Test")
    
    validator = SeasonalArbitrageValidator()
    summary = validator.run_test()
    
    if summary:
        logger.info("\n" + "=" * 50)
        logger.info("FINAL SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Trades: {summary['total_trades']}")
        logger.info(f"Win Rate: {summary['win_rate']:.1%}")
        logger.info(f"ROI: {summary['roi_percent']:+.1f}%")
        logger.info(f"Total P&L: {summary['total_pnl']:+.1f}¢")
        
        if summary['roi_percent'] > 10:
            logger.info("✅ STRATEGY SHOWS PROMISE - Consider live testing")
        elif summary['roi_percent'] > 0:
            logger.info("⚠️  MARGINAL PERFORMANCE - Refine parameters")
        else:
            logger.info("❌ STRATEGY UNDERPERFORMED - Major changes needed")
    else:
        logger.error("Test failed - check logs for errors")

if __name__ == "__main__":
    main()