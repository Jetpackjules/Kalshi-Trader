import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import logging
import sys
import os
import random

# Add dashboard to path (assuming running from weather_forecast_backtest/)
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'dashboard')))
# Also try parent directory if running from root
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '../dashboard')))

try:
    from utils.fetch_nws import get_nws_history
    from utils.fetch_orderbook import get_markets_by_date
    from utils.fetch_history import get_full_history
except ImportError:
    # Fallback if paths are weird
    sys.path.append(r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\dashboard")
    from utils.fetch_nws import get_nws_history
    from utils.fetch_orderbook import get_markets_by_date
    from utils.fetch_history import get_full_history

def get_local_weather_history(start_date, end_date):
    """Read weather history from local CSV."""
    csv_path = "nws_weather_history.csv"
    if not os.path.exists(csv_path):
        # Try parent dir
        csv_path = "../nws_weather_history.csv"
        if not os.path.exists(csv_path):
            print(f"Error: Could not find {csv_path}")
            return pd.DataFrame()
            
    try:
        # Try reading with default header
        try:
            df = pd.read_csv(csv_path, on_bad_lines='skip')
        except:
            # Fallback: Read with 5 columns if header mismatch
            df = pd.read_csv(csv_path, names=['timestamp', 'temp_c', 'temp_f', 'source', 'raw_data'], header=0)
            
        # Ensure columns exist
        if 'temp_f' not in df.columns and 'temp_c' in df.columns:
             df['temp_f'] = (df['temp_c'] * 9/5) + 32
             
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        
        # Filter
        mask = (df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)
        return df.loc[mask]
    except Exception as e:
        print(f"Error reading local weather CSV: {e}")
        return pd.DataFrame()

def get_local_markets_by_date(date_str):
    """Get markets from local history CSV matching the date string."""
    csv_path = "kalshi_market_history.csv"
    if not os.path.exists(csv_path):
        csv_path = "../kalshi_market_history.csv"
        if not os.path.exists(csv_path):
            return []
            
    try:
        df = pd.read_csv(csv_path)
        # Ticker format: KXHIGHNY-25NOV24-T56
        # date_str: NOV24
        target = f"-25{date_str}-"
        
        relevant_tickers = df[df['ticker'].str.contains(target, na=False)]['ticker'].unique()
        
        markets = []
        for ticker in relevant_tickers:
            parts = ticker.split('-')
            if len(parts) < 3: continue
            
            strike_part = parts[2] # T56 or B56.5
            strike_type = 'greater' if strike_part.startswith('T') else 'less'
            strike_val = float(strike_part[1:])
            
            market = {
                'ticker': ticker,
                'strike_type': strike_type,
                'floor_strike': strike_val if strike_type == 'greater' else None,
                'cap_strike': strike_val if strike_type == 'less' else None
            }
            markets.append(market)
            
        return markets
    except Exception as e:
        print(f"Error reading local markets: {e}")
        return []

class Strategy:
    def __init__(self, name):
        self.name = name
    
    def on_tick(self, market, current_temp, market_price, current_time, forecast_high):
        return "HOLD"

class ForecastStrategy(Strategy):
    def __init__(self, margin=5):
        super().__init__(f"Forecast Value (Margin {margin})")
        self.margin = margin
        
    def on_tick(self, market, current_temp, market_price, current_time, forecast_high):
        # Logic:
        # If Forecast High > Strike + Margin -> Buy YES (Expect High Temp)
        # If Forecast High < Strike - Margin -> Buy NO (Expect Low Temp)
        
        strike_type = market.get('strike_type')
        floor = market.get('floor_strike')
        cap = market.get('cap_strike')
        
        # We only care about the "High" temp markets (KXHIGHNY)
        
        # Case 1: "High > X" (Greater)
        if strike_type == 'greater' and floor is not None:
            # If Forecast says 60, and Market is > 50.
            # If 60 > 50 + 5 -> Buy YES
            if forecast_high > (floor + self.margin):
                if market_price < 90: # Don't buy if already expensive
                    return "BUY_YES"
            # If Forecast says 40, and Market is > 50.
            # If 40 < 50 - 5 -> Buy NO
            elif forecast_high < (floor - self.margin):
                if market_price > 10: # Don't buy NO if already cheap (YES < 10)
                    return "BUY_NO"

        # Case 2: "High < X" (Less)
        elif strike_type == 'less' and cap is not None:
            # If Forecast says 40, and Market is < 50.
            # If 40 < 50 - 5 -> Buy YES (It will be less)
            if forecast_high < (cap - self.margin):
                if market_price < 90:
                    return "BUY_YES"
            # If Forecast says 60, and Market is < 50.
            # If 60 > 50 + 5 -> Buy NO (It won't be less)
            elif forecast_high > (cap + self.margin):
                if market_price > 10:
                    return "BUY_NO"
                    
        return "HOLD"

class MultiBacktester:
    def __init__(self, strategies, initial_capital=10000.0, data_delay_min=0, forecast_noise=2.0):
        self.strategies = strategies
        self.initial_capital = initial_capital
        self.data_delay_min = data_delay_min
        self.forecast_noise = forecast_noise # +/- degrees of error
        self.results = {s.name: {'capital': initial_capital, 'trades': [], 'positions': {}} for s in strategies}
        
    def run(self, start_date, end_date):
        print(f"Starting Forecast Backtest ({start_date.date()} to {end_date.date()})")
        print(f"Simulated Forecast Error: +/- {self.forecast_noise} F")
        
        # Fetch NWS Data
        print("Fetching Weather Data (Local)...")
        self.nws_data = get_local_weather_history(start_date, end_date)
        if self.nws_data.empty:
            print("No weather data found!")
            return
            
        self.nws_data = self.nws_data.sort_values('timestamp')
        
        current_date = start_date
        while current_date <= end_date:
            self.process_date(current_date)
            current_date += timedelta(days=1)
            
        self.generate_report()
        
    def process_date(self, date):
        date_str = date.strftime("%b%d").upper()
        print(f"Processing {date_str}...")
        
        markets = get_local_markets_by_date(date_str)
        if not markets:
            print(f"No local markets found for {date_str}")
            return

        # Determine Actual High for Settlement
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        day_temps = self.nws_data[(self.nws_data['timestamp'] >= day_start) & (self.nws_data['timestamp'] < day_end)]
        if day_temps.empty:
            return
        actual_high = day_temps['temp_f'].max()
        
        # Simulate Forecast (Actual + Noise)
        # We generate ONE forecast for the day (e.g. the morning forecast)
        forecast_error = random.uniform(-self.forecast_noise, self.forecast_noise)
        forecast_high = actual_high + forecast_error
        
        print(f"  Actual High: {actual_high:.1f}F | Sim Forecast: {forecast_high:.1f}F (Err: {forecast_error:.1f}F)")
        
        # Simulate Hourly Trading
        hours_to_trade = range(14, 24) # 9 AM to 6 PM ET
        
        for hour in hours_to_trade:
            current_time = day_start.replace(hour=hour)
            
            # Get Weather View (Delayed)
            view_time = current_time - timedelta(minutes=self.data_delay_min)
            visible_temps = day_temps[day_temps['timestamp'] <= view_time]
            
            if visible_temps.empty:
                current_temp = 0
            else:
                current_temp = visible_temps['temp_f'].max()
            
            # Iterate Markets
            for market in markets:
                ticker = market['ticker']
                history = get_full_history(ticker)
                if not history: continue
                
                hist_df = pd.DataFrame(history)
                hist_df['ts'] = pd.to_datetime(hist_df['end_period_ts'], unit='s', utc=True)
                
                past_candles = hist_df[hist_df['ts'] <= current_time]
                if past_candles.empty: continue
                
                last_candle = past_candles.iloc[-1]
                price_data = last_candle.get('price', {})
                if not isinstance(price_data, dict): continue
                
                yes_price = price_data.get('close')
                if yes_price is None: continue
                
                # Run each strategy
                for strategy in self.strategies:
                    res = self.results[strategy.name]
                    if res['capital'] <= 0: continue
                    
                    if ticker in res['positions']:
                        continue
                    
                    # Pass forecast_high to strategy
                    signal = strategy.on_tick(market, current_temp, yes_price, current_time, forecast_high)
                    
                    trade = None
                    if signal == "BUY_YES":
                        cost = yes_price
                        if res['capital'] >= cost:
                            trade = {'action': 'BUY_YES', 'price': yes_price, 'ticker': ticker, 'temp': current_temp, 'time': current_time}
                    elif signal == "BUY_NO":
                        cost = 100 - yes_price
                        if res['capital'] >= cost:
                            trade = {'action': 'BUY_NO', 'price': cost, 'ticker': ticker, 'temp': current_temp, 'time': current_time}
                            
                    if trade:
                        res['capital'] -= trade['price']
                        res['positions'][ticker] = trade
                        res['trades'].append(trade)

        # End of Day Settlement
        for strategy in self.strategies:
            res = self.results[strategy.name]
            for ticker, trade in list(res['positions'].items()):
                market = next((m for m in markets if m['ticker'] == ticker), None)
                if not market: continue
                
                payout = 0
                strike_type = market.get('strike_type')
                floor = market.get('floor_strike')
                cap = market.get('cap_strike')
                
                yes_won = False
                if strike_type == 'greater':
                    if floor is not None and actual_high > floor: yes_won = True
                elif strike_type == 'less':
                    if cap is not None and actual_high < cap: yes_won = True
                elif strike_type == 'between':
                    if floor is not None and cap is not None:
                        if floor <= actual_high < cap: yes_won = True
                        
                if trade['action'] == 'BUY_YES' and yes_won: payout = 100
                if trade['action'] == 'BUY_NO' and not yes_won: payout = 100
                
                res['capital'] += payout
                
                for t in res['trades']:
                    if t == trade:
                        t['payout'] = payout
                        t['profit'] = payout - t['price']
                        t['actual_high'] = actual_high
            
            res['positions'] = {}

    def generate_report(self):
        print("\n=== Backtest Results ===")
        print(f"Forecast Error: +/- {self.forecast_noise} F\n")
        
        for name, res in self.results.items():
            initial = self.initial_capital
            final = res['capital']
            roi = (final - initial) / initial
            trades = len(res['trades'])
            wins = len([t for t in res['trades'] if t['profit'] > 0])
            
            print(f"Strategy: {name}")
            print(f"  Trades: {trades}")
            print(f"  Wins:   {wins}")
            print(f"  Return: {roi:.2%}")
            print(f"  PnL:    ${final - initial:.2f}")
            print("-" * 30)

if __name__ == "__main__":
    # Test with varying levels of forecast accuracy
    strategies = [
        ForecastStrategy(margin=2), # Aggressive
        ForecastStrategy(margin=5), # Conservative
    ]
    
    # We only have data for Nov 24-25 in the CSVs provided
    start_d = datetime(2025, 11, 24, tzinfo=timezone.utc)
    end_d = datetime(2025, 11, 25, tzinfo=timezone.utc)
    
    # Run with 2.0 degrees of noise (Typical NWS error is ~2-3F)
    bt = MultiBacktester(strategies, forecast_noise=2.0)
    bt.run(start_d, end_d)
