import pandas as pd
import numpy as np
from complex_strategy_backtest import ComplexBacktester, RegimeSwitcher, best_yes_ask, best_yes_bid
import complex_strategy_backtest

# Override the configuration to point to the correct logs
complex_strategy_backtest.LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
complex_strategy_backtest.START_DATE = None
complex_strategy_backtest.END_DATE = None
complex_strategy_backtest.INITIAL_CAPITAL = 100.00 

class FixedRegimeSwitcher(RegimeSwitcher):
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
        
        # --- THE FIX IS HERE ---
        # We ALWAYS update the MM if it is an active hour, regardless of spread tightness.
        # This ensures the MM's internal price history (fair_prices) is always up to date.
        if is_active_hour:
            mm_orders = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx)
            
            # However, we might still want to RESTRICT TRADING if spread is wide?
            # The original logic coupled "Updating" with "Trading".
            # If we want to mimic the Observer Bot's "Correct" behavior, we should update.
            # The MM itself has logic to decide if it wants to trade.
            # But the RegimeSwitcher might want to filter orders if not tight.
            
            # Let's assume the FIX is to allow updates, but maybe filter orders if we want to be conservative?
            # For now, let's allow the MM to decide. If the MM sees a wide spread, it might not trade anyway 
            # (it checks edge vs fee).
            
            # If we want to strictly enforce "Only Trade when Tight" but "Always Update":
            if not is_tight and mm_orders:
                 # If we are not tight, we can DISCARD the orders, but the MM state was updated!
                 # But wait, if we discard orders, we might miss opportunities?
                 # The user's complaint was "stuck on old prices". 
                 # If we update, we won't be stuck.
                 # Let's try the "Clean" fix: Update and let MM decide.
                 pass
                 
        else:
            mm_orders = None
            
        if mm_orders is None: return None
        
        return mm_orders

if __name__ == "__main__":
    print("Running Backtest with FIXED STRATEGY (Continuous Updates)...")
    
    backtester = ComplexBacktester()
    fixed_strat = FixedRegimeSwitcher("Fixed Strategy (No Gating)")
    backtester.strategies = [fixed_strat]
    
    # Initialize portfolios 
    from complex_strategy_backtest import Wallet, defaultdict
    backtester.portfolios = {}
    backtester.portfolios[fixed_strat.name] = {
        'wallet': Wallet(complex_strategy_backtest.INITIAL_CAPITAL),
        'inventory_yes': defaultdict(lambda: defaultdict(int)),
        'inventory_no': defaultdict(lambda: defaultdict(int)),
        'active_limit_orders': defaultdict(list),
        'trades': [],
        'pnl_by_source': defaultdict(float),
        'paid_out': set()
    }
    
    backtester.run()
