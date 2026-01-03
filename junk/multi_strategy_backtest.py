import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import os
import glob
from datetime import datetime, timedelta
import sys
import math
import subprocess

# --- Configuration ---
LOG_DIR = os.path.join(os.getcwd(), "live_trading_system", "vm_logs", "market_logs")
CHARTS_DIR = "backtest_charts"
INITIAL_CAPITAL = 10.64 # Starting Cash (Dec 17 Morning)
TRADING_FEE_PER_CONTRACT = 0.02 # Fee per contract
TEST_ONLY_LIVE_STRATEGY = True # Speed Optimization: Test only the strategy used in Live Trading
TEST_ONLY_OG_FAST = True # Speed Optimization: Test only OG Fast (Simulated)
AUTO_SYNC_LOGS = False # Automatically download logs from VM before running
START_DATE = "26JAN01" # e.g. "25DEC10" or None for all
END_DATE = "26JAN01"   # e.g. "25DEC17" or None for all

# --- Wallet Class for Realistic Settlement ---
class Wallet:
    def __init__(self, initial_capital):
        self.available_cash = initial_capital
        self.unsettled_positions = [] # List of {'amount': float, 'settle_time': datetime}
        
    def get_total_equity(self):
        # Equity = Available Cash + Unsettled Cash
        unsettled_total = sum(p['amount'] for p in self.unsettled_positions)
        return self.available_cash + unsettled_total

    def check_settlements(self, current_time):
        # Release cash if settle_time <= current_time
        remaining_unsettled = []
        for p in self.unsettled_positions:
            if p['settle_time'] <= current_time:
                self.available_cash += p['amount']
            else:
                remaining_unsettled.append(p)
        self.unsettled_positions = remaining_unsettled

    def spend(self, amount):
        if amount > self.available_cash:
            return False
        self.available_cash -= amount
        return True

    def add_cash(self, amount):
        self.available_cash += amount

    def add_unsettled(self, amount, settle_time):
        self.unsettled_positions.append({'amount': amount, 'settle_time': settle_time})

# --- Strategies ---

class Strategy:
    def __init__(self, name, risk_pct=0.5, freshness_tolerance=None):
        self.name = name
        self.risk_pct = risk_pct
        self.freshness_tolerance = freshness_tolerance # None = Infinite, timedelta = Limit
        self.start_time = None
        self.active_orders = [] # Track active limit orders locally if needed
        
    def start_new_day(self, first_timestamp):
        self.start_time = first_timestamp
        self.active_orders = []
        
    def on_snapshot(self, market_snapshot, current_time, holdings, active_orders=None):
        """
        market_snapshot: dict {ticker: market_data_dict}
        current_time: datetime
        active_orders: list of dicts (orders currently sitting in the book)
        Returns: list of order dicts
        """
        return []
        
    def filter_fresh_markets(self, market_snapshot, current_time):
        """Helper to filter markets by freshness"""
        if self.freshness_tolerance is None:
            return market_snapshot
            
        fresh = {}
        for t, m in market_snapshot.items():
            if (current_time - m['timestamp']) <= self.freshness_tolerance:
                fresh[t] = m
        return fresh

    def on_day_end(self, daily_pnl):
        pass

class ParametricStrategy(Strategy):
    """
    A configurable strategy that waits for X time and then trades based on logic.
    """
    def __init__(self, name, wait_minutes, risk_pct, logic_type="trend_no", greedy=False, take_profit=None, freshness_tolerance=None, min_price=50, max_price=70):
        super().__init__(name, risk_pct, freshness_tolerance)
        self.wait_minutes = wait_minutes
        self.logic_type = logic_type
        self.greedy = greedy
        self.take_profit = take_profit # e.g. 95 (cents)
        self.min_price = min_price
        self.max_price = max_price
        
    def on_snapshot(self, snapshot, current_time, holdings):
        orders = []
        
        # 0. Check Auto-Sell (Take Profit)
        if self.take_profit is not None:
            for h in holdings:
                ticker = h['ticker']
                if ticker in snapshot:
                    market_data = snapshot[ticker]
                    yes_ask = market_data['yes_ask']
                    no_ask = market_data['no_ask']
                    
                    if h['side'] == 'no':
                        if not pd.isna(no_ask):
                            if not pd.isna(yes_ask):
                                no_val = 100 - yes_ask
                                if no_val >= self.take_profit:
                                    orders.append(("SELL_NO", ticker, 1.0))
                                    
                    elif h['side'] == 'yes':
                        if not pd.isna(yes_ask):
                            if yes_ask >= self.take_profit:
                                orders.append(("SELL_YES", ticker, 1.0))
        
        # 1. Wait Logic
        if self.start_time is None: return orders
        if current_time < (self.start_time + timedelta(minutes=self.wait_minutes)):
            return orders
            
        # FILTER FRESHNESS
        fresh_snapshot = self.filter_fresh_markets(snapshot, current_time)
            
        # 2. Trade Logic
        if self.logic_type == "trend_no":
            for ticker, market_data in fresh_snapshot.items():
                yes_ask = market_data['yes_ask']
                if pd.isna(yes_ask): continue
                
                market_price = yes_ask
                no_price = 100 - market_price
                
                if self.min_price < no_price < self.max_price:
                    orders.append(("BUY_NO", ticker, 1.0))
            
        return orders

class DiversifiedStrategy(Strategy):
    """
    Waits for start time, then identifies ALL valid markets (50-70 range).
    Splits the daily budget equally among them and executes trades.
    """
    def __init__(self, name, wait_minutes, risk_pct=0.5, freshness_tolerance=None):
        super().__init__(name, risk_pct, freshness_tolerance)
        self.wait_minutes = wait_minutes
        self.start_time = None
        self.has_traded_today = False

    def start_new_day(self, first_timestamp):
        self.start_time = first_timestamp
        self.has_traded_today = False

    def on_snapshot(self, snapshot, current_time, holdings):
        if self.has_traded_today: return []
        if self.start_time is None: return []
        if current_time < (self.start_time + timedelta(minutes=self.wait_minutes)):
            return []

        # 1. Get View of Markets (Fresh or Forward Filled)
        visible_markets = self.filter_fresh_markets(snapshot, current_time)
        
        # 2. Identify Candidates
        candidates = []
        for ticker, market_data in visible_markets.items():
            yes_ask = market_data['yes_ask']
            if pd.isna(yes_ask): continue
            no_price = 100 - yes_ask
            
            # Range Logic: 50 < Price < 70
            if 50 < no_price < 70:
                candidates.append(ticker)
        
        if not candidates:
            return []

        # 3. Generate Orders
        # Split budget equally: Weight = 1.0 / Count
        weight = 1.0 / len(candidates)
        orders = []
        for ticker in candidates:
            orders.append(("BUY_NO", ticker, weight))
            
        self.has_traded_today = True # Mark as done
        return orders

class BestValueStrategy(Strategy):
    """
    Scans ALL markets and picks the SINGLE BEST one based on criteria.
    """
    def __init__(self, name, criteria="cheapest", risk_pct=0.5, freshness_tolerance=None, wait_minutes=120):
        super().__init__(name, risk_pct, freshness_tolerance)
        self.criteria = criteria # "cheapest", "expensive", "median"
        self.wait_minutes = wait_minutes
        
    def on_snapshot(self, snapshot, current_time, holdings):
        orders = []
        
        # 1. Wait Logic
        if self.start_time is None: return orders
        if current_time < (self.start_time + timedelta(minutes=self.wait_minutes)):
            return orders
            
        candidates = []
        
        fresh_snapshot = self.filter_fresh_markets(snapshot, current_time)
        
        for ticker, market_data in fresh_snapshot.items():
            yes_ask = market_data['yes_ask']
            if pd.isna(yes_ask): continue
            market_price = yes_ask
            no_price = 100 - market_price
            
            if 50 < no_price < 70:
                candidates.append((ticker, no_price))
                
        if not candidates: return []
        
        # Sort based on criteria
        if self.criteria == "cheapest":
            candidates.sort(key=lambda x: x[1]) # Ascending price
            best = candidates[0]
        elif self.criteria == "expensive":
            candidates.sort(key=lambda x: x[1], reverse=True) # Descending price
            best = candidates[0]
        elif self.criteria == "median":
            candidates.sort(key=lambda x: x[1])
            mid = len(candidates) // 2
            best = candidates[mid]
        else:
            return []
            
        return [("BUY_NO", best[0], 1.0)]

class RankedSplitStrategy(Strategy):
    """
    Identifies top N markets based on sorting criteria (e.g. Cheapest NO, Expensive NO).
    Splits budget equally among them.
    """
    def __init__(self, name, wait_minutes, sort_key='no_ask', ascending=True, top_n=3, trade_action='BUY_NO', risk_pct=0.5, freshness_tolerance=None, min_price=None, max_price=None):
        super().__init__(name, risk_pct, freshness_tolerance)
        self.wait_minutes = wait_minutes
        self.sort_key = sort_key # 'no_ask' or 'yes_ask'
        self.ascending = ascending # True = Cheapest, False = Expensive
        self.top_n = top_n
        self.trade_action = trade_action # 'BUY_NO' or 'BUY_YES'
        self.min_price = min_price
        self.max_price = max_price
        self.start_time = None
        self.has_traded_today = False

    def start_new_day(self, first_timestamp):
        self.start_time = first_timestamp
        self.has_traded_today = False

    def on_snapshot(self, snapshot, current_time, holdings):
        if self.has_traded_today: return []
        if self.start_time is None: return []
        if current_time < (self.start_time + timedelta(minutes=self.wait_minutes)):
            return []

        # 1. Get View of Markets
        visible_markets = self.filter_fresh_markets(snapshot, current_time)
        
        # 2. Identify Candidates
        candidates = []
        for ticker, market_data in visible_markets.items():
            val = market_data.get(self.sort_key)
            if pd.isna(val): continue
            
            # Price Filter
            if self.min_price is not None and val < self.min_price: continue
            if self.max_price is not None and val > self.max_price: continue
            
            candidates.append((ticker, val))
        
        if not candidates: return []

        # 3. Sort
        candidates.sort(key=lambda x: x[1], reverse=not self.ascending)
        
        # 4. Pick Top N
        top_candidates = candidates[:self.top_n]
        
        if not top_candidates: return []

        # 5. Generate Orders
        weight = 1.0 / len(top_candidates)
        orders = []
        for ticker, val in top_candidates:
            orders.append((self.trade_action, ticker, weight))
            
        self.has_traded_today = True
        return orders

class MomentumStrategy(Strategy):
    """
    Tracks price history and buys NO if YES price drops significantly (trend following).
    """
    def __init__(self, name, drop_threshold=10, lookback_minutes=60, risk_pct=0.5, freshness_tolerance=None):
        super().__init__(name, risk_pct, freshness_tolerance)
        self.drop_threshold = drop_threshold
        self.lookback_minutes = lookback_minutes
        self.price_history = {} # {ticker: [(time, yes_price)]}
        self.has_traded_today = {} # {ticker: bool}
        
    def start_new_day(self, first_timestamp):
        self.price_history = {}
        self.has_traded_today = {}
        
    def on_snapshot(self, snapshot, current_time, holdings):
        orders = []
        
        # 1. Update History
        for ticker, m in snapshot.items():
            yes_ask = m.get('yes_ask')
            if pd.isna(yes_ask): continue
            
            if ticker not in self.price_history:
                self.price_history[ticker] = []
            
            self.price_history[ticker].append((current_time, yes_ask))
            
            # Prune old history
            cutoff = current_time - timedelta(minutes=self.lookback_minutes)
            self.price_history[ticker] = [x for x in self.price_history[ticker] if x[0] >= cutoff]
            
        # 2. Check for Momentum
        for ticker, history in self.price_history.items():
            if self.has_traded_today.get(ticker, False): continue
            if not history: continue
            
            current_price = history[-1][1]
            # Find price ~60 mins ago (or oldest available if < 60 mins but > 30 mins?)
            # Let's just compare with oldest in window
            oldest_price = history[0][1]
            oldest_time = history[0][0]
            
            # Ensure we have enough history (at least 30 mins) to call it a trend
            if (current_time - oldest_time).total_seconds() < 1800: continue
            
            price_drop = oldest_price - current_price
            
            if price_drop >= self.drop_threshold:
                # Trend is DOWN for YES -> Buy NO
                # Check if price is still reasonable (e.g. not already 0)
                if current_price > 5: 
                    orders.append(("BUY_NO", ticker, 1.0)) # Full bet? Or split? 
                    # Strategy class doesn't handle sizing well if multiple trigger at once.
                    # But execute_trade handles budget.
                    self.has_traded_today[ticker] = True
                    
        return orders

# --- Helper Functions ---

def get_market_details(ticker):
    try:
        parts = ticker.split('-')
        suffix = parts[-1]
        type_char = suffix[0]
        val = float(suffix[1:])
        if type_char == 'T': return {'strike_type': 'greater', 'floor_strike': val, 'cap_strike': None}
        else: return {'strike_type': 'less', 'floor_strike': None, 'cap_strike': val}
    except:
        return {}

def sanitize_data(df):
    """
    Forces EOD prices to 0 or 100 if they end near those values.
    Vectorized for performance.
    """
    # 0. Filter out corrupted lines (Empty Book Artifacts: 0,0,100,100)
    if 'implied_yes_ask' in df.columns and 'implied_no_ask' in df.columns:
        mask_corrupt = (df['implied_yes_ask'] > 99) & (df['implied_no_ask'] > 99)
        if mask_corrupt.any():
            df = df[~mask_corrupt]
            
    if df.empty: return df

    # 1. Get the last row for each ticker
    last_rows = df.drop_duplicates('market_ticker', keep='last').copy()
    
    # 2. Identify tickers that need sanitization
    mask_high = last_rows['implied_no_ask'] > 95
    mask_low = last_rows['implied_no_ask'] < 5
    
    rows_to_add = []
    
    last_timestamp = df['timestamp'].iloc[-1]
    
    if mask_high.any():
        high_rows = last_rows[mask_high].copy()
        high_rows['timestamp'] = last_timestamp
        high_rows['implied_yes_ask'] = 0
        high_rows['implied_no_ask'] = 100
        rows_to_add.append(high_rows)
        
    if mask_low.any():
        low_rows = last_rows[mask_low].copy()
        low_rows['timestamp'] = last_timestamp
        low_rows['implied_yes_ask'] = 100
        low_rows['implied_no_ask'] = 0
        rows_to_add.append(low_rows)
        
    if rows_to_add:
        sanitized_df = pd.concat(rows_to_add, ignore_index=True)
        df = pd.concat([df, sanitized_df], ignore_index=True)
        df = df.sort_values('timestamp')
        
    return df

# --- Main Backtester Class ---

# --- Strategy 2.5 Implementation ---

class InventoryAwareMarketMaker(Strategy):
    """
    Algorithm 1: Inventory-Aware Spread-Farming Market Maker
    Quotes inside the spread around an EMA fair price, managing inventory risk.
    """
    def __init__(self, name, risk_pct=0.5, max_inventory=5000, inventory_penalty=0.01, window=20, max_offset=2):
        super().__init__(name, risk_pct, freshness_tolerance=None)
        self.max_inventory = max_inventory
        self.inventory_penalty = inventory_penalty # per contract
        self.window = window
        self.max_offset = max_offset
        self.fair_price = None # EMA
        self.alpha = 2 / (window + 1)
        
    def on_snapshot(self, snapshot, current_time, holdings, active_orders=None):
        orders = []
        
        
        # Calculate current inventory (Net YES)
        net_inventory = 0
        for h in holdings:
            if h['side'] == 'yes': net_inventory += h['qty']
            else: net_inventory -= h['qty'] # Short YES = Long NO
            
        tick_expiry = current_time + timedelta(seconds=10) # 10s expiry for quotes
        
        for ticker, m in snapshot.items():
            # 1. Update EMA
            yes_ask = m.get('yes_ask') # Sellers
            no_ask = m.get('no_ask')
            
            if pd.isna(yes_ask): 
                continue
            
            # Use Mid Price
            if pd.isna(no_ask):
                 continue
                 
            best_bid = 100 - no_ask
            mid = (best_bid + yes_ask) / 2.0
            
            if self.fair_price is None:
                self.fair_price = mid
            else:
                self.fair_price = self.alpha * mid + (1 - self.alpha) * self.fair_price
                
            # 2. Check Inventory Limits
            can_buy_yes = net_inventory < self.max_inventory
            can_sell_yes = net_inventory > -self.max_inventory
            
            # 3. Calculate Quotes (AGGRESSIVE LIMIT LOGIC - Matching v5)
            # Instead of quoting inside spread, we check for EDGE and pay the spread if it exists.
            
            # Fair Price (EMA)
            fair_prob = self.fair_price / 100.0
            
            # Execution Prices (Aggressive: Ask + 1)
            exec_yes = min(99, yes_ask + 1)
            exec_no = min(99, no_ask + 1)
            
            # Edge Calculation
            edge_yes = fair_prob - (exec_yes / 100.0)
            edge_no = (1.0 - fair_prob) - (exec_no / 100.0)
            
            # Fee Buffer (approx 2c round trip)
            required_edge = 0.02 
            
            qty = 10 # Fixed size for sim
            
            # 4. Generate Orders (Aggressive Limit -> Immediate Fill Assumption)
            
            if can_buy_yes and edge_yes > required_edge:
                 orders.append({
                     'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 
                     'type': 'LIMIT', 'price': exec_yes, 'expiry': tick_expiry
                 })
            
            if can_sell_yes and edge_no > required_edge: # Buy NO
                 orders.append({
                     'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 
                     'type': 'LIMIT', 'price': exec_no, 'expiry': tick_expiry
                 })
                 
        return orders

class MicroScalper(Strategy):
    """
    Algorithm 2: Micro Mean-Reversion Scalper (Limit-Only)
    Exploits short-term bounces.
    """
    def __init__(self, name, threshold=1.5, risk_pct=0.5):
        super().__init__(name, risk_pct, freshness_tolerance=None)
        self.threshold = threshold
        self.last_mids = {} # {ticker: mid_price}
        
    def on_snapshot(self, snapshot, current_time, holdings, active_orders=None):
        orders = []
        
        for ticker, m in snapshot.items():
            yes_ask = m.get('yes_ask')
            no_ask = m.get('no_ask')
            if pd.isna(yes_ask) or pd.isna(no_ask): continue
            
            best_bid = 100 - no_ask
            mid = (best_bid + yes_ask) / 2.0
            
            last_mid = self.last_mids.get(ticker)
            self.last_mids[ticker] = mid # Update for next tick
            
            if last_mid is None: continue
            
            delta = mid - last_mid
            
            # Mean Reversion Logic
            tick_expiry = current_time + timedelta(seconds=30)
            qty = 5
            
            # If price spiked UP (Positive Delta) -> Expect Down -> Short YES (Buy NO)
            if delta >= self.threshold:
                # Place Limit Offer at Ask (Passive entry?)
                # "Trigger: Place YES ask at implied_yes_ask"
                # YES Ask = Bound by sellers. If we place at implied_yes_ask, we join the queue.
                # Equivalent: Buy NO at (100 - implied_yes_ask).
                limit_price = 100 - yes_ask
                orders.append({
                     'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 
                     'type': 'LIMIT', 'price': int(limit_price), 'expiry': tick_expiry
                })
                
            # If price crashed DOWN (Negative Delta) -> Expect Up -> Long YES
            elif delta <= -self.threshold:
                # Place Limit Bid at Bed
                # YES Bid = best_bid.
                limit_price = best_bid
                orders.append({
                     'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 
                     'type': 'LIMIT', 'price': int(limit_price), 'expiry': tick_expiry
                })
                
        return orders

class RegimeSwitcher(Strategy):
    """
    Algorithm 3: Meta-Controller
    Gates strategies based on time-of-day.
    """
    def __init__(self, name, risk_pct=0.5):
        super().__init__(name, risk_pct, freshness_tolerance=None)
        self.maker = InventoryAwareMarketMaker("Maker_Sub", risk_pct)
        self.scalper = MicroScalper("Scalper_Sub", risk_pct)
        
    def start_new_day(self, first_timestamp):
        self.start_time = first_timestamp
        self.maker.start_new_day(first_timestamp)
        self.scalper.start_new_day(first_timestamp)
        
    def on_snapshot(self, snapshot, current_time, holdings, active_orders=None):
        # Time-of-Day Logic
        # MAKER_FAVORABLE: 10AM - 3PM
        hour = current_time.hour
        
        is_maker_favorable = (10 <= hour < 15)
        # NEUTRAL: 9AM-10AM, 3PM-4PM
        is_neutral = (9 <= hour < 10) or (15 <= hour < 16)
        
        orders = []
        
        if is_maker_favorable:
            # Aggressive
            orders.extend(self.maker.on_snapshot(snapshot, current_time, holdings, active_orders))
            orders.extend(self.scalper.on_snapshot(snapshot, current_time, holdings, active_orders))
            
        elif is_neutral:
            # Conservative (Only Maker, wider?)
            # For sim, just run Maker, no Scalper
            orders.extend(self.maker.on_snapshot(snapshot, current_time, holdings, active_orders))
            
        # NO_TRADE: Outside hours (e.g. 4PM+, pre-9AM) -> Empty orders
        
        return orders

class HumanReadableBacktester:
    def __init__(self):
        self.strategies = []
        
        # --- GENERATE STRATEGIES ---
        
        # 0. Live Clone (Exact) - Matches trader.py
        self.strategies.append(ParametricStrategy(
            "Live Clone (Exact)", 
            wait_minutes=0, 
            risk_pct=0.5, 
            logic_type="trend_no", 
            freshness_tolerance=None,
            min_price=50,
            max_price=75
        ))

        # 1. Live Strategy v3 (Production) - Strict 1s Freshness
        self.strategies.append(ParametricStrategy(
            "Live Strategy v3", 
            wait_minutes=120, 
            risk_pct=0.5, 
            logic_type="trend_no", 
            freshness_tolerance=timedelta(seconds=1)
        ))
        
        # 2. Unfiltered (Ghost Chaser) - No Freshness Limit
        self.strategies.append(ParametricStrategy(
            "Unfiltered (Ghost Chaser)", 
            wait_minutes=120, 
            risk_pct=0.5, 
            logic_type="trend_no", 
            freshness_tolerance=None
        ))
        
        # 3. Sniper (Cheapest) - UNFILTERED (Forward Fill)
        self.strategies.append(BestValueStrategy(
            "Sniper: Cheapest", 
            criteria="cheapest", 
            risk_pct=0.5, 
            freshness_tolerance=None, # User requested Forward Fill for Snipers
            wait_minutes=120
        ))
        
        # 4. Sniper (Expensive) - UNFILTERED (Forward Fill)
        self.strategies.append(BestValueStrategy(
            "Sniper: Expensive", 
            criteria="expensive", 
            risk_pct=0.5, 
            freshness_tolerance=None, # User requested Forward Fill for Snipers
            wait_minutes=120
        ))
        
        # 5. Diversified (Split) - UNFILTERED (Forward Fill)
        self.strategies.append(DiversifiedStrategy(
            "Diversified (Split)", 
            wait_minutes=120, 
            risk_pct=0.5, 
            freshness_tolerance=None # Forward Fill to see ALL markets
        ))

        # 6. Split Cheapest 3 (NO) - True Longshots Only (<20c)
        self.strategies.append(RankedSplitStrategy(
            "Split Cheapest 3 (NO)",
            wait_minutes=120,
            sort_key='no_ask',
            ascending=True,
            top_n=3,
            trade_action='BUY_NO',
            risk_pct=0.5,
            freshness_tolerance=None
            # max_price removed per user request
        ))

        # 7. Contrarian YES (Longshot) - Buy YES if < 20c (NO > 80c)
        self.strategies.append(RankedSplitStrategy(
            "Contrarian YES (Longshot)",
            wait_minutes=120,
            sort_key='yes_ask',
            ascending=True, # Cheapest YES
            top_n=3,
            trade_action='BUY_YES',
            risk_pct=0.5,
            freshness_tolerance=None
            # max_price removed per user request
        ))

        # 8. Split Exp NO -> Buy YES (Unchanged)
        self.strategies.append(RankedSplitStrategy(
            "Split Exp NO -> Buy YES",
            wait_minutes=120,
            sort_key='no_ask',
            ascending=False, # Expensive NO
            top_n=3,
            trade_action='BUY_YES',
            risk_pct=0.5,
            freshness_tolerance=None
        ))

        # 9. Split Cheapest 3 NO -> Buy YES (Hedge)
        self.strategies.append(RankedSplitStrategy(
            "Split Cheap NO -> Buy YES",
            wait_minutes=120,
            sort_key='no_ask',
            ascending=True, # Cheapest NO
            top_n=3,
            trade_action='BUY_YES',
            risk_pct=0.5,
            freshness_tolerance=None
        ))

        # 10. The Sniper (High Prob) - Wait for 12:00 PM, Buy NO > 90c
        self.strategies.append(RankedSplitStrategy(
            "The Sniper (High Prob)",
            wait_minutes=180, # 9:00 AM + 180 mins = 12:00 PM
            sort_key='no_ask',
            ascending=True, # Cheapest NO (that is > 90)
            top_n=1, # Go all in on the best one
            trade_action='BUY_NO',
            risk_pct=0.5,
            freshness_tolerance=None,
            min_price=90
        ))

        # 11. The Smart Portfolio (Variance Reduction) - Buy NO < 80c, Split across all
        self.strategies.append(RankedSplitStrategy(
            "The Smart Portfolio",
            wait_minutes=120,
            sort_key='no_ask',
            ascending=True,
            top_n=999, # Buy ALL that match criteria
            trade_action='BUY_NO',
            risk_pct=0.5,
            freshness_tolerance=None,
            max_price=80
        ))

        # 12. The Momentum Surfer (Trend Following)
        self.strategies.append(MomentumStrategy(
            "The Momentum Surfer",
            drop_threshold=10,
            lookback_minutes=60,
            risk_pct=0.5,
            freshness_tolerance=None
        ))

        # --- Strategy 2.5 (New) ---
        # Balanced Calibration
        self.strategies.append(InventoryAwareMarketMaker("Algo 1: Inventory MM", risk_pct=0.5, max_offset=2, window=20)) 
        self.strategies.append(MicroScalper("Algo 2: Micro Scalper", risk_pct=0.5, threshold=0.5))
        self.strategies.append(RegimeSwitcher("Algo 3: Regime Switcher", risk_pct=0.5))

        print(f"Generated {len(self.strategies)} strategies.")

        # --- Execution Flags ---
        TEST_STRATEGY_2_5_ONLY = True

        if TEST_STRATEGY_2_5_ONLY:
             print("[Strategy 2.5] Running Strategy 2.5 Algos ONLY")
             cols = ["Algo 1: Inventory MM", "Algo 2: Micro Scalper", "Algo 3: Regime Switcher"]
             self.strategies = [s for s in self.strategies if s.name in cols]
        elif TEST_ONLY_OG_FAST:
            print("⚠️  TEST_ONLY_OG_FAST is ON. Running ONLY 'Live Strategy v3'")
            self.strategies = [s for s in self.strategies if s.name == "Live Strategy v3"]

        # Initialize Portfolios with Wallets
        self.portfolios = {}
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(INITIAL_CAPITAL), # New Wallet
                'cash': INITIAL_CAPITAL,
                'holdings': [],
                'trades': [],
                'daily_start_cash': INITIAL_CAPITAL,
                'daily_start_cash': INITIAL_CAPITAL,
                'spent_today': 0.0,
                'active_limit_orders': []
            }
        
        if not os.path.exists(CHARTS_DIR): os.makedirs(CHARTS_DIR)
        
        self.performance_history = [] # List of {date: str, strategy_name: equity, ...}

    def check_limit_fills(self, portfolio, snapshot, timestamp, daily_trades_viz, strategy_name):
        """
        Checks active limit orders against current market snapshot for fills.
        """
        active_orders = portfolio['active_limit_orders']
        still_active = []
        
        for order in active_orders:
            ticker = order['ticker']
            if ticker not in snapshot:
                still_active.append(order)
                continue
                
            market = snapshot[ticker]
            # Market Prices (Seller asks)
            yes_ask = market.get('yes_ask')
            no_ask = market.get('no_ask')
            
            if pd.isna(yes_ask) or pd.isna(no_ask):
                still_active.append(order)
                continue
            
            # Derived Bid Prices (Buyer bids) - approximate as 100 - Ask of other side
            # This is "Best Market Bid"
            yes_bid = 100 - no_ask
            no_bid = 100 - yes_ask
            
            filled = False
            fill_price = 0.0
            
            limit_price = order['price']
            qty = order['qty']
            action = order['action'] # BUY_YES, SELL_NO etc
            
            # --- MATCHING LOGIC ---
            # BUY LIMIT: Fills if Market Ask <= Limit Price (Seller met me)
            # SELL LIMIT: Fills if Market Bid >= Limit Price (Buyer met me)
            
            if action == 'BUY_YES':
                if yes_ask <= limit_price:
                    filled = True
                    fill_price = limit_price # Limit guarantees price (or better, but simplifiy to limit)
            elif action == 'BUY_NO':
                if no_ask <= limit_price:
                    filled = True
                    fill_price = limit_price
            elif action == 'SELL_YES':
                if yes_bid >= limit_price:
                    filled = True
                    fill_price = limit_price
            elif action == 'SELL_NO':
                if no_bid >= limit_price:
                    filled = True
                    fill_price = limit_price
                    
            if filled:
                # EXECUTE TRADE
                # Note: Inventory/Cash checks should have been done at order creation? 
                # Or do we reserve cash?
                # For simplicity, we assume cash was reserved or we check now.
                # Let's check now to be safe, if buying.
                
                is_buy = 'BUY' in action
                cost = 0
                proceeds = 0
                
                if is_buy:
                    price_per = fill_price / 100.0
                    total_cost = (qty * price_per) + self.calculate_fee(fill_price, qty)
                    
                    if portfolio['wallet'].spend(total_cost):
                        portfolio['cash'] = portfolio['wallet'].available_cash
                        portfolio['spent_today'] += total_cost
                        side = 'yes' if 'YES' in action else 'no'
                        portfolio['holdings'].append({
                            'ticker': ticker, 'side': side, 'qty': qty, 'price': fill_price, 'cost': total_cost
                        })
                        
                        portfolio['trades'].append({
                            'time': timestamp, 'action': action, 'ticker': ticker, 'price': fill_price, 'qty': qty, 'cost': total_cost,
                            'capital_after': portfolio['wallet'].get_total_equity(),
                            'type': 'LIMIT_FILL'
                        })
                        
                        # Viz
                        viz_y = no_ask if pd.notna(no_ask) else fill_price 
                        daily_trades_viz.append({
                            'time': timestamp, 'strategy': strategy_name, 'action': action, 'ticker': ticker,
                            'price': fill_price, 'qty': qty, 'cost': total_cost, 'viz_y': viz_y
                        })
                    else:
                        # Cancelled due to lack of funds? Or keep trying?
                        # Keep trying strictly.
                        still_active.append(order)
                        
                else: # SELL
                    # Verify holding exists (it should, unless we sold it elsewhere? Strategies managing same ticker?)
                    # Simplified: Assume we have it if order exists.
                    side = 'yes' if 'YES' in action else 'no'
                    holding_to_sell = None
                    for h in portfolio['holdings']:
                        if h['ticker'] == ticker and h['side'] == side:
                            holding_to_sell = h
                            break
                    
                    if holding_to_sell:
                        price_per = fill_price / 100.0
                        proceeds = qty * price_per
                        portfolio['holdings'].remove(holding_to_sell)
                        portfolio['wallet'].add_cash(proceeds)
                        portfolio['cash'] = portfolio['wallet'].available_cash
                        
                        portfolio['trades'].append({
                            'time': timestamp, 'action': action, 'ticker': ticker, 'price': fill_price, 'qty': qty, 'cost': 0, 'proceeds': proceeds,
                            'capital_after': portfolio['wallet'].get_total_equity(),
                            'pnl': proceeds - holding_to_sell['cost'],
                            'exit_price': fill_price,
                            'type': 'LIMIT_FILL'
                        })
                        daily_trades_viz.append({
                            'time': timestamp, 'strategy': strategy_name, 'action': action, 'ticker': ticker,
                            'price': fill_price, 'qty': qty, 'cost': 0, 'pnl': proceeds - holding_to_sell['cost']
                        })
                    else:
                        # Holding gone? Cancel order.
                        pass 

            else:
                # Check expiry/Time-in-force?
                if 'expiry' in order and timestamp >= order['expiry']:
                    pass # Expire
                else:
                    still_active.append(order)
                    
        portfolio['active_limit_orders'] = still_active

    def run(self):
        print("=== Starting Parametric Backtest ===")

        if AUTO_SYNC_LOGS:
            print("🔄 Auto-Sync: Checking for new logs from VM...")
            try:
                # Dynamically find the script relative to this file
                sync_script = os.path.join(os.path.dirname(__file__), "live_trading_system", "sync_vm_logs.py")
                if os.path.exists(sync_script):
                    subprocess.run(["python", sync_script], check=True)
            except Exception as e:
                print(f"⚠️ Warning: Auto-Sync failed: {e}")
        


        
        files = sorted(glob.glob(os.path.join(LOG_DIR, "market_data_*.csv")))
        if not files:
            print("No log files found!")
            return
            
        recent_files = []
        for f in files:
            # Extract date part: market_data_KXHIGHNY-25DEC17.csv -> 25DEC17
            date_str = f.split('-')[-1].replace('.csv', '')
            
            # Filter Logic
            if START_DATE and date_str < START_DATE:
                continue
            if END_DATE and date_str > END_DATE:
                continue
                
            recent_files.append(f)
        
        print(f"Processing {len(recent_files)} days of data...")

        for csv_file in recent_files:
            self.process_day(csv_file)

        self.generate_report()
        self.generate_performance_chart()
        
        all_trades = []
        for name, p in self.portfolios.items():
            for t in p['trades']:
                t['strategy'] = name
                all_trades.append(t)
        
        if all_trades:
            pd.DataFrame(all_trades).to_csv("debug_trades.csv", index=False)
            print("Saved trades to debug_trades.csv")
            
        print("=== Backtest Complete ===")

    def process_day(self, csv_file):
        date_str = os.path.basename(csv_file).split('-')[-1].replace('.csv', '')
        print(f"Processing {date_str}...", end='\r')
        
        try:
            df = pd.read_csv(csv_file, on_bad_lines='skip')
        except:
            return

        if df.empty: return

        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
        df = df.sort_values('timestamp')
        
        # Forward Fill prices to ensure "Last Known Value" is available
        # This fixes the issue where a tick only updates YES but we need the NO price for visualization
        df[['implied_yes_ask', 'implied_no_ask', 'best_yes_bid', 'best_no_bid']] = df.groupby('market_ticker')[['implied_yes_ask', 'implied_no_ask', 'best_yes_bid', 'best_no_bid']].ffill()
        
        # --- FIX DATA INVERSION (CONDITIONAL) ---
        # The CSV logs have YES and NO columns swapped ONLY for 25DEC17.
        # We swap them back here to match reality.
        # --- FIX DATA INVERSION (CONDITIONAL) ---
        # The CSV logs have YES and NO columns swapped ONLY for 25DEC17.
        # We swap them back here to match reality.
        if "25DEC17" in csv_file:
            # Using direct assignment to be safe
            temp_yes = df['implied_yes_ask'].copy()
            df['implied_yes_ask'] = df['implied_no_ask']
            df['implied_no_ask'] = temp_yes
            
            temp_bid = df['best_yes_bid'].copy()
            df['best_yes_bid'] = df['best_no_bid']
            df['best_no_bid'] = temp_bid
            print(f"⚠️  Applied Data Inversion Fix for {csv_file}")
        # --------------------------
        # --------------------------
        # --------------------------

        df = sanitize_data(df)
        
        first_timestamp = df['timestamp'].iloc[0]
        for s in self.strategies:
            s.start_new_day(first_timestamp)
            self.portfolios[s.name]['spent_today'] = 0.0 
            self.portfolios[s.name]['cash'] = self.portfolios[s.name]['wallet'].available_cash
            self.portfolios[s.name]['daily_start_cash'] = self.portfolios[s.name]['wallet'].get_total_equity()
        
        daily_trades_viz = []
        market_state = {}
        
        records = df.to_dict('records')
        total_rows = len(records)
        print_interval = max(1, total_rows // 10)
        
        print(f"Processing {date_str}: 0% ({total_rows} ticks)...", end='\r')
        
        for i, row in enumerate(records):
            if i % print_interval == 0:
                print(f"Processing {date_str}: {int(i/total_rows*100)}% ({i}/{total_rows})", end='\r')
                
            ticker = row['market_ticker']
            
            # Initialize if not exists
            if ticker not in market_state:
                market_state[ticker] = {
                    'yes_ask': None, 'no_ask': None,
                    'yes_bid': None, 'no_bid': None,
                    'market_ticker': ticker,
                    'timestamp': row['timestamp']
                }
            
            # Update fields if present (and not NaN)
            if pd.notna(row.get('implied_yes_ask')): market_state[ticker]['yes_ask'] = row['implied_yes_ask']
            if pd.notna(row.get('implied_no_ask')): market_state[ticker]['no_ask'] = row['implied_no_ask']
            if pd.notna(row.get('best_yes_bid')): market_state[ticker]['yes_bid'] = row['best_yes_bid']
            if pd.notna(row.get('best_no_bid')): market_state[ticker]['no_bid'] = row['best_no_bid']
            market_state[ticker]['timestamp'] = row['timestamp']
            current_time = row['timestamp']
            
            # Unified Strategy Loop
            for s in self.strategies:
                portfolio = self.portfolios[s.name]
                wallet = portfolio['wallet']
                
                # 1. Check Settlement (Cash clearing)
                wallet.check_settlements(current_time)
                portfolio['cash'] = wallet.available_cash
                
                # 2. Check Limit Fills (NEW)
                self.check_limit_fills(portfolio, market_state, current_time, daily_trades_viz, s.name)

                # 3. Strategy Logic
                orders = s.on_snapshot(market_state, current_time, portfolio['holdings'], active_orders=portfolio.get('active_limit_orders', []))
                
                if not orders: continue
                
                for order in orders:
                     # Legacy Tuple: (Action, Ticker, Weight)
                     if isinstance(order, tuple):
                         action, t_ticker, weight = order
                         if t_ticker in market_state:
                             m_data = market_state[t_ticker]
                             # Use existing execute_trade signature? Wait, the file view showed:
                             # self.execute_trade(strat, action, ticker, m_data['yes_ask'], m_data['no_ask'], current_time, daily_trades_viz, weight)
                             # But `strat` variable name in loop is `s`.
                             # And keys are 'implied_yes_ask' etc.
                             # Actually, let's look at the old code in view_file:
                             # self.execute_trade(strat, action, ticker, m_data['yes_ask'], m_data['no_ask']...)
                             # But m_data was set with 'implied_yes_ask'. Wait, let me check execute_trade signature later.
                             # For now, I will use exactly what was there, just adapted for the new loop structure.
                             # Actually, the old code used `strat` (loop var) and `market_state[ticker]`.
                             self.execute_trade(s, action, t_ticker, m_data['implied_yes_ask'], m_data['implied_no_ask'], current_time, daily_trades_viz, weight)
                     
                     # New Dict Format (Limit Orders)
                     elif isinstance(order, dict):
                         o_type = order.get('type', 'MARKET')
                         if o_type == 'LIMIT':
                             if order['qty'] > 0:
                                 portfolio['active_limit_orders'].append(order)
            
            # DEBUG: Check price of 25DEC18 on Dec 17 at 14:00
            if "25DEC18" in ticker and str(current_time).startswith("2025-12-17 14:00"):
                 print(f"DEBUG: {current_time} {ticker} YesAsk={market_state[ticker].get('yes_ask')} NoAsk={market_state[ticker].get('no_ask')}")
                    
        print(f"Processing {date_str}: 100% ({total_rows}/{total_rows})")

        self.settle_eod(df, daily_trades_viz)
        
        for name, p in self.portfolios.items():
            end_equity = p['wallet'].get_total_equity()
            daily_pnl = end_equity - p['daily_start_cash']
            strat_obj = next((s for s in self.strategies if s.name == name), None)
            if strat_obj:
                strat_obj.on_day_end(daily_pnl)
            if "Safe Baseline" in name:
                print(f"  [Daily PnL] {date_str}: ${daily_pnl:.2f} (End Equity: ${end_equity:.2f})")
        
        # Record Daily Performance
        day_record = {'date': date_str}
        for name, p in self.portfolios.items():
            day_record[name] = p['wallet'].get_total_equity()
        self.performance_history.append(day_record)
        
        key_strategies = [s.name for s in self.strategies]
        
        daily_report = {}
        for name, p in self.portfolios.items():
            if name in key_strategies:
                wallet = p['wallet']
                equity = wallet.get_total_equity()
                liquid = wallet.available_cash
                invested = equity - liquid
                daily_report[name] = {
                    'start': p['daily_start_cash'], 
                    'end': equity,
                    'liquid': liquid,
                    'invested': invested
                }
                        
        self.generate_daily_chart(df, daily_trades_viz, daily_report, date_str, key_strategies)
        
    def calculate_fee(self, price, qty):
        p_decimal = price / 100.0
        raw_fee = 0.07 * qty * p_decimal * (1 - p_decimal)
        fee = math.ceil(raw_fee * 100) / 100.0
        return fee

    def execute_trade(self, strategy, action, ticker, yes_ask, no_ask, timestamp, daily_trades_viz, weight=1.0):
        portfolio = self.portfolios[strategy.name]
        wallet = portfolio['wallet']
        
        if action == "BUY_YES":
            if pd.isna(yes_ask): return
            price = yes_ask
            side = 'yes'
            is_sell = False
        elif action == "BUY_NO":
            if pd.isna(no_ask): return
            price = no_ask
            side = 'no'
            is_sell = False
        elif action == "SELL_YES":
            if pd.isna(yes_ask): return
            price = max(0, yes_ask - 2) 
            side = 'yes'
            is_sell = True
        elif action == "SELL_NO":
            if pd.isna(no_ask): return
            price = max(0, no_ask - 2)
            side = 'no'
            is_sell = True
        else:
            return

        if is_sell:
            holding_to_sell = None
            for i, h in enumerate(portfolio['holdings']):
                if h['ticker'] == ticker and h['side'] == side:
                    holding_to_sell = h
                    break
            
            if holding_to_sell:
                qty = holding_to_sell['qty']
                proceeds = qty * (price / 100.0)
                portfolio['holdings'].remove(holding_to_sell)
                wallet.add_cash(proceeds)
                portfolio['cash'] = wallet.available_cash
                portfolio['trades'].append({
                    'time': timestamp, 'action': action, 'ticker': ticker, 'price': price, 'qty': qty, 'cost': 0, 'proceeds': proceeds,
                    'capital_after': wallet.get_total_equity(),
                    'pnl': proceeds - holding_to_sell['cost'],
                    'exit_price': price
                })
                daily_trades_viz.append({
                    'time': timestamp, 'strategy': strategy.name, 'action': action, 'ticker': ticker,
                    'price': price, 'qty': qty, 'cost': 0, 'pnl': proceeds - holding_to_sell['cost']
                })
            return

        for h in portfolio['holdings']:
            if h['ticker'] == ticker:
                return

        total_equity = wallet.get_total_equity()
        available_cash = wallet.available_cash
        daily_budget = total_equity * strategy.risk_pct
        target_spend_for_trade = daily_budget * weight
        spent_so_far = portfolio['spent_today']
        
        if getattr(strategy, 'greedy', False):
            max_spend = min(target_spend_for_trade, available_cash)
        else:
            if spent_so_far >= daily_budget:
                return
            available_global = daily_budget - spent_so_far
            max_spend = min(target_spend_for_trade, available_global, available_cash)
        
        # REMOVED: if max_spend < 1.0: return
        
        price_per_contract = price / 100.0
        safe_cost_per_contract = price_per_contract + 0.02
        qty = int(max_spend // safe_cost_per_contract)
        
        if qty <= 0: return

        fee = self.calculate_fee(price, qty)
        cost = (qty * price_per_contract) + fee
        
        while cost > max_spend and qty > 0:
            qty -= 1
            fee = self.calculate_fee(price, qty)
            cost = (qty * price_per_contract) + fee

        if qty <= 0: return

        if qty > 0:
            if wallet.spend(cost):
                portfolio['cash'] = wallet.available_cash
                portfolio['spent_today'] += cost
                
                # DEBUG: Trace Spend
                print(f"  [TRADE] {ticker} {action} | Qty: {qty} | Cost: ${cost:.2f} | Equity: ${total_equity:.2f} | Budget: ${daily_budget:.2f} | Spent: ${portfolio['spent_today']:.2f}")

                portfolio['holdings'].append({
                    'ticker': ticker, 'side': side, 'qty': qty, 'price': price, 'cost': cost
                })
                portfolio['trades'].append({
                    'time': timestamp, 'action': action, 'ticker': ticker, 'price': price, 'qty': qty, 'cost': cost,
                    'capital_after': wallet.get_total_equity()
                })
                
                # For visualization, we want to plot on the NO line.
                viz_y = no_ask if pd.notna(no_ask) else (100 - price if side == 'yes' else price)
                
                daily_trades_viz.append({
                    'time': timestamp, 'strategy': strategy.name, 'action': action, 'ticker': ticker,
                    'price': price, 'qty': qty, 'cost': cost, 'viz_y': viz_y
                })

    def settle_eod(self, df, daily_trades_viz):
        last_rows = df.groupby('market_ticker').last()
        if not df.empty:
            settle_time = df['timestamp'].iloc[-1] + timedelta(hours=1)
        else:
            settle_time = datetime.now()

        for name, portfolio in self.portfolios.items():
            for holding in list(portfolio['holdings']):
                ticker = holding['ticker']
                side = holding['side']
                qty = holding['qty']
                cost = holding['cost']
                
                if ticker in last_rows.index:
                    row = last_rows.loc[ticker]
                    yes_ask = row['implied_yes_ask']
                    no_ask = row['implied_no_ask']
                    
                    # print(f"DEBUG SETTLE: {ticker} | YES_ASK: {yes_ask} | NO_ASK: {no_ask}") # DEBUG

                    final_price = 0
                    if side == 'yes':
                        if no_ask > 90: final_price = 0
                        elif yes_ask > 90: final_price = 100
                        else: final_price = yes_ask 
                    else:
                        if yes_ask > 90: final_price = 0
                        elif no_ask > 90: final_price = 100
                        else: final_price = no_ask

                    proceeds = qty * (final_price / 100.0)
                    portfolio['wallet'].add_unsettled(proceeds, settle_time)
                    portfolio['trades'].append({
                        'time': settle_time, 'action': 'SETTLE', 'ticker': ticker, 'price': final_price, 'qty': qty, 'cost': 0, 'proceeds': proceeds,
                        'capital_after': portfolio['wallet'].get_total_equity(),
                        'pnl': proceeds - cost,
                        'exit_price': final_price
                    })
                    daily_trades_viz.append({
                        'time': settle_time, 'strategy': name, 'action': 'SETTLE', 'ticker': ticker,
                        'price': final_price, 'qty': qty, 'cost': 0, 'pnl': proceeds - cost
                    })
            portfolio['holdings'] = []

    def generate_report(self):
        print("\n=== Final Leaderboard (Top 20) ===")
        print(f"\n{'Strategy':<40} | {'Final $':<10} | {'ROI':<8} | {'Trades':<7}")
        print("-" * 75)
        
        results = []
        for name, res in self.portfolios.items():
            final_capital = res['wallet'].get_total_equity()
            pnl = final_capital - INITIAL_CAPITAL
            roi = (pnl / INITIAL_CAPITAL) * 100
            num_trades = len(res['trades'])
            results.append((name, final_capital, roi, num_trades))
            
        results.sort(key=lambda x: x[2], reverse=True)
        
        for name, final_capital, roi, num_trades in results[:20]:
            print(f"{name:<40} | ${final_capital:<9.2f} | {roi:>6.1f}% | {num_trades:<7}")
            
        # Save Full Report
        with open('backtest_report_parametric.txt', 'w') as f:
            f.write("=== PARAMETRIC BACKTEST REPORT ===\n")
            f.write(f"Strategies Tested: {len(self.strategies)}\n\n")
            f.write(f"{'Strategy':<40} | {'Final $':<10} | {'ROI':<8} | {'Trades':<7}\n")
            f.write("-" * 75 + "\n")
            for name, final_capital, roi, num_trades in results:
                f.write(f"{name:<40} | ${final_capital:<9.2f} | {roi:>6.1f}% | {num_trades:<7}\n")

    def generate_daily_chart(self, df, trades, daily_report, date_str, key_strategies):
        # Filter trades for key strategies
        trades = [t for t in trades if t['strategy'] in key_strategies]
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.15, 0.25],
            subplot_titles=(f"Market Activity & Trades - {date_str}", "Daily Strategy Performance", "Detailed Trade Log"),
            specs=[[{"type": "xy"}], [{"type": "table"}], [{"type": "table"}]]
        )
        
        for ticker in df['market_ticker'].unique():
            market_data = df[df['market_ticker'] == ticker]
            if market_data.empty: continue
            
            fig.add_trace(
                go.Scatter(
                    x=market_data['timestamp'], 
                    y=market_data['implied_no_ask'],
                    mode='lines',
                    name=ticker,
                    line_shape='hv', # Step chart
                    line=dict(width=1.5),
                    opacity=0.7
                ),
                row=1, col=1
            )
            
        # 2. Trade Markers
        for i, t in enumerate(trades):
            # Determine Color and Y-Position
            if 'YES' in t['action']:
                color = 'blue'
            else:
                color = 'red'
            
            # Use the captured visualization Y-coordinate (NO Price) if available
            # Fallback to 100-price for YES if not available (legacy/safety)
            if 'viz_y' in t:
                y_pos = t['viz_y']
            else:
                y_pos = 100 - t['price'] if 'YES' in t['action'] else t['price']
                
            symbol = 'circle'
            
            # REMOVED Jitter: Time offset causes misalignment with market lines.
            # We want exact alignment.
            plot_time = t['time']
            
            # Tooltip
            hover_text = (
                f"<b>{t['strategy']}</b><br>"
                f"{t['action']} {t['ticker']}<br>"
                f"Trade Price: {t['price']:.0f}¢<br>"
                f"Plot Y: {y_pos:.0f}<br>"
                f"Qty: {t['qty']}<br>"
                f"Cost: ${t['cost']:.2f}<br>"
                f"Time: {t['time'].strftime('%H:%M:%S')}"
            )
            
            fig.add_trace(
                go.Scatter(
                    x=[plot_time],
                    y=[y_pos],
                    mode='markers',
                    marker=dict(color=color, size=10, symbol=symbol, line=dict(width=2, color='black')),
                    name=f"Trade: {t['strategy']}",
                    text=hover_text,
                    hoverinfo='text',
                    showlegend=False
                ),
                row=1, col=1
            )

        # 3. Daily Report Table
        report_data = []
        for strat, data in daily_report.items():
            pnl = data['end'] - data['start']
            pnl_pct = (pnl / data['start']) * 100 if data['start'] > 0 else 0
            report_data.append([strat, f"${data['start']:.2f}", f"${data['end']:.2f}", f"${pnl:.2f} ({pnl_pct:.1f}%)"])
            
        fig.add_trace(
            go.Table(
                header=dict(values=["Strategy", "Start Capital", "End Capital", "PnL"],
                            fill_color='paleturquoise', align='left'),
                cells=dict(values=list(zip(*report_data)),
                           fill_color='lavender', align='left')
            ),
            row=2, col=1
        )

        # 4. Detailed Trade Table
        day_trades_data = []
        for t in trades:
            pnl_str = f"${t.get('pnl', 0):.2f}"
            day_trades_data.append([
                t['time'].strftime("%H:%M"),
                t['strategy'],
                t['ticker'],
                t['action'],
                f"{t['price']:.0f}¢",
                t['qty'],
                f"${t['cost']:.2f}",
                f"{t.get('exit_price', 0):.0f}¢",
                pnl_str
            ])
        
        day_trades_data.sort(key=lambda x: x[0])
        
        if day_trades_data:
            headers = ["Time", "Strategy", "Ticker", "Action", "Entry", "Qty", "Cost", "Exit (EOD)", "PnL"]
            fig.add_trace(
                go.Table(
                    header=dict(values=headers,
                                fill_color='paleturquoise', align='left'),
                    cells=dict(values=list(zip(*day_trades_data)),
                               fill_color='lavender', align='left')
                ),
                row=3, col=1
            )
        else:
            fig.add_trace(
                go.Table(
                    header=dict(values=["No Trades Executed Today"], fill_color='lightgrey', align='center'),
                    cells=dict(values=[], fill_color='white', align='center')
                ),
                row=3, col=1
            )

        fig.update_layout(
            height=1200,
            title_text=f"Backtest Report: {date_str}",
            hovermode="closest"
        )
        fig.update_yaxes(title_text="Price / Prob", range=[0, 100], row=1, col=1)
        
        filename = os.path.join(CHARTS_DIR, f"backtest_{date_str}.html")
        fig.write_html(filename)

    def generate_performance_chart(self):
        if not self.performance_history: return
        
        df = pd.DataFrame(self.performance_history)
        
        # Create Line Chart
        fig = go.Figure()
        
        # Add a trace for each strategy
        # Columns are 'date' and strategy names
        strategies = [c for c in df.columns if c != 'date']
        
        for strat in strategies:
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df[strat],
                mode='lines+markers',
                name=strat
            ))
            
        fig.update_layout(
            title="Portfolio Performance Over Time",
            xaxis_title="Date",
            yaxis_title="Portfolio Value ($)",
            hovermode="x unified",
            height=800
        )
        
        # Add a horizontal line for Initial Capital
        fig.add_hline(y=INITIAL_CAPITAL, line_dash="dash", line_color="gray", annotation_text="Initial Capital")
        
        filename = os.path.join(CHARTS_DIR, "cumulative_performance.html")
        fig.write_html(filename)
        print(f"Generated cumulative performance chart: {filename}")

if __name__ == "__main__":
    bt = HumanReadableBacktester()
    bt.run()
