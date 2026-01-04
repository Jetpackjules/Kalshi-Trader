import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from complex_strategy_backtest import ComplexBacktester, Wallet, RegimeSwitcher


DEFAULT_SNAPSHOT_DIR = os.path.join(os.getcwd(), "vm_logs", "snapshots")
DEFAULT_MARKET_LOGS_DIR = os.path.join(os.getcwd(), "vm_logs", "market_logs")

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
    def __init__(self, snapshot_path: str, market_logs_dir: str):
        super().__init__()
        self.snapshot_path = snapshot_path
        self.market_logs_dir = market_logs_dir
        self.load_snapshot()
        # Use the same strategy as the main backtester by default
        self.strategies = [RegimeSwitcher("Algo 3: Regime Switcher (Meta)")]

    def load_snapshot(self):
        print(f"Loading snapshot from {self.snapshot_path}...")
        with open(self.snapshot_path, 'r') as f:
            data = json.load(f)

        # 1. Set Time (Use the snapshot timestamp!)
        ts_str = data.get('timestamp') or data.get('last_update')
        self.start_date = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        self.current_time = self.start_date
        
        # 2. Initialize Wallet
        balance = float(data.get('balance') or data.get('cash') or 0.0)
        strategy_name = "Algo 3: Regime Switcher (Meta)"

        self.portfolios = {
            strategy_name: {
                'wallet': Wallet(balance),
                'inventory_yes': defaultdict(lambda: defaultdict(int)),
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'pnl_by_source': defaultdict(float),
                'paid_out': set(),
                'cost_basis': defaultdict(float),
                'daily_start_equity': float(data.get('daily_start_equity') or 0.0),
            }
        }
        
        # 3. Initialize Inventory & Calculate Exposure
        positions = data.get('positions', {})
        self.current_exposure = 0.0

        p = self.portfolios[strategy_name]
        
        for ticker, pos in positions.items():
            yes_qty = pos.get('yes', 0)
            no_qty = pos.get('no', 0)
            cost = pos.get('cost', 0.0)
            self.current_exposure += cost

            # Attribute all snapshot holdings to the MM source for parity with ComplexBacktester
            if yes_qty > 0:
                p['inventory_yes']['MM'][ticker] = int(yes_qty)
            if no_qty > 0:
                p['inventory_no']['MM'][ticker] = int(no_qty)
            if cost and cost > 0:
                p['cost_basis'][ticker] = float(cost)
                
        # 4. Set Daily Start Equity
        self.daily_start_equity = float(data.get('daily_start_equity') or 0.0)
        p['daily_start_equity'] = self.daily_start_equity
        
        print(f"Snapshot Loaded:")
        print(f"  Timestamp: {self.start_date}")
        print(f"  Balance: ${balance:.2f}")
        print(f"  Daily Start Equity: ${self.daily_start_equity:.2f}")
        print(f"  Current Exposure: ${self.current_exposure:.2f}")
        print(f"  Positions: {len(positions)}")

    def run_simulation(self):
        print(f"Starting parity simulation from {self.current_time}...")

        logs_dir = self.market_logs_dir
        if not os.path.exists(logs_dir):
            raise FileNotFoundError(f"Market logs dir not found: {logs_dir}")

        files = [
            os.path.join(logs_dir, f)
            for f in os.listdir(logs_dir)
            if f.startswith("market_data_") and f.endswith(".csv")
        ]
        files.sort()

        relevant = []
        for path in files:
            try:
                df = pd.read_csv(path)
                df.columns = [c.strip() for c in df.columns]
                df['datetime'] = pd.to_datetime(df['timestamp'], format='mixed', dayfirst=True)
                df = df[df['datetime'] >= self.current_time]
                if not df.empty:
                    df['date_str'] = df['datetime'].dt.strftime("%y%b%d").str.upper()
                    relevant.append(df)
            except Exception:
                continue

        if not relevant:
            print("No market data found after snapshot time.")
            return

        master_df = pd.concat(relevant, ignore_index=True)
        master_df.sort_values('datetime', inplace=True)
        print(f"Loaded {len(master_df)} ticks after snapshot.")

        last_prices = {}
        daily_trades_viz = []
        strategy_name = "Algo 3: Regime Switcher (Meta)"
        p = self.portfolios[strategy_name]

        for idx, row in enumerate(master_df.itertuples(index=False)):
            current_time = row.datetime
            ticker = row.market_ticker
            ms = {
                'yes_ask': getattr(row, 'implied_yes_ask', np.nan),
                'no_ask': getattr(row, 'implied_no_ask', np.nan),
                'yes_bid': getattr(row, 'best_yes_bid', np.nan),
                'no_bid': getattr(row, 'best_no_bid', np.nan),
            }

            # update last_prices only while market live (same as ComplexBacktester)
            end_t = self.market_end_time_from_ticker(ticker) if hasattr(self, 'market_end_time_from_ticker') else None
            yask = ms.get('yes_ask', np.nan)
            ybid = ms.get('yes_bid', np.nan)
            if not pd.isna(yask) and not pd.isna(ybid):
                mid = (yask + ybid) / 2.0
                if end_t is None or current_time < end_t:
                    last_prices[ticker] = mid

            p['wallet'].check_settlements(current_time)
            self.liquidate_at_end(p, ticker, ms, current_time)
            self.handle_market_expiries(p, current_time, last_prices)
            self.check_limit_fills(p, ticker, ms, current_time, daily_trades_viz, strategy_name, last_prices)

            if end_t is None or current_time < end_t:
                src_invs = {
                    'MM': {'YES': p['inventory_yes']['MM'][ticker], 'NO': p['inventory_no']['MM'][ticker]},
                    'Scalper': {'YES': p['inventory_yes']['Scalper'][ticker], 'NO': p['inventory_no']['Scalper'][ticker]},
                }
                for s in self.strategies:
                    new_orders = s.on_market_update(
                        ticker,
                        ms,
                        current_time,
                        src_invs,
                        p['active_limit_orders'][ticker],
                        p['wallet'].available_cash,
                        idx,
                    )
                    if new_orders is not None:
                        active_orders = []
                        for o in new_orders:
                            filled = False
                            action = o['action']
                            limit_price = o['price']
                            qty = o['qty']
                            source = o['source']

                            if action == 'BUY_YES':
                                curr_ask = ms.get('yes_ask', np.nan)
                                if not pd.isna(curr_ask) and limit_price >= curr_ask:
                                    filled = bool(self.execute_trade(p, ticker, action, float(curr_ask), qty, source, current_time, ms, s.name, daily_trades_viz))
                            elif action == 'BUY_NO':
                                curr_ask = ms.get('no_ask', np.nan)
                                if not pd.isna(curr_ask) and limit_price >= curr_ask:
                                    filled = bool(self.execute_trade(p, ticker, action, float(curr_ask), qty, source, current_time, ms, s.name, daily_trades_viz))

                            if not filled:
                                active_orders.append(o)
                        p['active_limit_orders'][ticker] = active_orders

        print(f"Parity simulation complete. Trades executed: {len(p.get('trades', []))}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, help="Path to snapshot JSON")
    parser.add_argument("--market-logs-dir", default=DEFAULT_MARKET_LOGS_DIR)
    args = parser.parse_args()

    backtester = SnapshotBacktester(args.snapshot, args.market_logs_dir)
    backtester.run_simulation()


if __name__ == "__main__":
    main()
