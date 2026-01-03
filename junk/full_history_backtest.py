import pandas as pd
import numpy as np
import os
import math
import sys
from datetime import datetime, timedelta
from collections import defaultdict
from complex_strategy_backtest import ComplexBacktester, Wallet, best_yes_bid, best_yes_ask, calculate_convex_fee

# --- Strategy Classes (Replicated from Live Trader V4) ---

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
        
    def reset(self):
        print(f"[{self.name}] Resetting State")
        self.spread_histories.clear()
        self.last_decision = {}
        if hasattr(self, 'mm'):
            # The MM class might not have reset if I didn't copy it fully or if it's base class
            # But let's try to call it if it exists
            if hasattr(self.mm, 'reset'):
                self.mm.reset()
        
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
        
        # IMPORTANT: Fix for the "bug" where live bot passes position dict instead of strategy dict
        # In live_trader_v4.py, it passes self.positions[ticker] which is {'yes': qty, 'no': qty}
        # But here we are in backtester.
        # If we want to replicate live bot, we should mimic its behavior.
        # But wait, `portfolios_inventories` here comes from `ComplexBacktester`.
        # `ComplexBacktester` passes `self.portfolios[strategy.name]['inventory_yes']` etc?
        # No, `ComplexBacktester` calls `strategy.on_market_update`.
        # We need to ensure `ComplexBacktester` passes the right thing.
        # In `ComplexBacktester.process_tick`:
        # `inventories = {'YES': self.portfolios[s.name]['inventory_yes'][s.name].get(ticker, 0), ...}`
        # So `ComplexBacktester` passes `{'YES': qty, 'NO': qty}`.
        
        # `RegimeSwitcher` expects `portfolios_inventories.get('MM')`.
        # If `ComplexBacktester` passes `{'YES': ..., 'NO': ...}`, then `.get('MM')` is None.
        # So `mm_inv` becomes `{'YES': 0, 'NO': 0}`.
        
        # MATCH LIVE BOT BEHAVIOR EXACTLY
        # 1. Get Settled Inventory (passed by Backtester in nested format)
        mm_inv = portfolios_inventories.get('MM', {'YES': 0, 'NO': 0}).copy()
        
        # 2. Add Pending Orders (Live Bot does this in `run` loop, Backtester doesn't)
        # We must add them here to ensure the strategy sees its "Shadow Inventory"
        for o in active_orders:
            # Filter by source if needed, though Backtester passes all for this ticker
            if o.get('source') == 'MM':
                qty = o['qty']
                if o['action'] == 'BUY_YES':
                    mm_inv['YES'] = mm_inv.get('YES', 0) + qty
                elif o['action'] == 'BUY_NO':
                    mm_inv['NO'] = mm_inv.get('NO', 0) + qty
        
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

class FullHistoryBacktester(ComplexBacktester):
    def __init__(self):
        super().__init__()
        # Override strategies with the Live Bot's strategy
        self.strategies = [RegimeSwitcher("RegimeSwitcher")]
        
        # Re-initialize portfolios for the new strategy
        self.portfolios = {}
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(self.initial_capital),
                'inventory_yes': defaultdict(lambda: defaultdict(int)),
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'paid_out': set(),
                'cost_basis': defaultdict(float),
                'daily_start_equity': self.initial_capital
            }
        
        # Set Date Range
        self.start_date_config = datetime(2025, 12, 5)
        self.end_date_config = None # Latest

    # We need to override `run` or ensure `START_DATE` global is used?
    # `ComplexBacktester` uses global `START_DATE`.
    # But we can set `self.start_date`?
    # No, `ComplexBacktester` doesn't seem to have `start_date` instance var in `__init__`.
    # It uses `START_DATE` from the module scope.
    
    # We can rely on `load_all_data` filtering.
    # Or we can monkeypatch the module level variable?
    # Better: `ComplexBacktester` likely reads `START_DATE` in `load_all_data`.
    
    # Let's just run it and see.
    
if __name__ == "__main__":
    # Set the global config in the imported module
    import complex_strategy_backtest
    complex_strategy_backtest.START_DATE = "2025-12-05"
    complex_strategy_backtest.INITIAL_CAPITAL = 1000.0
    
    print("=== Full History Backtest (Dec 5 - Present) ===")
    bt = FullHistoryBacktester()
    bt.run()
