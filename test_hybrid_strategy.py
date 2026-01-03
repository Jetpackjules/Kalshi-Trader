import pandas as pd
import numpy as np
from complex_strategy_backtest import ComplexBacktester, RegimeSwitcher, best_yes_ask, best_yes_bid
import complex_strategy_backtest

# Override Configuration
complex_strategy_backtest.LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
complex_strategy_backtest.START_DATE = "25DEC23"
complex_strategy_backtest.END_DATE = "25DEC26"
complex_strategy_backtest.INITIAL_CAPITAL = 100.00 

class HybridRegimeSwitcher(RegimeSwitcher):
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
        
        # --- HYBRID LOGIC ---
        # 1. ALWAYS Update the MM (so fair price is fresh)
        # 2. BUT only return orders if is_tight (so we don't trade wide spreads)
        
        if is_active_hour:
            # Always call update to refresh internal state (fair_prices, etc.)
            mm_orders = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx)
            
            # If NOT tight, discard the orders (Gate the Output, not the Input)
            if not is_tight:
                mm_orders = [] 
        else:
            mm_orders = None
            
        if mm_orders is None: return None
        
        return mm_orders

if __name__ == "__main__":
    print("Running Backtest with HYBRID STRATEGY (Update Always, Trade Gated)...")
    
    backtester = ComplexBacktester()
    hybrid_strat = HybridRegimeSwitcher("Hybrid Strategy")
    backtester.strategies = [hybrid_strat]
    
    # Initialize portfolios 
    from complex_strategy_backtest import Wallet, defaultdict
    backtester.portfolios = {}
    backtester.portfolios[hybrid_strat.name] = {
        'wallet': Wallet(complex_strategy_backtest.INITIAL_CAPITAL),
        'inventory_yes': defaultdict(lambda: defaultdict(int)),
        'inventory_no': defaultdict(lambda: defaultdict(int)),
        'active_limit_orders': defaultdict(list),
        'trades': [],
        'pnl_by_source': defaultdict(float),
        'paid_out': set()
    }
    
    backtester.run()
