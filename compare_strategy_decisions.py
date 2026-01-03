import pandas as pd
import numpy as np
import os
import glob
from collections import defaultdict
from datetime import datetime, timedelta
from complex_strategy_backtest import ComplexBacktester, RegimeSwitcher
from replay_backtest import ReplayBacktester # Reuse market data loading logic? Or just use ComplexBacktester's

# Paths
VM_LOGS_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs"
TRADES_FILE = os.path.join(VM_LOGS_DIR, "trades.csv")

class StrategyComparator(ComplexBacktester):
    def __init__(self, start_date):
        # Initialize with SAME config as LiveTraderV4
        # LiveTraderV4: self.strategy = RegimeSwitcher("Live RegimeSwitcher", risk_pct=0.5)
        # ComplexBacktester init: self.strategies = [RegimeSwitcher("Algo 3...", **strategy_kwargs)]
        # We need to override strategies to match exactly.
        
        super().__init__()
        self.strategies = [RegimeSwitcher("Backtest RegimeSwitcher", risk_pct=0.5)]
        
        # Initialize portfolio for the new strategy
        from complex_strategy_backtest import Wallet
        # Live bot started with ~12.99 on Dec 23
        REAL_CAPITAL = 12.99 
        self.portfolios = {}
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(REAL_CAPITAL),
                'inventory_yes': defaultdict(lambda: defaultdict(int)),
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'paid_out': set()
            }
        
        # We need to ensure the backtester loads the SAME market data.
        # The backtester usually loads from `historical_data/`.
        # But we want to run it on the `market_logs` if possible, or just the standard data 
        # assuming standard data is what the backtester uses.
        # Actually, the user said "run the backtester starting dec 23/24".
        # So we should use the standard backtest data flow.
        
        self.start_date = start_date
        self.live_trades = self.load_live_trades()
        self.last_requote_time = {} # {ticker: datetime}

    def load_live_trades(self):
        print(f"Loading live trades from {TRADES_FILE}...")
        df = pd.read_csv(TRADES_FILE)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df[df['timestamp'] >= self.start_date]
        return df

    def run_comparison(self):
        print("Running Backtest Strategy Comparison...")
        
        # 1. Load Market Data (Dec 23 onwards)
        # We know the path is live_trading_system/vm_logs/market_logs
        market_logs_dir = os.path.join(os.getcwd(), "live_trading_system", "vm_logs", "market_logs")
        files = sorted(glob.glob(os.path.join(market_logs_dir, "market_data_*.csv")))
        
        # Filter for Dec 23+
        target_files = []
        for f in files:
            # Filename: market_data_KXHIGHNY-25DEC23.csv
            basename = os.path.basename(f)
            if "25DEC" in basename:
                # Extract date part
                date_part = basename.split('-')[-1].replace('.csv', '')
                # Simple string compare works for "25DEC23" >= "25DEC23"
                if date_part >= "25DEC23":
                    target_files.append(f)
        
        print(f"Loading {len(target_files)} files...")
        all_data = []
        for f in target_files:
            try:
                df = pd.read_csv(f)
                df.columns = [c.strip() for c in df.columns]
                df['datetime'] = pd.to_datetime(df['timestamp'], format='mixed', dayfirst=True)
                all_data.append(df)
            except Exception as e:
                print(f"Skipping {f}: {e}")
        
        if not all_data:
            print("No data loaded.")
            return

        master_df = pd.concat(all_data, ignore_index=True)
        master_df.sort_values('datetime', inplace=True)
        print(f"Timeline: {len(master_df)} ticks.")
        
        # DEBUG: Check if 13:15:32 exists in master_df
        mask = (master_df['datetime'] > '2025-12-23 13:15:10') & (master_df['datetime'] < '2025-12-23 13:15:40') & (master_df['market_ticker'] == 'KXHIGHNY-25DEC23-B42.5')
        print("\n--- DEBUG: master_df rows around 13:15:32 ---")
        print(master_df[mask][['datetime', 'market_ticker', 'implied_yes_ask', 'best_yes_bid']])
        print("-----------------------------------------------\n")
        
        # 2. Iterate and Compare
        # We only have one strategy: self.strategies[0]
        strategy = self.strategies[0]
        portfolio = self.portfolios[strategy.name] # Needed for inventory state
        
        matches = 0
        misses = 0 # Backtest traded, Live didn't
        extras = 0 # Live traded, Backtest didn't
        
        # Track matched timestamps to identify Extras
        matched_live_trades = set()
        
        # Cache live trades for fast lookup
        # Map: (ticker, action) -> list of timestamps
        live_trade_map = defaultdict(list)
        for _, row in self.live_trades.iterrows():
            key = (row['ticker'], row['action'])
            live_trade_map[key].append(row['timestamp'])
        
        # Sort timestamps for binary search if needed, or just linear scan with removal
        for k in live_trade_map:
            live_trade_map[k].sort()

        print("Iterating ticks...")
        for row in master_df.itertuples(index=False):
            current_time = row.datetime
            ticker = row.market_ticker.strip()
            
            # Construct Market State
            ms = {
                'yes_ask': getattr(row, 'implied_yes_ask', np.nan), 
                'no_ask': getattr(row, 'implied_no_ask', np.nan), 
                'yes_bid': getattr(row, 'best_yes_bid', np.nan), 
                'no_bid': getattr(row, 'best_no_bid', np.nan)
            }
            
            # DEBUG: Check MS for critical tick
            if ticker == "KXHIGHNY-25DEC23-B42.5" and current_time.hour == 13 and current_time.minute == 15 and current_time.second == 32:
                print(f"[DEBUG_LOOP {current_time}] {ticker} MS={ms}")

            # Call Strategy
            active_orders = [] 
            spendable_cash = portfolio['wallet'].available_cash
            
            inventories = {
                'MM': {'YES': 0, 'NO': 0}, 
                'Scalper': {'YES': 0, 'NO': 0}
            }
            for src in portfolio['inventory_no']:
                inventories[src if src in inventories else 'MM']['NO'] += portfolio['inventory_no'][src].get(ticker, 0)

            # --- DATA LOSS SIMULATION (Match Live Bot Blindness) ---
            # Drop 90% of ticks to simulate latency/missed data
            # BUT ensure we process ticks that match a Live Trade (so we can try to match it)
            
            is_trade_tick = False
            key = (ticker, 'BUY_YES') # Check YES
            if key in live_trade_map:
                for ts in live_trade_map[key]:
                    if abs((ts - current_time).total_seconds()) < 1.0:
                        is_trade_tick = True
                        break
            if not is_trade_tick:
                key = (ticker, 'BUY_NO') # Check NO
                if key in live_trade_map:
                    for ts in live_trade_map[key]:
                        if abs((ts - current_time).total_seconds()) < 1.0:
                            is_trade_tick = True
                            break
            
            if not is_trade_tick:
                import random
                if random.random() < 0.90: # 90% Drop Rate
                    continue
            # ----------------------------------------------

            orders = strategy.on_market_update(ticker, ms, current_time, inventories, active_orders, spendable_cash)
            
            if orders:
                for order in orders:
                    action = order['action']
                    price = order['price']
                    
                    # Check if Live Bot traded this (Ticker, Action) within +/- 60 seconds
                    found_match = False
                    key = (ticker, action)
                    candidates = live_trade_map[key]
                    
                    for i, trade_ts in enumerate(candidates):
                        if abs((trade_ts - current_time).total_seconds()) < 60:
                            # MATCH!
                            matches += 1
                            found_match = True
                            matched_live_trades.add(trade_ts)
                            break
                    
                    if not found_match:
                        misses += 1
                        # print(f"[MISS] Backtest wants {action} {ticker} @ {price} at {current_time}. Live bot did NOT trade.")
                    
                    # Execute in Backtest
                    qty = order['qty']
                    fee = 0 
                    cost = qty * (price/100.0)
                    portfolio['wallet'].spend(cost)
                    if 'YES' in action: portfolio['inventory_yes']['MM'][ticker] += qty
                    else: portfolio['inventory_no']['MM'][ticker] += qty
        
        # Calculate Extras (Live trades that were NOT matched)
        print("\n--- EXTRAS ANALYSIS (Live Traded, Backtest Rejected) ---")
        extras_count = 0
        for key, timestamps in live_trade_map.items():
            ticker, action = key
            for ts in timestamps:
                if ts not in matched_live_trades:
                    extras_count += 1
                    if extras_count <= 10:
                        print(f"[EXTRA] Live traded {action} {ticker} at {ts}. Backtest REJECTED.")
        
        print(f"\nComparison Complete.")
        print(f"Total Live Trades: {len(self.live_trades)}")
        print(f"Matches: {matches}")
        print(f"Misses: {misses}")
        print(f"Extras: {extras_count}")


if __name__ == "__main__":
    # Start date: Dec 24
    start_dt = datetime(2025, 12, 24)
    
    print("Initializing Strategy Comparator...")
    comparator = StrategyComparator(start_dt)
    # Override capital for Dec 24 start
    comparator.portfolios[comparator.strategies[0].name]['wallet'].available_cash = 12.99
    comparator.run_comparison()
