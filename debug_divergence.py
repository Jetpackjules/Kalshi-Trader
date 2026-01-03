import pandas as pd
import complex_strategy_backtest
from complex_strategy_backtest import ComplexBacktester, RegimeSwitcher
import os

# Configure Backtester
complex_strategy_backtest.LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
complex_strategy_backtest.START_DATE = "2025-12-24"
complex_strategy_backtest.END_DATE = "2025-12-25"
complex_strategy_backtest.INITIAL_CAPITAL = 36.60 # Start with Dec 23 end equity from previous run to be fair? 
# Actually, let's start with the REAL equity from Dec 23 end ($21.24) to see if it recovers.
# Or start with $100 to see pure behavior. Let's stick to the previous run's state ($36.60) or just $100 for isolation.
# Let's use $100 to isolate the logic, not the bankroll.
complex_strategy_backtest.INITIAL_CAPITAL = 10000.00

class BuggyStrategy(RegimeSwitcher):
    def __init__(self):
        super().__init__("Buggy (Live)", risk_pct=0.5)

class DebugBacktester(ComplexBacktester):
    def __init__(self):
        super().__init__()
        self.strategies = [BuggyStrategy()]
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
                'paid_out': set()
            }
            
    def run(self):
        self.start_date = pd.to_datetime("2025-12-24")
        print(f"DEBUG: start_date={self.start_date}")
        super().run()
        # Dump trades
        print("\n=== SIMULATION TRADES (Dec 24) ===")
        trades = self.portfolios["Buggy (Live)"]['trades']
        if not trades:
            print("No trades.")
        else:
            df = pd.DataFrame(trades)
            print(df.to_string())
            df.to_csv("sim_trades_dec24.csv", index=False)

if __name__ == "__main__":
    complex_strategy_backtest.START_DATE = "25DEC24"
    complex_strategy_backtest.END_DATE = "25DEC25" 
    complex_strategy_backtest.WARMUP_START_DATE = "2025-12-24"
    complex_strategy_backtest.INITIAL_CAPITAL = 21.24 # Match Live Bot starting equity
    
    bt = DebugBacktester()
    bt.start_date = pd.to_datetime("2025-12-24")
    bt.end_date = pd.to_datetime("2025-12-31")
    bt.warmup_start_date = pd.to_datetime("2025-12-23")
    
    bt.run()
    
    # Dump Daily Equity
    print("\n=== DAILY EQUITY ===")
    print("Date,Equity")
    for entry in bt.performance_history:
        # entry is dict with 'date', 'equity', etc.
        # Check structure of performance_history in ComplexBacktester
        # It seems it stores {'date': ..., 'equity': ...}
        print(f"{entry['date']},{entry['equity']}")
