import json
import pandas as pd
import numpy as np
import os
import math
from datetime import datetime, timedelta
from collections import defaultdict
from complex_strategy_backtest import ComplexBacktester, Wallet

# Paths
SNAPSHOT_FILE = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\snapshots\snapshot_2026-01-01.json"
MARKET_LOGS_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"

# --- Helper Functions ---
def calculate_convex_fee(price, qty):
    """0.07 * qty * p * (1-p) - Kalshi style fee"""
    p = price / 100.0
    raw_fee = 0.07 * qty * p * (1 - p)
    fee = math.ceil(raw_fee * 100) / 100.0
    return fee

def best_yes_bid(ms):
    yb = ms.get('yes_bid', np.nan)
    na = ms.get('no_ask', np.nan)
    if not pd.isna(yb):
        return yb
    if not pd.isna(na):
        return 100 - na
    return np.nan

def best_yes_ask(ms):
    return ms.get('yes_ask', np.nan)

# --- Strategy Classes ---
class ComplexStrategy:
    def __init__(self, name, risk_pct=0.5):
        self.name = name
        self.risk_pct = risk_pct
        self.reason = "Initializing..."
        
    def on_market_update(self, ticker, market_state, current_time, inventory, active_orders, spendable_cash, idx=0):
        return None

class InventoryAwareMarketMaker(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5, max_inventory=500, inventory_penalty=0.1, max_offset=2, alpha=0.1):
        super().__init__(name, risk_pct)
        self.max_inventory = max_inventory
        self.inventory_penalty = inventory_penalty
        self.max_offset = max_offset
        self.alpha = alpha
        
        self.fair_prices = {} 
        self.last_quote_time = {} 
        self.last_mid_snapshot = {} 

    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, spendable_cash, idx=0):
        yes_ask = best_yes_ask(market_state)
        no_ask = market_state.get('no_ask', np.nan)
        yes_bid = best_yes_bid(market_state)
        
        debug = {"fair": 0, "edge": 0, "status": "Initializing"}

        if pd.isna(yes_ask) or pd.isna(yes_bid):
            debug["status"] = "Missing price data"
            return None, debug

        mid = (yes_bid + yes_ask) / 2.0
        self.last_mid_snapshot[ticker] = mid
        self.last_quote_time[ticker] = current_time

        hist = self.fair_prices.get(ticker, [])
        hist.append(mid)
        if len(hist) > 20: hist.pop(0)
        self.fair_prices[ticker] = hist
        
        if len(hist) < 20: 
            debug["status"] = f"Warmup ({len(hist)}/20)"
            return None, debug
        
        mean_price = np.mean(hist)
        fair_prob = mean_price / 100.0
        debug["fair"] = round(mean_price, 2)
        
        exec_yes_prob_for_yes = yes_ask / 100.0
        exec_yes_prob_for_no = np.nan
        if not pd.isna(no_ask):
             exec_yes_prob_for_no = 1.0 - (no_ask / 100.0) 
        
        edge = 0
        action = None
        price_to_pay = 0
        
        edge_yes = fair_prob - exec_yes_prob_for_yes
        edge_no = np.nan
        if not pd.isna(no_ask):
            edge_no = (1.0 - fair_prob) - (no_ask / 100.0)
        
        if edge_yes > 0:
            edge = edge_yes
            action = 'BUY_YES'
            price_to_pay = yes_ask
        elif not pd.isna(edge_no) and edge_no > 0:
            edge = edge_no
            action = 'BUY_NO'
            price_to_pay = no_ask
            
        if action is None: 
            debug["status"] = f"No Edge (Fair {mean_price:.1f} vs YAsk {yes_ask:.1f}/NAsk {no_ask:.1f})"
            return None, debug
        
        debug["edge"] = round(edge * 100, 2)
        
        dummy_qty = 10
        fee_est = calculate_convex_fee(price_to_pay, dummy_qty) / dummy_qty
        fee_cents = fee_est * 100
        
        required_edge_cents = fee_cents + 0.5
        
        if (edge * 100) < required_edge_cents: 
            debug["status"] = f"Edge {edge*100:.2f}c < Req {required_edge_cents:.2f}c"
            return None, debug
        
        edge_cents = edge * 100.0
        p = price_to_pay / 100.0
        fee_per_contract = 0.07 * p * (1 - p)
        fee_cents = fee_per_contract * 100.0

        edge_after_fee = edge_cents - fee_cents - 0.5
        if edge_after_fee <= 0:
            debug["status"] = f"Edge after fee {edge_after_fee:.2f}c <= 0"
            return None, debug

        scale = min(1.0, edge_after_fee / 4.0)

        max_notional = spendable_cash * 0.25
        max_loss = spendable_cash * 0.06

        price_unit = price_to_pay / 100.0
        cost_unit = price_unit + fee_per_contract

        qty_by_notional = int(max_notional / cost_unit) if cost_unit > 0 else 0
        qty_by_loss = int(max_loss / cost_unit) if cost_unit > 0 else 0

        base_qty = min(qty_by_notional, qty_by_loss)
        if base_qty <= 0:
            debug["status"] = f"Size 0 (Cash ${spendable_cash:.2f})"
            return None, debug

        # INVENTORY CHECK (Includes Pending)
        current_inv = inventories['YES'] if action == 'BUY_YES' else inventories['NO']
        room = self.max_inventory - current_inv
        if room <= 0:
            debug["status"] = f"Inventory Full ({current_inv})"
            return None, debug

        inv_penalty = 1.0 / (1.0 + current_inv / 200.0)

        qty = int(base_qty * scale * inv_penalty)
        qty = max(1, min(qty, room))
        
        fee_real = calculate_convex_fee(price_to_pay, qty)
        fee_cents_real = (fee_real / qty) * 100.0
        
        edge_after_fee_real = edge_cents - fee_cents_real - 0.5
        if edge_after_fee_real <= 0:
            debug["status"] = f"Real edge after fee {edge_after_fee_real:.2f}c <= 0"
            return None, debug
        
        orders = []
        
        # WALL CLOCK EXPIRY
        expiry = datetime.now() + timedelta(seconds=15)
        
        if action == 'BUY_YES':
            if inventories['NO'] > 0: 
                debug["status"] = "Opposite Inventory (NO)"
                return None, debug
            orders.append({'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 'price': yes_ask, 'expiry': expiry, 'source': 'MM', 'time': current_time})
        
        elif action == 'BUY_NO':
            if inventories['YES'] > 0: 
                debug["status"] = "Opposite Inventory (YES)"
                return None, debug
            orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 'price': no_ask, 'expiry': expiry, 'source': 'MM', 'time': current_time})
            
        debug["status"] = f"SIGNAL {action} {qty} @ {price_to_pay}"
        return orders, debug

class RegimeSwitcher(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5):
        super().__init__(name, risk_pct)
        self.mm = InventoryAwareMarketMaker("Sub-MM", risk_pct)
        self.spread_histories = defaultdict(list)
        self.last_decision = {} # {ticker, mid, spread, reason, timestamp}
        
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, spendable_cash, idx=0):
        yes_ask = best_yes_ask(market_state)
        yes_bid = best_yes_bid(market_state)
        
        # Default decision state
        decision = {
            "ticker": ticker,
            "mid": 0.0,
            "spread": 0.0,
            "reason": "Waiting for data...",
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }

        if pd.isna(yes_ask) or pd.isna(yes_bid): 
            decision["reason"] = "Missing price data"
            self.last_decision = decision
            return None
        
        spread = yes_ask - yes_bid
        mid = (yes_ask + yes_bid) / 2.0
        
        decision["mid"] = round(mid, 1)
        decision["spread"] = round(spread, 1)
        
        hist = self.spread_histories[ticker]
        hist.append(spread)
        if len(hist) > 500: hist.pop(0)
        
        tight_threshold = np.percentile(hist, 50) if len(hist) > 100 else sum(hist)/len(hist)
        is_tight = spread <= tight_threshold
        
        h = current_time.hour
        is_active_hour = (5 <= h <= 8) or (13 <= h <= 17) or (21 <= h <= 23)
        
        if not is_active_hour:
            decision["reason"] = f"Outside active hours (Hour: {h})"
        elif not is_tight:
            decision["reason"] = f"Spread {spread:.1f}c > Threshold {tight_threshold:.1f}c"
        else:
            decision["reason"] = "Market Active & Tight"
            
        mm_active = [o for o in active_orders if o.get('source') == 'MM']
        
        # MATCH LIVE BOT BEHAVIOR: Get 'MM' inventory from nested dict
        mm_inv = portfolios_inventories.get('MM', {'YES': 0, 'NO': 0})
        
        mm_orders = None
        mm_debug = None
        if is_active_hour and is_tight:
            mm_orders, mm_debug = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, spendable_cash, idx)
            if mm_debug:
                decision["reason"] = mm_debug["status"]
                decision["fair"] = mm_debug["fair"]
                decision["edge"] = mm_debug["edge"]
        elif not is_active_hour:
            mm_orders = None
        else:
            mm_orders = []
            
        self.last_decision = decision
        
        if mm_orders is None: return None
        
        combined = []
        if mm_orders is not None: combined.extend(mm_orders)
        else: combined.extend(mm_active)
        
        return combined

class SnapshotBacktester(ComplexBacktester):
    def __init__(self, snapshot_path):
        super().__init__()
        self.snapshot_path = snapshot_path
        self.load_snapshot()
        self.strategies = [RegimeSwitcher("SnapshotStrategy")]

    def load_snapshot(self):
        print(f"Loading snapshot from {self.snapshot_path}...")
        with open(self.snapshot_path, 'r') as f:
            data = json.load(f)

        # 1. Set Time (Use the snapshot timestamp!)
        ts_str = data.get('timestamp') or data.get('last_update')
        self.start_date = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        self.current_time = self.start_date
        
        # 2. Initialize Wallet
        balance = data.get('balance') or data.get('cash')
        self.portfolios = {
            'SnapshotStrategy': {
                'wallet': Wallet(balance),
                'inventory_yes': {'SnapshotStrategy': {}},
                'inventory_no': {'SnapshotStrategy': {}},
                'active_limit_orders': {},
                'trades': [],
                'paid_out': set()
            }
        }
        
        # 3. Initialize Inventory & Calculate Exposure
        positions = data['positions']
        self.current_exposure = 0.0
        
        for ticker, pos in positions.items():
            yes_qty = pos.get('yes', 0)
            no_qty = pos.get('no', 0)
            cost = pos.get('cost', 0.0)
            self.current_exposure += cost
            
            if yes_qty > 0:
                if ticker not in self.portfolios['SnapshotStrategy']['inventory_yes']['SnapshotStrategy']:
                    self.portfolios['SnapshotStrategy']['inventory_yes']['SnapshotStrategy'][ticker] = 0
                self.portfolios['SnapshotStrategy']['inventory_yes']['SnapshotStrategy'][ticker] = yes_qty
            if no_qty > 0:
                if ticker not in self.portfolios['SnapshotStrategy']['inventory_no']['SnapshotStrategy']:
                    self.portfolios['SnapshotStrategy']['inventory_no']['SnapshotStrategy'][ticker] = 0
                self.portfolios['SnapshotStrategy']['inventory_no']['SnapshotStrategy'][ticker] = no_qty
                
        # 4. Set Daily Start Equity
        self.daily_start_equity = data['daily_start_equity']
        
        print(f"Snapshot Loaded:")
        print(f"  Timestamp: {self.start_date}")
        print(f"  Balance: ${balance:.2f}")
        print(f"  Daily Start Equity: ${self.daily_start_equity:.2f}")
        print(f"  Current Exposure: ${self.current_exposure:.2f}")
        print(f"  Positions: {len(positions)}")

        # --- MANUAL SETTLEMENT PATCH (Jan 1 Markets) ---
        # The Sim doesn't have full settlement logic, so we apply the known outcome of Jan 1 markets
        # to see if the freed-up budget triggers trades.
        print("Applying Manual Settlement for Jan 1 Markets...")
        
        # 1. Remove Expired Positions
        jan1_tickers = [t for t in positions if "26JAN01" in t]
        settled_cash = 13.00 # From comparing snapshots ($39.26 - $26.26)
        removed_exposure = 0.0
        
        for t in jan1_tickers:
            print(f"  Settling {t}...")
            # Remove from inventory
            if t in self.portfolios['SnapshotStrategy']['inventory_yes']['SnapshotStrategy']:
                del self.portfolios['SnapshotStrategy']['inventory_yes']['SnapshotStrategy'][t]
            if t in self.portfolios['SnapshotStrategy']['inventory_no']['SnapshotStrategy']:
                del self.portfolios['SnapshotStrategy']['inventory_no']['SnapshotStrategy'][t]
            
            # Calculate removed exposure
            removed_exposure += positions[t]['cost']
            
        # 2. Update Wallet and Exposure
        self.portfolios['SnapshotStrategy']['wallet'].available_cash += settled_cash
        self.current_exposure -= removed_exposure
        
        print(f"Settlement Complete:")
        print(f"  Cash Added: ${settled_cash:.2f} -> New Balance: ${self.portfolios['SnapshotStrategy']['wallet'].available_cash:.2f}")
        print(f"  Exposure Removed: ${removed_exposure:.2f} -> New Exposure: ${self.current_exposure:.2f}")
        print(f"  Budget Freed: ${removed_exposure:.2f}")

    def run_simulation(self):
        print(f"Starting Simulation from {self.current_time}...")
        
        # Load Data
        files = [f for f in os.listdir(MARKET_LOGS_DIR) if f.startswith("market_data_KXHIGHNY-") and f.endswith(".csv")]
        relevant_data = []
        print(f"Scanning {len(files)} log files for data after {self.current_time}...")
        
        for f in files:
            path = os.path.join(MARKET_LOGS_DIR, f)
            try:
                df = pd.read_csv(path)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                # Filter for data AFTER the snapshot
                start_ts = self.current_time
                # We can go until the end of the file/day
                
                mask = (df['timestamp'] >= start_ts)
                df_subset = df[mask].copy()
                
                if not df_subset.empty:
                    relevant_data.append(df_subset)
            except Exception as e:
                pass
                
        if not relevant_data:
            print("No market data found after snapshot time.")
            return
            
        full_df = pd.concat(relevant_data)
        full_df = full_df.sort_values('timestamp')
        print(f"Found {len(full_df)} ticks.")
        
        trade_count = 0
        
        for i, row in full_df.iterrows():
            self.current_time = row['timestamp']
            ticker = row['market_ticker']
            
            market_state = {
                'yes_bid': row['best_yes_bid'],
                'yes_ask': row['implied_yes_ask'],
                'no_bid': row['best_no_bid'],
                'no_ask': row['implied_no_ask'],
                'last_price': row.get('last_price', 0),
                'timestamp': row['timestamp']
            }
            
            for strategy in self.strategies:
                portfolio = self.portfolios[strategy.name]
                
                inv_yes = portfolio['inventory_yes']['SnapshotStrategy'].get(ticker, 0)
                inv_no = portfolio['inventory_no']['SnapshotStrategy'].get(ticker, 0)
                
                # MATCH LIVE BOT BEHAVIOR: Nested Inventory
                pos_for_strategy = {
                    'MM': {
                        'YES': inv_yes, 
                        'NO': inv_no
                    }
                }
                
                # Calculate Spendable Cash (Budget - Exposure)
                budget = self.daily_start_equity * strategy.risk_pct
                available_budget = budget - self.current_exposure
                
                # Also limited by actual cash balance
                spendable = min(portfolio['wallet'].available_cash, available_budget)
                
                # If budget is full, spendable might be negative or zero
                if spendable < 0: spendable = 0
                
                orders = strategy.on_market_update(
                    ticker, 
                    market_state, 
                    self.current_time, 
                    pos_for_strategy, 
                    [], # active_orders
                    spendable
                )
                
                if orders:
                    for order in orders:
                        print(f"[{self.current_time}] SIGNAL: {order['action']} {order['qty']} @ {order['price']} ({order['source']})")
                        trade_count += 1
                        
                        # Update Exposure (Simplified)
                        # In a real backtest we'd execute and update cost.
                        # Here we just increment exposure to prevent infinite signaling if we were looping.
                        # But since we process linear time, it's fine.
                        # However, if we get a signal, we should technically "execute" it to update exposure for the NEXT tick.
                        # Otherwise we might get the same signal 100 times.
                        
                        cost = (order['qty'] * order['price'] / 100.0) + calculate_convex_fee(order['price'], order['qty'])
                        self.current_exposure += cost
                        portfolio['wallet'].available_cash -= cost
                        
        print(f"Simulation Complete. Total Signals: {trade_count}")

if __name__ == "__main__":
    backtester = SnapshotBacktester(SNAPSHOT_FILE)
    backtester.run_simulation()
