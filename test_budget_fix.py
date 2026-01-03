import pandas as pd
import numpy as np
import math
from datetime import timedelta
from collections import defaultdict
import complex_strategy_backtest
from complex_strategy_backtest import ComplexBacktester, RegimeSwitcher, InventoryAwareMarketMaker, MicroScalper, best_yes_ask, best_yes_bid, calculate_convex_fee

# --- Configuration ---
complex_strategy_backtest.LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
complex_strategy_backtest.START_DATE = "25DEC17" 
complex_strategy_backtest.END_DATE = "25DEC19"
complex_strategy_backtest.INITIAL_CAPITAL = 100.00

# --- 1. BUGGY STRATEGY (The Live One) ---
class BuggyStrategy(RegimeSwitcher):
    def __init__(self):
        super().__init__("Buggy (Live)", risk_pct=0.5)

# --- Custom Backtester ---
class ComparisonBacktester(ComplexBacktester):
    def __init__(self):
        self.strategies = [BuggyStrategy()]
        self.start_time_midnight_filter = False
        self.performance_history = []
        self.portfolios = {}
        
        from complex_strategy_backtest import Wallet, defaultdict
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(complex_strategy_backtest.INITIAL_CAPITAL),
                'inventory_yes': defaultdict(lambda: defaultdict(int)),
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'pnl_by_source': defaultdict(float),
                'paid_out': set(),
                'daily_start_equity': complex_strategy_backtest.INITIAL_CAPITAL # Initialize!
            }

if __name__ == "__main__":
    print("=== BUDGET FIX VERIFICATION (Dec 17 - Dec 19) ===")
    print("Strategy: Buggy (Live) with Budget Check Patch")
    print("Starting Backtest...", flush=True)
    
    bt = ComparisonBacktester()
    bt.run()
