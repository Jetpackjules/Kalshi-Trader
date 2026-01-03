import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from complex_strategy_backtest import ComplexBacktester, Wallet, calculate_convex_fee, market_end_time_from_ticker, payout_time_from_ticker, settle_mid_price
import plotly.graph_objects as go

# Paths
VM_LOGS_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs"
TRADES_FILE = os.path.join(VM_LOGS_DIR, "trades.csv")
MARKET_LOGS_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"

class ReplayBacktester(ComplexBacktester):
    def __init__(self, start_date, initial_capital=1000.0):
        # Initialize parent
        super().__init__()
        # Override the portfolio with our custom initial capital
        self.initial_capital = initial_capital
        self.start_date = start_date
        # We only have one "strategy" which is the Replay
        self.strategies = [] # Clear default strategies
        self.portfolios = {
            'Replay': {
                'wallet': Wallet(initial_capital),
                'inventory_yes': {'Replay': {}},
                'inventory_no': {'Replay': {}},
                'active_limit_orders': {},
                'trades': [],
                'paid_out': set()
            }
        }
        self.real_trades = self.load_real_trades(start_date)
        self.market_data_cache = {}

    def load_real_trades(self, start_date):
        print(f"Loading real trades from {TRADES_FILE}...")
        df = pd.read_csv(TRADES_FILE)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df[df['timestamp'] >= start_date]
        df = df.sort_values('timestamp')
        print(f"Loaded {len(df)} trades to replay.")
        return df

    def get_market_data(self, ticker):
        if ticker in self.market_data_cache:
            return self.market_data_cache[ticker]
        
        # Ticker format: KXHIGHNY-25DEC23-B42.5
        # We need to extract the date part: 25DEC23
        try:
            parts = ticker.split('-')
            date_str = parts[1] # 25DEC23
            
            # Construct filename: market_data_KXHIGHNY-25DEC23.csv
            filename = f"market_data_KXHIGHNY-{date_str}.csv"
            path = os.path.join(MARKET_LOGS_DIR, filename)
            
            if not os.path.exists(path):
                # print(f"Warning: Market log not found for {ticker} at {path}")
                return None
                
            # Load the daily file if not already loaded (we might cache the whole file)
            # But wait, we cache by ticker.
            # Let's cache the daily DF separately?
            # For simplicity, let's just load and filter.
            
            df_day = pd.read_csv(path)
            # Filter for specific ticker
            # Column is 'market_ticker'
            df_ticker = df_day[df_day['market_ticker'] == ticker].copy()
            
            if df_ticker.empty:
                return None
                
            df_ticker['timestamp'] = pd.to_datetime(df_ticker['timestamp'])
            self.market_data_cache[ticker] = df_ticker
            return df_ticker
            
        except Exception as e:
            print(f"Error loading market data for {ticker}: {e}")
            return None

    def run_replay(self):
        print("Starting Replay...")
        
        # Initialize Portfolio
        portfolio = {
            'wallet': Wallet(self.initial_capital),
            'inventory_yes': {'Replay': {}},
            'inventory_no': {'Replay': {}},
            'active_limit_orders': {}, # Not used but needed for structure
            'trades': [],
            'paid_out': set()
        }
        
        # We need to step through time to handle settlements correctly.
        # Settlements happen at 1AM next day usually.
        # We can just iterate through the trades, but we must check for settlements 
        # that should have happened *before* the current trade.
        
        # Get all unique tickers to monitor for settlement
        active_tickers = set()
        
        # Time iteration
        # We'll jump from trade to trade, but check for settlements in between.
        
        current_time = self.start_date
        
        # Add a final "trade" at now to flush remaining settlements
        final_timestamp = datetime.now()
        
        # Iterate through trades
        for _, row in self.real_trades.iterrows():
            trade_time = row['timestamp']
            ticker = row['ticker']
            
            # 1. Advance time and handle settlements
            # We need to check if any active tickers expired/settled between current_time and trade_time
            # This is tricky without a fine-grained loop.
            # Simplified: Check all active tickers. If their payout time passed, settle them.
            
            # Update current time to trade time
            current_time = trade_time
            
            # Check settlements
            # We need to know the settlement PRICE.
            # We can use the market logs.
            # Or simpler: assume if it's expired, we get 100 or 0 based on the result.
            # But we don't know the result without data!
            # Let's try to infer result from the trade log? No.
            # We MUST have market data.
            
            self.handle_settlements(portfolio, current_time)
            
            # 2. Execute Trade
            self.execute_trade(portfolio, row)
            active_tickers.add(ticker)
            
            # Log status
            # print(f"[{current_time}] Equity: {portfolio['wallet'].total_equity(portfolio, {}, {})}")

        # Final flush
        current_time = final_timestamp
        self.handle_settlements(portfolio, current_time)
        
        # Calculate MtM of remaining positions
        mtm_value = 0
        print("\n--- Open Positions ---")
        for src in portfolio['inventory_yes']:
            for ticker, qty in portfolio['inventory_yes'][src].items():
                if qty > 0:
                    # Get last price
                    df = self.get_market_data(ticker)
                    price = 0
                    if df is not None and not df.empty:
                        last_row = df.iloc[-1]
                        y_bid = last_row['best_yes_bid']
                        y_ask = last_row['implied_yes_ask']
                        if not pd.isna(y_bid) and not pd.isna(y_ask):
                            price = (y_bid + y_ask) / 2
                        elif not pd.isna(y_bid): price = y_bid
                        else: price = 0
                    
                    val = qty * (price / 100.0)
                    mtm_value += val
                    print(f"YES {ticker}: {qty} @ {price:.1f} = ${val:.2f}")

        for src in portfolio['inventory_no']:
            for ticker, qty in portfolio['inventory_no'][src].items():
                if qty > 0:
                    # Get last price
                    df = self.get_market_data(ticker)
                    price = 0
                    if df is not None and not df.empty:
                        last_row = df.iloc[-1]
                        n_bid = last_row['best_no_bid']
                        n_ask = last_row['implied_no_ask']
                        if not pd.isna(n_bid) and not pd.isna(n_ask):
                            price = (n_bid + n_ask) / 2
                        elif not pd.isna(n_bid): price = n_bid
                        else: price = 0
                    
                    val = qty * (price / 100.0)
                    mtm_value += val
                    print(f"NO {ticker}: {qty} @ {price:.1f} = ${val:.2f}")

        total_equity = portfolio['wallet'].available_cash + mtm_value
        
        print(f"\nFinal Cash: {portfolio['wallet'].available_cash:.2f}")
        print(f"MtM Value: {mtm_value:.2f}")
        print(f"Total Equity: {total_equity:.2f}")
        return portfolio

    def handle_settlements(self, portfolio, current_time):
        # Iterate over all held positions
        # YES
        for src in portfolio['inventory_yes']:
            for ticker, qty in list(portfolio['inventory_yes'][src].items()):
                if qty > 0:
                    self.try_settle(portfolio, ticker, qty, True, current_time, src)
        
        # NO
        for src in portfolio['inventory_no']:
            for ticker, qty in list(portfolio['inventory_no'][src].items()):
                if qty > 0:
                    self.try_settle(portfolio, ticker, qty, False, current_time, src)

    def try_settle(self, portfolio, ticker, qty, is_yes, current_time, source):
        # Check if settled
        pay_time = payout_time_from_ticker(ticker)
        if pay_time and current_time >= pay_time:
            # It's payout time!
            # We need the result.
            
            df = self.get_market_data(ticker)
            final_price = 0
            if df is not None and not df.empty:
                last_row = df.iloc[-1]
                # Columns: timestamp,market_ticker,best_yes_bid,best_no_bid,implied_no_ask,implied_yes_ask
                # We need a mid price or settlement price.
                # Let's use best_yes_bid and implied_yes_ask to estimate mid.
                
                y_bid = last_row['best_yes_bid']
                y_ask = last_row['implied_yes_ask']
                
                if pd.isna(y_bid) or pd.isna(y_ask):
                     # Try NO side
                     n_bid = last_row['best_no_bid']
                     n_ask = last_row['implied_no_ask']
                     if not pd.isna(n_bid) and not pd.isna(n_ask):
                         mid = 100 - ((n_bid + n_ask) / 2)
                     else:
                         # Fallback to whatever is available
                         mid = 50 # Unknown
                else:
                    mid = (y_bid + y_ask) / 2
                
                if mid > 98: final_price = 100
                elif mid < 2: final_price = 0
                else: final_price = mid # Cash settlement?
            else:
                # Fallback: Can't settle without data.
                # print(f"Warning: No market data for {ticker}, cannot settle.")
                return

            payout = 0
            if is_yes:
                payout = qty * (final_price / 100.0)
                portfolio['inventory_yes'][source][ticker] = 0
            else:
                payout = qty * ((100 - final_price) / 100.0)
                portfolio['inventory_no'][source][ticker] = 0
            
            if payout > 0:
                portfolio['wallet'].add_cash(payout) # Immediate add for simplicity, or use add_unsettled if strictly following time
                # Since we are AT payout time, it's cash.
            
            # Log it
            portfolio['trades'].append({
                'time': current_time,
                'action': 'PAYOUT',
                'ticker': ticker,
                'price': final_price,
                'qty': qty,
                'fee': 0,
                'cost': -payout, # Negative cost = profit
                'source': 'Settlement',
                'capital_after': portfolio['wallet'].available_cash
            })

    def execute_trade(self, portfolio, row):
        action = row['action']
        ticker = row['ticker']
        price = row['price']
        qty = row['qty']
        fee = row['fee']
        
        cost_per_share = price / 100.0
        total_cost = (qty * cost_per_share) + fee
        
        # Deduct Cash
        # We force the spend even if negative (shouldn't happen in replay if real bot had cash)
        portfolio['wallet'].available_cash -= total_cost
        
        # Add Inventory
        if 'BUY_YES' in action:
            if ticker not in portfolio['inventory_yes']['Replay']:
                portfolio['inventory_yes']['Replay'][ticker] = 0
            portfolio['inventory_yes']['Replay'][ticker] += qty
        elif 'BUY_NO' in action:
            if ticker not in portfolio['inventory_no']['Replay']:
                portfolio['inventory_no']['Replay'][ticker] = 0
            portfolio['inventory_no']['Replay'][ticker] += qty
            
        # Log
        portfolio['trades'].append({
            'time': row['timestamp'],
            'action': action,
            'ticker': ticker,
            'price': price,
            'qty': qty,
            'fee': fee,
            'cost': total_cost,
            'source': 'Replay',
            'capital_after': portfolio['wallet'].available_cash
        })

    def generate_chart(self, portfolio):
        # Extract equity curve
        # We need to reconstruct daily equity.
        # Iterate trades and calc equity at each step?
        # Or just daily snapshots.
        
        dates = []
        equities = []
        
        # Reconstruct equity series
        # Start
        current_cash = self.initial_capital
        # We need to track inventory value too for Mark-to-Market
        # This is hard without full market data history.
        # Let's just plot Cash + Settled PnL?
        # No, user wants "Equity".
        # Equity = Cash + Position Value.
        # Position Value requires current market price.
        
        # Simplified: Just plot Cash (Realized Equity) for now?
        # Or try to use the market data cache.
        
        # Let's generate a point for every trade
        running_inventory = {} # ticker -> {yes: qty, no: qty}
        
        history = []
        
        # Re-run logic to track history (inefficient but clear)
        # Actually we can just parse the 'trades' list from portfolio
        
        # But we need MTM value.
        # Let's skip MTM for the first pass and just show Cash?
        # No, that will look jagged.
        # Let's try to get MTM if possible.
        
        pass

if __name__ == "__main__":
    # Start date: Dec 23 (since we have logs/trades from then)
    start_dt = datetime(2025, 12, 23)
    
    # Initial Capital: Found 12.99 in logs
    replay = ReplayBacktester(start_dt, initial_capital=12.99)
    portfolio = replay.run_replay()
    
    # Generate simple CSV report of trades and final equity
    df_res = pd.DataFrame(portfolio['trades'])
    df_res.to_csv("replay_trades_log.csv", index=False)
    print(f"Final Equity (Cash): {portfolio['wallet'].available_cash}")
