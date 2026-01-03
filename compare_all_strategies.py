import pandas as pd
import numpy as np
import math
from datetime import timedelta
from collections import defaultdict
import complex_strategy_backtest
from complex_strategy_backtest import ComplexBacktester, RegimeSwitcher, InventoryAwareMarketMaker, MicroScalper, best_yes_ask, best_yes_bid, calculate_convex_fee

# --- Configuration ---
complex_strategy_backtest.LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
complex_strategy_backtest.START_DATE = "25DEC23" # Recent Period (User Claim)
complex_strategy_backtest.END_DATE = None      # To End
complex_strategy_backtest.INITIAL_CAPITAL = 100.00

# --- 1. BUGGY STRATEGY (The Live One) ---
# The base RegimeSwitcher in complex_strategy_backtest.py IS the buggy one (gated update).
class BuggyStrategy(RegimeSwitcher):
    def __init__(self):
        super().__init__("Buggy (Live)", risk_pct=0.5)

# --- 2. FIXED STRATEGY (Ungated) ---
class FixedStrategy(RegimeSwitcher):
    def __init__(self):
        super().__init__("Fixed (Ungated)", risk_pct=0.5)
        
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        # COPY OF BASE LOGIC BUT WITH is_tight FORCED TRUE
        yes_ask = best_yes_ask(market_state)
        yes_bid = best_yes_bid(market_state)
        if pd.isna(yes_ask) or pd.isna(yes_bid): return None
        
        spread = yes_ask - yes_bid
        hist = self.spread_histories[ticker]
        hist.append(spread)
        if len(hist) > 500: hist.pop(0)
        
        # FORCE TIGHT
        is_tight = True 
        
        h = current_time.hour
        if self.active_hours is not None:
            is_active_hour = h in self.active_hours
        else:
            is_active_hour = (not complex_strategy_backtest.ENABLE_TIME_CONSTRAINTS) or (5 <= h <= 8) or (13 <= h <= 17) or (21 <= h <= 23)
        
        mm_active = [o for o in active_orders if o.get('source') == 'MM']
        mm_inv = portfolios_inventories.get('MM', {'YES': 0, 'NO': 0})
        
        mm_orders = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx) if is_active_hour and is_tight else (None if not is_active_hour else [])
        
        if mm_orders is None: return None
        return mm_orders

# --- 3. HYBRID STRATEGY (Always Update, Gate Trade) ---
class HybridStrategy(RegimeSwitcher):
    def __init__(self):
        super().__init__("Hybrid (Proposed)", risk_pct=0.5)

    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        yes_ask = best_yes_ask(market_state)
        yes_bid = best_yes_bid(market_state)
        if pd.isna(yes_ask) or pd.isna(yes_bid): return None
        
        spread = yes_ask - yes_bid
        hist = self.spread_histories[ticker]
        hist.append(spread)
        if len(hist) > 500: hist.pop(0)
        
        tight_threshold = np.percentile(hist, self.tightness_percentile) if len(hist) > 100 else sum(hist)/len(hist)
        is_tight = spread <= tight_threshold
        
        h = current_time.hour
        if self.active_hours is not None:
            is_active_hour = h in self.active_hours
        else:
            is_active_hour = (not complex_strategy_backtest.ENABLE_TIME_CONSTRAINTS) or (5 <= h <= 8) or (13 <= h <= 17) or (21 <= h <= 23)
        
        mm_active = [o for o in active_orders if o.get('source') == 'MM']
        mm_inv = portfolios_inventories.get('MM', {'YES': 0, 'NO': 0})
        
        if is_active_hour:
            # ALWAYS UPDATE
            mm_orders = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx)
            # GATE OUTPUT
            if not is_tight:
                mm_orders = []
        else:
            mm_orders = None
            
        if mm_orders is None: return None
        return mm_orders

# --- 4. ORIGINAL STRATEGY (Simple MM) ---
# Re-implementing the simpler logic from multi_strategy_backtest.py
class SimpleMM(complex_strategy_backtest.ComplexStrategy):
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
             orders.append({'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 'price': my_bid_tick, 'expiry': tick_expiry, 'source': 'MM'})
        if can_sell_yes:
             orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 'price': 100 - my_ask_tick, 'expiry': tick_expiry, 'source': 'MM'})
             
        return orders

class OriginalStrategy(RegimeSwitcher):
    def __init__(self):
        super().__init__("Original (Simple)", risk_pct=0.5)
        # Swap the MM
        self.mm = SimpleMM("Simple_MM", risk_pct=0.5)

# --- 5. TREND STRATEGY ---
class TrendStrategy(complex_strategy_backtest.ComplexStrategy):
    def __init__(self):
        super().__init__("Trend Strategy", risk_pct=0.5)
        self.min_price = 50
        self.max_price = 75
        
    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        orders = []
        yes_ask = market_state.get('yes_ask')
        if pd.isna(yes_ask): return None
        
        market_price = yes_ask
        no_price = 100 - market_price
        
        if self.min_price < no_price < self.max_price:
            if not active_orders:
                tick_expiry = current_time + timedelta(minutes=5)
                orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': 10, 'price': int(no_price), 'expiry': tick_expiry, 'source': 'Trend'})
        return orders

# --- Custom Backtester to run them all ---
class ComparisonBacktester(ComplexBacktester):
    def __init__(self):
        # Initialize ALL strategies
        self.strategies = [
            BuggyStrategy(),
            FixedStrategy(),
            HybridStrategy(),
            OriginalStrategy(),
            TrendStrategy()
        ]
        
        self.start_time_midnight_filter = False
        self.performance_history = []
        self.portfolios = {}
        
        # Init Portfolios
        from complex_strategy_backtest import Wallet, defaultdict
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(complex_strategy_backtest.INITIAL_CAPITAL),
                'inventory_yes': defaultdict(lambda: defaultdict(int)),
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'pnl_by_source': defaultdict(float),
                'paid_out': set()
            }

if __name__ == "__main__":
    print("=== FULL RANGE STRATEGY COMPARISON (Dec 05 - Dec 28) ===")
    print("Strategies: Buggy, Fixed, Hybrid, Original, Trend")
    print("Starting Backtest...", flush=True)
    
    bt = ComparisonBacktester()
    bt.run()
