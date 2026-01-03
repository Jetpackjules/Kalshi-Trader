import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime, timedelta
import math
from collections import defaultdict

# --- Configuration ---
LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
START_DATE = "25DEC23"
END_DATE = "25DEC26"
INITIAL_CAPITAL = 100.00

# --- Helper Functions ---
def best_yes_ask(ms): return ms.get('yes_ask', np.nan)
def best_yes_bid(ms): return ms.get('yes_bid', np.nan)

def calculate_convex_fee(price, qty):
    p = price / 100.0
    raw_fee = 0.07 * qty * p * (1 - p)
    return math.ceil(raw_fee * 100) / 100.0

def market_end_time_from_ticker(ticker):
    try:
        parts = ticker.strip().split('-')
        for p in parts:
            if len(p) == 7 and p[:2].isdigit():
                d = datetime.strptime(p, "%y%b%d")
                return (d + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    except: pass
    return None

# --- Strategy Classes (Copied from multi_strategy_backtest.py) ---

class Strategy:
    def __init__(self, name, risk_pct=0.5):
        self.name = name
        self.risk_pct = risk_pct
    def start_new_day(self, first_timestamp): pass
    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0): return None

class InventoryAwareMarketMaker(Strategy):
    def __init__(self, name, risk_pct=0.5, max_inventory=5000, inventory_penalty=0.01, window=20, max_offset=2):
        super().__init__(name, risk_pct)
        self.max_inventory = max_inventory
        self.inventory_penalty = inventory_penalty
        self.window = window
        self.max_offset = max_offset
        self.fair_price = None 
        self.alpha = 2 / (window + 1)
        
    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        orders = []
        net_inventory = inventories['YES'] - inventories['NO']
        tick_expiry = current_time + timedelta(seconds=10)
        
        yes_ask = market_state.get('yes_ask')
        no_ask = market_state.get('no_ask')
        if pd.isna(yes_ask) or pd.isna(no_ask): return None
        
        best_bid = 100 - no_ask
        mid = (best_bid + yes_ask) / 2.0
        
        if self.fair_price is None: self.fair_price = mid
        else: self.fair_price = self.alpha * mid + (1 - self.alpha) * self.fair_price
            
        can_buy_yes = net_inventory < self.max_inventory
        can_sell_yes = net_inventory > -self.max_inventory
        
        spread = yes_ask - best_bid
        if spread <= 0: return None
        
        base_offset = min(spread / 2 - 1, self.max_offset)
        base_offset = max(0, base_offset)
        inv_adj = net_inventory * self.inventory_penalty
        
        my_bid = self.fair_price - base_offset - inv_adj
        my_ask = self.fair_price + base_offset - inv_adj
        
        my_bid_tick = max(1, min(99, int(math.floor(my_bid))))
        my_ask_tick = max(1, min(99, int(math.ceil(my_ask))))
        
        qty = 10
        
        if can_buy_yes:
             orders.append({'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 'type': 'LIMIT', 'price': my_bid_tick, 'expiry': tick_expiry, 'source': 'MM'})
        if can_sell_yes:
             orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 'type': 'LIMIT', 'price': 100 - my_ask_tick, 'expiry': tick_expiry, 'source': 'MM'})
             
        return orders

class MicroScalper(Strategy):
    def __init__(self, name, threshold=1.5, risk_pct=0.5):
        super().__init__(name, risk_pct)
        self.threshold = threshold
        self.last_mids = {}
        
    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        yes_ask = market_state.get('yes_ask')
        no_ask = market_state.get('no_ask')
        if pd.isna(yes_ask) or pd.isna(no_ask): return None
        
        best_bid = 100 - no_ask
        mid = (best_bid + yes_ask) / 2.0
        last_mid = self.last_mids.get(ticker)
        self.last_mids[ticker] = mid
        
        if last_mid is None: return None
        if active_orders: return None
        
        delta = mid - last_mid
        tick_expiry = current_time + timedelta(seconds=30)
        qty = 5
        
        if delta >= self.threshold:
            return [{'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 'type': 'LIMIT', 'price': int(100 - yes_ask), 'expiry': tick_expiry, 'source': 'Scalper'}]
        elif delta <= -self.threshold:
            return [{'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 'type': 'LIMIT', 'price': int(best_bid), 'expiry': tick_expiry, 'source': 'Scalper'}]
        return None

class ParametricStrategy(Strategy):
    def __init__(self, name, wait_minutes, risk_pct, logic_type="trend_no", greedy=False, take_profit=None, freshness_tolerance=None, min_price=50, max_price=70):
        super().__init__(name, risk_pct)
        self.wait_minutes = wait_minutes
        self.logic_type = logic_type
        self.min_price = min_price
        self.max_price = max_price
        
    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        orders = []
        yes_ask = market_state.get('yes_ask')
        if pd.isna(yes_ask): return None
        
        # Trend Logic: Buy NO if price is in range
        market_price = yes_ask
        no_price = 100 - market_price
        
        if self.min_price < no_price < self.max_price:
            # Simple entry: Buy NO
            # Check if we already have position? The original didn't check holdings in on_snapshot, 
            # but the backtester handles execution.
            # We should probably limit frequency.
            # For this debug, let's just place a limit order if no active order
            if not active_orders:
                tick_expiry = current_time + timedelta(minutes=5)
                orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': 10, 'type': 'LIMIT', 'price': int(no_price), 'expiry': tick_expiry, 'source': 'Trend'})
        return orders

# --- Backtester ---
class SimpleBacktester:
    def __init__(self):
        # Use the Trend Strategy
        self.strategy = ParametricStrategy("Trend Strategy", wait_minutes=0, risk_pct=0.5, min_price=50, max_price=75)
        self.wallet = INITIAL_CAPITAL
        self.inventory_yes = defaultdict(int)
        self.inventory_no = defaultdict(int)
        self.active_orders = defaultdict(list)
        self.trades = []
        
    def run(self):
        print("Starting Backtest...", flush=True)
        files = sorted(glob.glob(os.path.join(LOG_DIR, "market_data_*.csv")))
        target_files = [f for f in files if (START_DATE is None or f.split('-')[-1].replace('.csv', '') >= START_DATE) and (END_DATE is None or f.split('-')[-1].replace('.csv', '') <= END_DATE)]
        
        print(f"Loading {len(target_files)} files...", flush=True)
        all_data = []
        for f in target_files:
            try:
                df = pd.read_csv(f)
                df.columns = [c.strip() for c in df.columns]
                df['datetime'] = pd.to_datetime(df['timestamp'], format='mixed', dayfirst=True)
                all_data.append(df)
            except: pass
            
        if not all_data:
            print("No data found.", flush=True)
            return
            
        master_df = pd.concat(all_data, ignore_index=True)
        master_df.sort_values('datetime', inplace=True)
        print(f"Processing {len(master_df)} ticks...", flush=True)
        
        last_date = None
        
        last_prices = {}
        
        for idx, row in enumerate(master_df.itertuples(index=False)):
            current_time = row.datetime
            ticker = row.market_ticker.strip()
            
            # Track Last Prices
            yask = getattr(row, 'implied_yes_ask', np.nan)
            ybid = getattr(row, 'best_yes_bid', np.nan)
            if not pd.isna(yask) and not pd.isna(ybid):
                mid = (yask + ybid) / 2.0
                last_prices[ticker] = mid
            
            # Day End Logic
            curr_date = current_time.strftime("%y%b%d")
            if last_date != curr_date:
                if last_date:
                    # Calculate Equity
                    inventory_val = 0
                    for t, qty in self.inventory_yes.items():
                        mid = last_prices.get(t, 0) # Default to 0 if unknown (conservative)
                        inventory_val += qty * (mid / 100.0)
                    for t, qty in self.inventory_no.items():
                        mid = last_prices.get(t, 0)
                        inventory_val += qty * ((100 - mid) / 100.0)
                        
                    equity = self.wallet + inventory_val
                    print(f"[Day End {last_date}] Equity: ${equity:.2f} (Cash: ${self.wallet:.2f} | Inv: ${inventory_val:.2f})", flush=True)
                last_date = curr_date
            
            market_state = {
                'yes_ask': getattr(row, 'implied_yes_ask', np.nan),
                'no_ask': getattr(row, 'implied_no_ask', np.nan),
                'yes_bid': getattr(row, 'best_yes_bid', np.nan)
            }
            
            # Check Fills
            active = self.active_orders[ticker]
            still_active = []
            for o in active:
                if current_time >= o['expiry']: continue
                filled = False
                price = o['price']
                if o['action'] == 'BUY_YES':
                    if not pd.isna(market_state['yes_ask']) and market_state['yes_ask'] <= price: filled = True
                elif o['action'] == 'BUY_NO':
                    if not pd.isna(market_state['no_ask']) and market_state['no_ask'] <= price: filled = True
                    
                if filled:
                    cost = (o['qty'] * price / 100.0) + calculate_convex_fee(price, o['qty'])
                    if self.wallet >= cost:
                        self.wallet -= cost
                        if o['action'] == 'BUY_YES': self.inventory_yes[ticker] += o['qty']
                        else: self.inventory_no[ticker] += o['qty']
                        self.trades.append(o)
                    else: still_active.append(o)
                else: still_active.append(o)
            self.active_orders[ticker] = still_active
            
            # Run Strategy
            invs = {'YES': self.inventory_yes[ticker], 'NO': self.inventory_no[ticker]}
            new_orders = self.strategy.on_market_update(ticker, market_state, current_time, invs, self.active_orders[ticker], self.wallet, idx)
            if new_orders:
                self.active_orders[ticker] = new_orders
                
            # Liquidate at End (Simplified: Cash out at 0/100 or Mid)
            end_t = market_end_time_from_ticker(ticker)
            if end_t and current_time >= end_t:
                # Assume settlement at mid (or 0/100 if close)
                # For now, just clear inventory
                self.inventory_yes[ticker] = 0
                self.inventory_no[ticker] = 0
                self.active_orders[ticker] = []
                
        print(f"Final Cash: ${self.wallet:.2f}", flush=True)

if __name__ == "__main__":
    SimpleBacktester().run()
