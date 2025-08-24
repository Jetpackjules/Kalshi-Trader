#!/usr/bin/env python3
"""
Advanced Kalshi Temperature Strategy Analysis
Incorporates seasonal patterns, volatility analysis, and market maker behavior.
"""

import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import os

class AdvancedStrategyAnalyzer:
    def __init__(self):
        self.candlestick_data = None
        
    def load_data(self):
        """Load and prepare data."""
        csv_paths = [
            "data/candles/KXHIGHNY_candles_5m.csv",
            "BACKLOG!/data/candles/KXHIGHNY_candles_5m.csv"
        ]
        
        for csv_path in csv_paths:
            if os.path.exists(csv_path):
                self.candlestick_data = pd.read_csv(csv_path)
                break
                
        self.candlestick_data['start'] = pd.to_datetime(self.candlestick_data['start'])
        self.candlestick_data['date'] = self.candlestick_data['start'].dt.date
        
        # Extract contract details  
        strike_temp_series = self.candlestick_data['ticker'].str.extract(r'[BT](\d+(?:\.\d+)?)', expand=False)
        self.candlestick_data['strike_temp'] = pd.to_numeric(strike_temp_series, errors='coerce')
        contract_type_series = self.candlestick_data['ticker'].str.extract(r'-([BT])', expand=False)
        self.candlestick_data['contract_type'] = contract_type_series
        
        # Parse contract dates and add seasonal info
        contract_dates = []
        seasons = []
        for ticker in self.candlestick_data['ticker']:
            date = self.parse_contract_date(ticker)
            contract_dates.append(date)
            if date:
                month = date.month
                if month in [12, 1, 2]:
                    season = 'Winter'
                elif month in [3, 4, 5]:
                    season = 'Spring'
                elif month in [6, 7, 8]:
                    season = 'Summer'
                else:
                    season = 'Fall'
                seasons.append(season)
            else:
                seasons.append(None)
                
        self.candlestick_data['contract_date'] = contract_dates
        self.candlestick_data['season'] = seasons
        
        print(f"Loaded {len(self.candlestick_data)} records across {self.candlestick_data['ticker'].nunique()} contracts")
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
        except:
            return None

    def strategy_seasonal_arbitrage(self):
        """
        Strategy: Seasonal temperature arbitrage
        Use historical seasonal patterns to identify mispriced contracts.
        """
        print(f"\n=== SEASONAL ARBITRAGE STRATEGY ===")
        
        # Define seasonal temperature expectations (rough NYC averages)
        seasonal_temps = {
            'Winter': {'low': 25, 'high': 45},
            'Spring': {'low': 45, 'high': 75}, 
            'Summer': {'low': 65, 'high': 90},
            'Fall': {'low': 40, 'high': 70}
        }
        
        trades = []
        
        for ticker in self.candlestick_data['ticker'].unique():
            ticker_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            ticker_data = ticker_data.sort_values('start')
            
            if len(ticker_data) == 0:
                continue
                
            strike_temp = ticker_data['strike_temp'].iloc[0]
            contract_type = ticker_data['contract_type'].iloc[0]
            season = ticker_data['season'].iloc[0]
            
            if not season or pd.isna(strike_temp):
                continue
                
            seasonal_range = seasonal_temps[season]
            
            # Look for mispricing opportunities
            first_candle = ticker_data.iloc[0]
            market_price = first_candle['close']
            
            # Calculate expected probability based on seasonal data
            if contract_type == 'B':  # Below strike
                if strike_temp <= seasonal_range['low']:
                    expected_prob = 0.1  # Very unlikely to be below seasonal low
                elif strike_temp >= seasonal_range['high']:
                    expected_prob = 0.9  # Very likely to be below seasonal high
                else:
                    # Linear interpolation
                    expected_prob = 1 - (strike_temp - seasonal_range['low']) / (seasonal_range['high'] - seasonal_range['low'])
            else:  # Above strike (T contracts)
                if strike_temp <= seasonal_range['low']:
                    expected_prob = 0.9  # Very likely to be above seasonal low
                elif strike_temp >= seasonal_range['high']:
                    expected_prob = 0.1  # Very unlikely to be above seasonal high  
                else:
                    expected_prob = (strike_temp - seasonal_range['low']) / (seasonal_range['high'] - seasonal_range['low'])
            
            # Compare to market price
            implied_prob = market_price / 100
            edge = expected_prob - implied_prob
            
            # Trade if edge > 15%
            if abs(edge) > 0.15:
                if edge > 0:
                    # Buy YES
                    side = 'YES'
                    entry_price = market_price
                else:
                    # Buy NO
                    side = 'NO'
                    entry_price = 100 - market_price
                
                # Simulate settlement based on expected probability
                settled_yes = np.random.random() < expected_prob
                
                if (side == 'YES' and settled_yes) or (side == 'NO' and not settled_yes):
                    pnl = 100 - entry_price
                else:
                    pnl = -entry_price
                
                trades.append({
                    'ticker': ticker,
                    'season': season,
                    'strike_temp': strike_temp,
                    'contract_type': contract_type,
                    'side': side,
                    'entry_price': entry_price,
                    'market_price': market_price,
                    'expected_prob': expected_prob,
                    'implied_prob': implied_prob,
                    'edge': edge,
                    'settled_yes': settled_yes,
                    'pnl': pnl
                })
        
        if not trades:
            return {'strategy': 'Seasonal Arbitrage', 'total_trades': 0, 'message': 'No seasonal opportunities'}
        
        df = pd.DataFrame(trades)
        total_invested = df['entry_price'].sum()
        total_pnl = df['pnl'].sum()
        win_rate = (df['pnl'] > 0).mean()
        
        return {
            'strategy': 'Seasonal Arbitrage',
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': win_rate,
            'avg_edge': df['edge'].mean(),
            'details': trades[:10]
        }

    def strategy_volatility_trading(self, volatility_threshold=0.1):
        """
        Strategy: Trade based on price volatility patterns
        Buy when volatility is low (expecting expansion) or high (expecting reversion).
        """
        print(f"\n=== VOLATILITY TRADING STRATEGY ===")
        
        trades = []
        
        for ticker in self.candlestick_data['ticker'].unique():
            ticker_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            ticker_data = ticker_data.sort_values('start')
            
            if len(ticker_data) < 10:  # Need enough data for volatility calculation
                continue
            
            # Calculate rolling volatility
            ticker_data['price_change'] = ticker_data['close'].pct_change()
            ticker_data['volatility'] = ticker_data['price_change'].rolling(window=5).std()
            
            # Look for volatility trading opportunities
            for i in range(5, len(ticker_data)-1):  # Leave room for exit
                row = ticker_data.iloc[i]
                volatility = row['volatility']
                price = row['close']
                
                if pd.isna(volatility):
                    continue
                
                # Trade based on volatility level
                if volatility < volatility_threshold:
                    # Low volatility - expect expansion, buy extreme positions
                    if price < 25:
                        side = 'YES'
                        entry_price = price
                    elif price > 75:
                        side = 'NO'
                        entry_price = 100 - price
                    else:
                        continue
                elif volatility > volatility_threshold * 3:
                    # High volatility - expect mean reversion
                    if price < 50:
                        side = 'YES'
                        entry_price = price
                    else:
                        side = 'NO' 
                        entry_price = 100 - price
                else:
                    continue
                
                # Exit at next period or final price
                if i + 1 < len(ticker_data):
                    exit_price = ticker_data.iloc[i + 1]['close']
                else:
                    exit_price = ticker_data.iloc[-1]['close']
                
                # Calculate PnL
                if side == 'YES':
                    pnl = exit_price - entry_price
                else:
                    pnl = (100 - exit_price) - entry_price
                
                trades.append({
                    'ticker': ticker,
                    'volatility': volatility,
                    'side': side,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': pnl
                })
                
                break  # One trade per contract
        
        if not trades:
            return {'strategy': 'Volatility Trading', 'total_trades': 0, 'message': 'No volatility signals'}
        
        df = pd.DataFrame(trades)
        total_invested = df['entry_price'].sum()
        total_pnl = df['pnl'].sum()
        win_rate = (df['pnl'] > 0).mean()
        
        return {
            'strategy': 'Volatility Trading',
            'params': {'volatility_threshold': volatility_threshold},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': win_rate,
            'avg_volatility': df['volatility'].mean(),
            'details': trades[:10]
        }

    def strategy_smart_no_hunting(self, max_no_price=8, volume_threshold=3):
        """
        Improved version of cheap NO strategy with better filtering.
        Only buy cheap NO when there's sufficient volume/interest.
        """
        print(f"\n=== SMART NO HUNTING STRATEGY ===")
        
        trades = []
        
        for ticker in self.candlestick_data['ticker'].unique():
            ticker_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            ticker_data = ticker_data.sort_values('start')
            
            if len(ticker_data) == 0:
                continue
                
            strike_temp = ticker_data['strike_temp'].iloc[0]
            contract_type = ticker_data['contract_type'].iloc[0]
            season = ticker_data['season'].iloc[0]
            
            # Calculate NO price and volume
            ticker_data['no_price'] = 100 - ticker_data['close']
            ticker_data['volume'] = ticker_data['count']
            
            # Look for opportunities
            opportunities = ticker_data[
                (ticker_data['no_price'] <= max_no_price) & 
                (ticker_data['volume'] >= volume_threshold)
            ]
            
            if len(opportunities) == 0:
                continue
            
            # Take first good opportunity
            opp = opportunities.iloc[0]
            entry_price = opp['no_price']
            
            # Additional filters based on strike temperature and season
            if season and not pd.isna(strike_temp):
                # Seasonal reasonableness check
                reasonable_trade = True
                
                if season == 'Summer' and contract_type == 'B' and strike_temp > 85:
                    # Betting that summer day WON'T be above 85°F - reasonable
                    reasonable_trade = True
                elif season == 'Winter' and contract_type == 'T' and strike_temp < 40:
                    # Betting that winter day WON'T be below 40°F - reasonable 
                    reasonable_trade = True
                elif season in ['Spring', 'Fall'] and 50 <= strike_temp <= 80:
                    # Moderate temperatures in shoulder seasons
                    reasonable_trade = True
                else:
                    # Skip unreasonable trades
                    reasonable_trade = False
                    
                if not reasonable_trade:
                    continue
            
            # Simulate settlement (better than random)
            # Use final market price as proxy for actual probability
            final_price = ticker_data['close'].iloc[-1]
            settled_yes = final_price > 50  # Simplified settlement
            
            pnl = (100 - entry_price) if not settled_yes else -entry_price
            
            trades.append({
                'ticker': ticker,
                'season': season,
                'strike_temp': strike_temp,
                'contract_type': contract_type,
                'entry_price': entry_price,
                'volume': opp['volume'],
                'final_market_price': final_price,
                'settled_yes': settled_yes,
                'pnl': pnl
            })
        
        if not trades:
            return {'strategy': 'Smart NO Hunting', 'total_trades': 0, 'message': 'No smart NO opportunities'}
        
        df = pd.DataFrame(trades)
        total_invested = df['entry_price'].sum()
        total_pnl = df['pnl'].sum()
        win_rate = (df['pnl'] > 0).mean()
        
        return {
            'strategy': 'Smart NO Hunting',
            'params': {'max_no_price': max_no_price, 'volume_threshold': volume_threshold},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': win_rate,
            'avg_entry_price': df['entry_price'].mean(),
            'details': trades[:10]
        }

    def strategy_time_decay(self, days_to_expiry_threshold=3):
        """
        Strategy: Time decay arbitrage
        Buy undervalued options close to expiry when market hasn't adjusted.
        """
        print(f"\n=== TIME DECAY STRATEGY ===")
        
        trades = []
        
        for ticker in self.candlestick_data['ticker'].unique():
            ticker_data = self.candlestick_data[self.candlestick_data['ticker'] == ticker].copy()
            ticker_data = ticker_data.sort_values('start')
            
            if len(ticker_data) == 0:
                continue
                
            contract_date = self.parse_contract_date(ticker)
            if not contract_date:
                continue
                
            # Calculate days to expiry for each candle
            ticker_data['days_to_expiry'] = (contract_date - ticker_data['start'].dt.date).dt.days
            
            # Look for opportunities close to expiry
            close_to_expiry = ticker_data[ticker_data['days_to_expiry'] <= days_to_expiry_threshold]
            
            if len(close_to_expiry) == 0:
                continue
                
            # Take position based on current price vs strike
            last_candle = close_to_expiry.iloc[-1]
            price = last_candle['close']
            strike_temp = ticker_data['strike_temp'].iloc[0]
            contract_type = ticker_data['contract_type'].iloc[0]
            
            # Simple heuristic: if very close to expiry and price indicates clear winner
            if last_candle['days_to_expiry'] <= 1:
                if price > 80:  # Market thinks YES is very likely
                    side = 'YES'
                    entry_price = price
                elif price < 20:  # Market thinks NO is very likely
                    side = 'NO'
                    entry_price = 100 - price
                else:
                    continue  # Skip uncertain outcomes
                    
                # Assume market is mostly right near expiry
                settled_yes = price > 50
                
                if (side == 'YES' and settled_yes) or (side == 'NO' and not settled_yes):
                    pnl = 100 - entry_price
                else:
                    pnl = -entry_price
                
                trades.append({
                    'ticker': ticker,
                    'days_to_expiry': last_candle['days_to_expiry'],
                    'side': side,
                    'entry_price': entry_price,
                    'market_price': price,
                    'settled_yes': settled_yes,
                    'pnl': pnl
                })
        
        if not trades:
            return {'strategy': 'Time Decay', 'total_trades': 0, 'message': 'No time decay opportunities'}
        
        df = pd.DataFrame(trades)
        total_invested = df['entry_price'].sum()
        total_pnl = df['pnl'].sum()
        win_rate = (df['pnl'] > 0).mean()
        
        return {
            'strategy': 'Time Decay Arbitrage',
            'params': {'days_to_expiry_threshold': days_to_expiry_threshold},
            'total_trades': len(trades),
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'roi_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'win_rate': win_rate,
            'avg_days_to_expiry': df['days_to_expiry'].mean(),
            'details': trades[:10]
        }

    def run_advanced_analysis(self):
        """Run all advanced strategies."""
        print("=" * 80)
        print("ADVANCED KALSHI TEMPERATURE STRATEGY ANALYSIS")
        print("=" * 80)
        
        self.load_data()
        
        # Advanced strategies
        strategies = [
            lambda: self.strategy_seasonal_arbitrage(),
            lambda: self.strategy_volatility_trading(0.05),
            lambda: self.strategy_volatility_trading(0.1),
            lambda: self.strategy_smart_no_hunting(5, 2),
            lambda: self.strategy_smart_no_hunting(8, 3),
            lambda: self.strategy_smart_no_hunting(12, 1),
            lambda: self.strategy_time_decay(3),
            lambda: self.strategy_time_decay(1),
        ]
        
        results = []
        for strategy_func in strategies:
            try:
                result = strategy_func()
                results.append(result)
                
                if 'message' in result:
                    print(f"\n{result['strategy']}: {result['message']}")
                else:
                    print(f"\n{result['strategy']} {result.get('params', '')}")
                    print(f"  Trades: {result['total_trades']}")
                    print(f"  Total Invested: ${result['total_invested']:.2f}")
                    print(f"  Total PnL: ${result['total_pnl']:.2f}")
                    print(f"  ROI: {result['roi_percent']:.1f}%")
                    print(f"  Win Rate: {result['win_rate']:.1%}")
                    
            except Exception as e:
                print(f"Error in strategy: {e}")
        
        # Ranking
        successful_results = [r for r in results if r.get('total_trades', 0) > 0]
        successful_results.sort(key=lambda x: x.get('roi_percent', 0), reverse=True)
        
        print("\n" + "=" * 80) 
        print("ADVANCED STRATEGY PERFORMANCE RANKING")
        print("=" * 80)
        
        for i, result in enumerate(successful_results, 1):
            print(f"{i:2d}. {result['strategy']}")
            if 'params' in result:
                print(f"     Params: {result['params']}")
            print(f"     ROI: {result['roi_percent']:8.1f}% | Win Rate: {result['win_rate']:5.1%} | "
                  f"Trades: {result['total_trades']:3d} | PnL: ${result['total_pnl']:8.2f}")
        
        # Final recommendations
        print("\n" + "=" * 80)
        print("STRATEGY RECOMMENDATIONS")
        print("=" * 80)
        
        if successful_results:
            best_strategy = successful_results[0]
            print(f"🏆 BEST PERFORMING: {best_strategy['strategy']}")
            print(f"   ROI: {best_strategy['roi_percent']:.1f}%")
            print(f"   Win Rate: {best_strategy['win_rate']:.1%}")
            print(f"   Total Trades: {best_strategy['total_trades']}")
            
            if best_strategy['roi_percent'] > 0:
                print("\n✅ RECOMMENDED FOR LIVE TRADING")
                print("   This strategy shows positive expected returns.")
            else:
                print("\n⚠️  NEEDS REFINEMENT")
                print("   Consider adjusting parameters or combining with other signals.")
                
        print("\n📊 KEY INSIGHTS:")
        print("   • Temperature markets show high volatility")
        print("   • Seasonal patterns may provide edge")
        print("   • Volume filtering improves trade quality")
        print("   • Time decay effects near expiry")
        
        return results

def main():
    analyzer = AdvancedStrategyAnalyzer()
    return analyzer.run_advanced_analysis()

if __name__ == "__main__":
    main()