import pandas as pd
import numpy as np
from complex_strategy_backtest import ComplexBacktester, RegimeSwitcher, best_yes_ask, best_yes_bid
import complex_strategy_backtest

# Override the configuration to point to the correct logs
complex_strategy_backtest.LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
complex_strategy_backtest.START_DATE = None
complex_strategy_backtest.END_DATE = None
complex_strategy_backtest.INITIAL_CAPITAL = 100.00 # Match live bot roughly

class BuggyRegimeSwitcher(RegimeSwitcher):
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        # COPY OF THE BUGGY LOGIC FROM LIVE TRADER
        
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
        
        # --- THE BUG IS HERE ---
        if is_active_hour and is_tight:
            # Only update MM if tight
            mm_orders = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx)
        elif not is_active_hour:
            mm_orders = None
        else:
            # If WIDE, we return empty list AND DO NOT CALL mm.on_market_update
            # This causes the MM state (fair price history) to become STALE
            mm_orders = []
            
        if mm_orders is None: return None
        
        return mm_orders

if __name__ == "__main__":
    print("Running Backtest with FORCED BUG (Live Trader Replication)...")
    # Use the Buggy Strategy
    backtester = ComplexBacktester()
    buggy_strat = BuggyRegimeSwitcher("Buggy Live Trader Replica")
    backtester.strategies = [buggy_strat]
    
    # Re-initialize portfolios for the new strategy
    from complex_strategy_backtest import Wallet, defaultdict
    backtester.portfolios = {}
    backtester.portfolios[buggy_strat.name] = {
        'wallet': Wallet(complex_strategy_backtest.INITIAL_CAPITAL),
        'inventory_yes': defaultdict(lambda: defaultdict(int)),
        'inventory_no': defaultdict(lambda: defaultdict(int)),
        'active_limit_orders': defaultdict(list),
        'trades': [],
        'pnl_by_source': defaultdict(float),
        'paid_out': set()
    }
    
    backtester.run()
