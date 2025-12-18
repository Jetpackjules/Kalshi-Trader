import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import logging
import sys
import os

# Add dashboard to path
sys.path.append(os.path.join(os.getcwd(), 'dashboard'))


class Backtester:
    def __init__(self, strategy, initial_capital=10000.0):
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions = {} # ticker -> quantity
        self.trades = []
        self.history = []
        
    def run(self, start_date, end_date):
        """
        Simulates the strategy over a date range.
        """
        print(f"Starting backtest from {start_date.date()} to {end_date.date()}...")
        
        # Pre-fetch NWS data for the whole range to save calls
        from utils.fetch_nws import get_nws_history
        self.nws_data = get_nws_history(start_date, end_date)
        if not self.nws_data.empty:
            self.nws_data['timestamp'] = pd.to_datetime(self.nws_data['timestamp'], utc=True)
            self.nws_data = self.nws_data.sort_values('timestamp')
            
        current_date = start_date
        while current_date <= end_date:
            self.process_date(current_date)
            current_date += timedelta(days=1)
            
        self.generate_report()
        
    def process_date(self, date):
        """
        Processes a single day.
        """
        date_str = date.strftime("%b%d").upper()
        # print(f"Processing {date_str}...")
        
        from utils.fetch_orderbook import get_markets_by_date
        from utils.fetch_history import get_full_history
        
        # 1. Get markets for this date
        markets = get_markets_by_date(date_str)
        if not markets:
            return

        # 2. Get Max Temp for this day (Actual) - for settlement
        # In a real backtest, we wouldn't know this until the end.
        # But we need it to settle positions.
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        
        day_temps = self.nws_data[
            (self.nws_data['timestamp'] >= day_start) & 
            (self.nws_data['timestamp'] < day_end)
        ]
        
        if day_temps.empty:
            return
            
        actual_high = day_temps['temp_f'].max()
        
        # 3. Simulate Trading Day
        # We iterate through hourly steps? Or just one decision point?
        # Let's do one decision point: 12:00 PM ET (approx 17:00 UTC)
        decision_time = day_start.replace(hour=17)
        
        # Get current temp at decision time
        current_temps = day_temps[day_temps['timestamp'] <= decision_time]
        if current_temps.empty:
            current_temp = 0 # Should not happen if we have data
        else:
            current_temp = current_temps.iloc[-1]['temp_f']
            
        # 4. For each market, check strategy
        print(f"Checking {len(markets)} markets for {date_str}...")
        for market in markets:
            ticker = market['ticker']
            
            # Get market history to find price at decision time
            history = get_full_history(ticker)
            if not history:
                print(f"No history for {ticker}")
                continue
                
            hist_df = pd.DataFrame(history)
            hist_df['ts'] = pd.to_datetime(hist_df['end_period_ts'], unit='s', utc=True)
            
            # Find candle closest to decision_time
            # We want the latest candle BEFORE decision_time
            past_candles = hist_df[hist_df['ts'] <= decision_time]
            if past_candles.empty:
                print(f"No past candles for {ticker} at {decision_time}")
                continue
                
            last_candle = past_candles.iloc[-1]
            price_data = last_candle.get('price', {})
            if not isinstance(price_data, dict):
                continue
            
            # Assuming we buy YES
            market_price = price_data.get('close')
            if market_price is None:
                continue
                
            # Strategy Logic
            signal = self.strategy.on_tick(market, current_temp)
            print(f"Ticker: {ticker}, Type: {market.get('strike_type')}, Floor: {market.get('floor_strike')}, Temp: {current_temp}, Signal: {signal}")
            
            if signal == "BUY_YES":
                # Buy 100 contracts
                cost = market_price * 100 / 100.0 # Price is in cents
                if self.capital >= cost:
                    self.capital -= cost
                    self.positions[ticker] = self.positions.get(ticker, 0) + 100
                    self.trades.append({
                        'date': date_str,
                        'ticker': ticker,
                        'action': 'BUY_YES',
                        'price': market_price,
                        'qty': 100,
                        'temp_at_trade': current_temp
                    })
            elif signal == "BUY_NO":
                # Buy 100 NO contracts
                # NO price = 100 - YES price
                no_price = 100 - market_price
                cost = no_price * 100 / 100.0
                if self.capital >= cost:
                    self.capital -= cost
                    # Store negative quantity for NO? Or separate tracking?
                    # Let's use negative for NO positions for simplicity in this hack
                    self.positions[ticker] = self.positions.get(ticker, 0) - 100
                    self.trades.append({
                        'date': date_str,
                        'ticker': ticker,
                        'action': 'BUY_NO',
                        'price': no_price,
                        'qty': 100,
                        'temp_at_trade': current_temp
                    })
            
            # Settlement
            # If we have a position, settle it
            qty = self.positions.get(ticker, 0)
            if qty != 0:
                # Determine outcome (YES wins?)
                strike_type = market.get('strike_type')
                floor = market.get('floor_strike')
                cap = market.get('cap_strike')
                
                yes_won = False
                if strike_type == 'greater':
                    if floor is not None and actual_high > floor:
                        yes_won = True
                elif strike_type == 'less':
                    if cap is not None and actual_high < cap:
                        yes_won = True
                elif strike_type == 'between':
                    if floor is not None and cap is not None:
                        if floor <= actual_high < cap:
                            yes_won = True
                
                payout = 0
                if qty > 0: # Long YES
                    if yes_won:
                        payout = qty * 1.00
                else: # Long NO (qty is negative)
                    if not yes_won:
                        payout = abs(qty) * 1.00
                    
                self.capital += payout
                self.positions[ticker] = 0 # Close position
                
                # Update last trade with result
                if self.trades and self.trades[-1]['ticker'] == ticker:
                    trade = self.trades[-1]
                    trade['payout'] = payout
                    cost = trade['price'] * trade['qty'] / 100.0
                    trade['profit'] = payout - cost

    def generate_report(self):
        print(f"Backtest Complete.")
        print(f"Initial Capital: ${self.initial_capital:.2f}")
        print(f"Final Capital:   ${self.capital:.2f}")
        print(f"Return:          {(self.capital - self.initial_capital) / self.initial_capital:.2%}")
        print(f"Trades:          {len(self.trades)}")
        if self.trades:
            print("Last 5 Trades:")
            for t in self.trades[-5:]:
                print(t)

if __name__ == "__main__":
    class SimpleStrategy:
        def on_tick(self, market, current_temp):
            # Simple Logic:
            strike_type = market.get('strike_type')
            floor = market.get('floor_strike')
            cap = market.get('cap_strike')
            
            # 1. Momentum: If "Greater" and temp is rising close to floor
            if strike_type == 'greater' and floor is not None:
                if current_temp >= floor - 2:
                    return "BUY_YES"
            
            # 2. Arbitrage: If "Less" and temp is ALREADY > cap
            # High temp can only go up. If it's already above cap, "Less than cap" is impossible.
            # So YES is 0. NO is 100.
            if strike_type == 'less' and cap is not None:
                if current_temp > cap:
                    return "BUY_NO"
            
            return "HOLD"
            
    # Run for last 14 days
    end_d = datetime.now(timezone.utc)
    start_d = end_d - timedelta(days=14)
    
    bt = Backtester(SimpleStrategy())
    bt.run(start_d, end_d)

