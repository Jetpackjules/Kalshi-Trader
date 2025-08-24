#!/usr/bin/env python3
"""
Comprehensive Kalshi Temperature Market Strategy Backtester
Analyzes multiple trading strategies using historical data.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import glob
from pathlib import Path
import sys
import os

# Add modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

# Import weather APIs
try:
    from modules.synoptic_api import SynopticAPI
    from modules.ncei_asos import NCEIASOS  
    from modules.nws_api import NWSAPI
except ImportError:
    # Fallback - create dummy classes for now
    class SynopticAPI:
        def get_daily_max_temperature(self, date):
            return None
    class NCEIASOS:
        def get_daily_max_temperature(self, date):
            return None
    class NWSAPI:
        def get_daily_max_temperature(self, date):
            return None

class StrategyBacktester:
    def __init__(self):
        self.candlestick_data = None
        self.weather_apis = {
            'synoptic': SynopticAPI(),
            'asos': NCEIASOS(),
            'nws': NWSAPI()
        }
        self.results = {}
        
    def load_candlestick_data(self):
        """Load historical market price data."""
        csv_path = "data/candles/KXHIGHNY_candles_5m.csv"
        if not os.path.exists(csv_path):
            # Try backup location
            csv_path = "BACKLOG!/data/candles/KXHIGHNY_candles_5m.csv"
        
        self.candlestick_data = pd.read_csv(csv_path)
        self.candlestick_data['start'] = pd.to_datetime(self.candlestick_data['start'])
        self.candlestick_data['date'] = self.candlestick_data['start'].dt.date
        
        # Extract contract info
        self.candlestick_data['contract_date'] = self.candlestick_data['ticker'].str.extract(r'25([A-Z]{3}\d{2})')
        self.candlestick_data['strike_temp'] = self.candlestick_data['ticker'].str.extract(r'[BT](\d+(?:\.\d+)?)')
        self.candlestick_data['contract_type'] = self.candlestick_data['ticker'].str.extract(r'25[A-Z]{3}\d{2}-([BT])')
        
        print(f"Loaded {len(self.candlestick_data)} candlestick records")
        return self.candlestick_data
        
    def get_weather_data(self, target_date):
        """Get weather data for a specific date from multiple APIs."""
        weather_data = {}
        
        try:
            # Try each weather API
            for api_name, api_obj in self.weather_apis.items():
                try:
                    result = api_obj.get_daily_max_temperature(target_date)
                    if result and 'peak_temp' in result:
                        weather_data[api_name] = result['peak_temp']
                except Exception as e:
                    print(f"Error getting {api_name} data for {target_date}: {e}")
                    
        except Exception as e:
            print(f"General error getting weather data for {target_date}: {e}")
            
        return weather_data
        
    def parse_contract_date(self, contract_string):
        """Parse contract date from ticker (e.g., 25AUG19 -> 2025-08-19)."""
        try:
            # Extract date part
            date_part = contract_string.split('-')[1]  # 25AUG19
            year = 2000 + int(date_part[:2])  # 2025
            month_str = date_part[2:5]  # AUG
            day = int(date_part[5:])  # 19
            
            month_map = {
                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
            }
            
            return datetime(year, month_map[month_str], day).date()
        except Exception as e:
            print(f"Error parsing date from {contract_string}: {e}")
            return None
            
    def strategy_cheap_no_orders(self, max_price_cents=2):
        """
        Strategy 1: Buy cheap NO positions at market prices ≤ max_price_cents
        This is the current no_strategy_bot approach.
        """
        print(f"Testing Strategy 1: Cheap NO orders (≤{max_price_cents} cents)")
        
        trades = []
        total_invested = 0
        total_pnl = 0
        
        # Group by contract/ticker
        for ticker in self.candlestick_data['ticker'].unique():
            contract_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            contract_data = contract_data.sort_values('start')
            
            # Parse contract details
            contract_date = self.parse_contract_date(ticker)
            if not contract_date:
                continue
                
            strike_temp = float(contract_data['strike_temp'].iloc[0])
            contract_type = contract_data['contract_type'].iloc[0]  # B or T
            
            # Get actual temperature on settlement date
            weather_data = self.get_weather_data(contract_date)
            if not weather_data:
                continue
                
            actual_temp = np.mean(list(weather_data.values()))  # Average across APIs
            
            # Find trading opportunities (cheap NO positions)
            for _, candle in contract_data.iterrows():
                # Convert to "NO" side pricing (market prices are typically "YES")
                # For YES price P, NO price is approximately (100 - P)
                no_ask_price = 100 - candle['close']
                
                if no_ask_price <= max_price_cents:
                    # Execute trade
                    investment = max_price_cents  # Risk max_price_cents per trade
                    
                    # Determine settlement
                    if contract_type == 'B':  # Below strike
                        settled_yes = actual_temp < strike_temp
                    else:  # Above strike  
                        settled_yes = actual_temp >= strike_temp
                        
                    # NO position wins if market settles NO
                    pnl = (100 - max_price_cents) if not settled_yes else -max_price_cents
                    
                    trades.append({
                        'ticker': ticker,
                        'contract_date': contract_date,
                        'strike_temp': strike_temp,
                        'contract_type': contract_type,
                        'actual_temp': actual_temp,
                        'trade_time': candle['start'],
                        'no_price': no_ask_price,
                        'investment': investment,
                        'settled_yes': settled_yes,
                        'pnl': pnl
                    })
                    
                    total_invested += investment
                    total_pnl += pnl
                    
                    break  # Only one trade per contract
                    
        return {
            'strategy': 'Cheap NO Orders',
            'params': {'max_price_cents': max_price_cents},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': sum(1 for t in trades if t['pnl'] > 0) / len(trades) if trades else 0,
            'trades': trades
        }
        
    def strategy_weather_momentum(self, temp_drop_threshold=5):
        """
        Strategy 2: Weather API momentum signals
        Buy NO on HIGH contracts when APIs show temp dropping significantly.
        """
        print(f"Testing Strategy 2: Weather momentum (temp drop ≥{temp_drop_threshold}°F)")
        
        trades = []
        total_invested = 0
        total_pnl = 0
        
        # Get unique contract dates
        tickers_by_date = {}
        for ticker in self.candlestick_data['ticker'].unique():
            contract_date = self.parse_contract_date(ticker)
            if contract_date:
                if contract_date not in tickers_by_date:
                    tickers_by_date[contract_date] = []
                tickers_by_date[contract_date].append(ticker)
        
        for contract_date, tickers in tickers_by_date.items():
            # Get weather data 1-2 days before contract date
            prev_date = contract_date - timedelta(days=1)
            prev2_date = contract_date - timedelta(days=2)
            
            weather_today = self.get_weather_data(contract_date)
            weather_prev = self.get_weather_data(prev_date)  
            weather_prev2 = self.get_weather_data(prev2_date)
            
            if not (weather_today and weather_prev and weather_prev2):
                continue
                
            # Calculate temperature trend
            temp_today = np.mean(list(weather_today.values()))
            temp_prev = np.mean(list(weather_prev.values()))
            temp_prev2 = np.mean(list(weather_prev2.values()))
            
            temp_drop = temp_prev2 - temp_today  # Drop over 2 days
            
            if temp_drop >= temp_drop_threshold:
                # Look for HIGH contracts to buy NO on
                high_tickers = [t for t in tickers if '-T' in t]  # T = above strike
                
                for ticker in high_tickers:
                    contract_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
                    contract_data = contract_data.sort_values('start')
                    
                    if len(contract_data) == 0:
                        continue
                        
                    strike_temp = float(contract_data['strike_temp'].iloc[0])
                    
                    # Use mid-market pricing on first available candle
                    first_candle = contract_data.iloc[0]
                    mid_price = (first_candle['high'] + first_candle['low']) / 2
                    no_price = 100 - mid_price
                    
                    investment = 50  # Fixed bet size for weather signals
                    
                    # Settlement
                    settled_yes = temp_today >= strike_temp
                    pnl = (100 - no_price) if not settled_yes else -investment
                    
                    trades.append({
                        'ticker': ticker,
                        'contract_date': contract_date,
                        'strike_temp': strike_temp,
                        'actual_temp': temp_today,
                        'temp_drop': temp_drop,
                        'trade_price': no_price,
                        'investment': investment,
                        'settled_yes': settled_yes,
                        'pnl': pnl
                    })
                    
                    total_invested += investment
                    total_pnl += pnl
                    
        return {
            'strategy': 'Weather Momentum',
            'params': {'temp_drop_threshold': temp_drop_threshold},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': sum(1 for t in trades if t['pnl'] > 0) / len(trades) if trades else 0,
            'trades': trades
        }
        
    def strategy_mean_reversion(self, price_threshold=15):
        """
        Strategy 3: Mean reversion on mispriced contracts
        Buy when market price is significantly off from fair value based on weather APIs.
        """
        print(f"Testing Strategy 3: Mean reversion (price threshold {price_threshold} cents)")
        
        trades = []
        total_invested = 0
        total_pnl = 0
        
        for ticker in self.candlestick_data['ticker'].unique():
            contract_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            contract_data = contract_data.sort_values('start')
            
            if len(contract_data) == 0:
                continue
                
            contract_date = self.parse_contract_date(ticker)
            if not contract_date:
                continue
                
            strike_temp = float(contract_data['strike_temp'].iloc[0])
            contract_type = contract_data['contract_type'].iloc[0]
            
            # Get actual settlement temperature
            weather_data = self.get_weather_data(contract_date)
            if not weather_data:
                continue
                
            actual_temp = np.mean(list(weather_data.values()))
            
            # Calculate "fair value" based on actual outcome
            if contract_type == 'B':
                should_settle_yes = actual_temp < strike_temp
            else:
                should_settle_yes = actual_temp >= strike_temp
                
            fair_value = 80 if should_settle_yes else 20  # Rough fair value estimate
            
            # Look for mispricing in early candles
            early_candles = contract_data.head(5)  # First 5 trading periods
            
            for _, candle in early_candles.iterrows():
                market_price = candle['close']
                price_diff = abs(market_price - fair_value)
                
                if price_diff >= price_threshold:
                    # Determine trade direction
                    if market_price < fair_value:
                        # Market underpricing YES, buy YES
                        side = 'YES'
                        entry_price = market_price
                    else:
                        # Market overpricing YES, buy NO  
                        side = 'NO'
                        entry_price = 100 - market_price
                        
                    investment = 30  # Fixed position size
                    
                    # Calculate PnL
                    if (side == 'YES' and should_settle_yes) or (side == 'NO' and not should_settle_yes):
                        pnl = 100 - entry_price
                    else:
                        pnl = -investment
                        
                    trades.append({
                        'ticker': ticker,
                        'contract_date': contract_date,
                        'strike_temp': strike_temp,
                        'actual_temp': actual_temp,
                        'contract_type': contract_type,
                        'trade_time': candle['start'],
                        'side': side,
                        'entry_price': entry_price,
                        'fair_value': fair_value,
                        'price_diff': price_diff,
                        'investment': investment,
                        'settled_yes': should_settle_yes,
                        'pnl': pnl
                    })
                    
                    total_invested += investment
                    total_pnl += pnl
                    break  # One trade per contract
                    
        return {
            'strategy': 'Mean Reversion',
            'params': {'price_threshold': price_threshold},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': sum(1 for t in trades if t['pnl'] > 0) / len(trades) if trades else 0,
            'trades': trades
        }
        
    def strategy_portfolio_kelly(self, confidence_threshold=0.7):
        """
        Strategy 4: Kelly Criterion portfolio betting
        Size bets based on weather API confidence and expected value.
        """
        print(f"Testing Strategy 4: Kelly criterion (confidence ≥{confidence_threshold})")
        
        trades = []
        total_invested = 0
        total_pnl = 0
        bankroll = 1000  # Starting bankroll
        
        for ticker in self.candlestick_data['ticker'].unique()[:50]:  # Limit for performance
            contract_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            contract_data = contract_data.sort_values('start')
            
            if len(contract_data) == 0:
                continue
                
            contract_date = self.parse_contract_date(ticker)
            if not contract_date:
                continue
                
            strike_temp = float(contract_data['strike_temp'].iloc[0])
            contract_type = contract_data['contract_type'].iloc[0]
            
            # Get weather data from multiple APIs
            weather_data = self.get_weather_data(contract_date)
            if len(weather_data) < 2:  # Need multiple sources
                continue
                
            temps = list(weather_data.values())
            avg_temp = np.mean(temps)
            temp_std = np.std(temps) if len(temps) > 1 else 5.0
            
            # Calculate confidence based on API agreement
            confidence = 1 - (temp_std / 10.0)  # Higher std = lower confidence
            confidence = max(0.1, min(0.9, confidence))
            
            if confidence < confidence_threshold:
                continue
                
            # Determine expected settlement
            if contract_type == 'B':
                prob_yes = 1 - (1 / (1 + np.exp(-(strike_temp - avg_temp))))  # Logistic
            else:
                prob_yes = 1 / (1 + np.exp(-(avg_temp - strike_temp)))
                
            # Use first available market price
            first_candle = contract_data.iloc[0]
            market_price = first_candle['close']
            
            # Calculate Kelly fraction
            implied_prob = market_price / 100
            edge = prob_yes - implied_prob
            
            if edge > 0.05:  # Significant edge
                kelly_fraction = edge / (1 - implied_prob)
                bet_size = min(bankroll * kelly_fraction * 0.5, 100)  # Half-Kelly, max $100
                
                if bet_size >= 5:  # Minimum bet size
                    # Settlement
                    actual_temp = avg_temp  # Using our estimate
                    if contract_type == 'B':
                        settled_yes = actual_temp < strike_temp
                    else:
                        settled_yes = actual_temp >= strike_temp
                        
                    # PnL calculation
                    if settled_yes:
                        pnl = bet_size * ((100 - market_price) / market_price)
                    else:
                        pnl = -bet_size
                        
                    trades.append({
                        'ticker': ticker,
                        'contract_date': contract_date,
                        'strike_temp': strike_temp,
                        'avg_temp': avg_temp,
                        'confidence': confidence,
                        'prob_yes': prob_yes,
                        'market_price': market_price,
                        'edge': edge,
                        'kelly_fraction': kelly_fraction,
                        'bet_size': bet_size,
                        'settled_yes': settled_yes,
                        'pnl': pnl
                    })
                    
                    total_invested += bet_size
                    total_pnl += pnl
                    bankroll += pnl  # Update bankroll
                    
        return {
            'strategy': 'Kelly Criterion',
            'params': {'confidence_threshold': confidence_threshold},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': sum(1 for t in trades if t['pnl'] > 0) / len(trades) if trades else 0,
            'final_bankroll': bankroll,
            'trades': trades
        }
        
    def run_all_strategies(self):
        """Run all strategies and compare results."""
        print("=" * 80)
        print("KALSHI TEMPERATURE MARKET STRATEGY BACKTESTER")
        print("=" * 80)
        
        # Load data
        self.load_candlestick_data()
        
        strategies = [
            # Test cheap NO orders at different price thresholds
            lambda: self.strategy_cheap_no_orders(max_price_cents=2),
            lambda: self.strategy_cheap_no_orders(max_price_cents=5),
            lambda: self.strategy_cheap_no_orders(max_price_cents=10),
            
            # Test weather momentum with different thresholds
            lambda: self.strategy_weather_momentum(temp_drop_threshold=3),
            lambda: self.strategy_weather_momentum(temp_drop_threshold=5),
            lambda: self.strategy_weather_momentum(temp_drop_threshold=8),
            
            # Test mean reversion
            lambda: self.strategy_mean_reversion(price_threshold=10),
            lambda: self.strategy_mean_reversion(price_threshold=15),
            lambda: self.strategy_mean_reversion(price_threshold=20),
            
            # Test Kelly criterion
            lambda: self.strategy_portfolio_kelly(confidence_threshold=0.6),
            lambda: self.strategy_portfolio_kelly(confidence_threshold=0.7),
        ]
        
        results = []
        for i, strategy_func in enumerate(strategies, 1):
            print(f"\n[{i}/{len(strategies)}] Running strategy...")
            try:
                result = strategy_func()
                results.append(result)
                
                print(f"Strategy: {result['strategy']}")
                print(f"Params: {result['params']}")
                print(f"Total Trades: {result['total_trades']}")
                print(f"Total Invested: ${result['total_invested']:.2f}")
                print(f"Total PnL: ${result['total_pnl']:.2f}")
                print(f"ROI: {result['roi_percent']:.1f}%")
                print(f"Win Rate: {result['win_rate']:.1%}")
                if 'final_bankroll' in result:
                    print(f"Final Bankroll: ${result['final_bankroll']:.2f}")
                    
            except Exception as e:
                print(f"Error running strategy {i}: {e}")
                
        # Sort by ROI
        results.sort(key=lambda x: x['roi_percent'], reverse=True)
        
        print("\n" + "=" * 80)
        print("STRATEGY PERFORMANCE RANKING")
        print("=" * 80)
        
        for i, result in enumerate(results, 1):
            print(f"{i:2d}. {result['strategy']} {result['params']}")
            print(f"     ROI: {result['roi_percent']:8.1f}% | Win Rate: {result['win_rate']:5.1%} | "
                  f"Trades: {result['total_trades']:3d} | PnL: ${result['total_pnl']:8.2f}")
                  
        return results

def main():
    """Main execution function."""
    backtester = StrategyBacktester()
    results = backtester.run_all_strategies()
    
    # Save results to JSON for further analysis
    output_file = f"kalshi_strategy_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    
    # Make results JSON serializable
    serializable_results = []
    for result in results:
        serializable_result = result.copy()
        # Convert dates to strings in trades
        if 'trades' in serializable_result:
            for trade in serializable_result['trades']:
                for key, value in trade.items():
                    if isinstance(value, (datetime, pd.Timestamp)):
                        trade[key] = str(value)
                    elif hasattr(value, 'date') and callable(value.date):
                        trade[key] = str(value.date())
        serializable_results.append(serializable_result)
        
    with open(output_file, 'w') as f:
        json.dump(serializable_results, f, indent=2, default=str)
        
    print(f"\nResults saved to: {output_file}")
    
    return results

if __name__ == "__main__":
    main()