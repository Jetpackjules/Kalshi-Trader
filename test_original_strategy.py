import pandas as pd
import numpy as np
from multi_strategy_backtest import ComplexBacktester, RegimeSwitcher, InventoryAwareMarketMaker, MicroScalper, Strategy
import multi_strategy_backtest

# Override Configuration
multi_strategy_backtest.LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
multi_strategy_backtest.START_DATE = "25DEC23"
multi_strategy_backtest.END_DATE = "25DEC26"
multi_strategy_backtest.INITIAL_CAPITAL = 100.00

# The ComplexBacktester in multi_strategy_backtest.py is different from complex_strategy_backtest.py
# It expects 'strategy_kwargs' but hardcodes the strategy list in __init__.
# We need to subclass or monkeypatch to force it to run ONLY the RegimeSwitcher with the Simple MM.

class SimpleRegimeSwitcher(RegimeSwitcher):
    def __init__(self, name, risk_pct=0.5):
        # Initialize with the SIMPLE components from multi_strategy_backtest.py
        super().__init__(name, risk_pct)
        # Explicitly re-init to be sure (though super does it)
        self.maker = InventoryAwareMarketMaker("Maker_Sub", risk_pct)
        self.scalper = MicroScalper("Scalper_Sub", risk_pct)

class TestBacktester(ComplexBacktester):
    def __init__(self):
        # Bypass the hardcoded strategy list in the original class
        self.strategies = [SimpleRegimeSwitcher("Original Profitable Strategy")]
        self.start_time_midnight_filter = False
        self.performance_history = []
        self.portfolios = {}
        
        # Initialize portfolios (copied from original __init__ logic)
        from multi_strategy_backtest import Wallet, defaultdict
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(multi_strategy_backtest.INITIAL_CAPITAL),
                'inventory_yes': defaultdict(lambda: defaultdict(int)),
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'pnl_by_source': defaultdict(float),
                'paid_out': set()
            }

if __name__ == "__main__":
    print("Running Backtest with ORIGINAL STRATEGY (Simple MM + Scalper)...")
    backtester = TestBacktester()
    backtester.run()
