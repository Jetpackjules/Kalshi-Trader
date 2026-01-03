import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import os
import glob
from datetime import datetime, timedelta
import sys
import math
from collections import defaultdict

# --- Configuration ---
LOG_DIR = os.path.join(os.getcwd(), "live_trading_system", "vm_logs", "market_logs")
CHARTS_DIR = "backtest_charts"
INITIAL_CAPITAL = 1000.0 
START_DATE = None 
END_DATE = None

if not os.path.exists(CHARTS_DIR):
    os.makedirs(CHARTS_DIR)

# --- Constants for Settlement ---
MARKET_END_HOUR = 0      # 00:00 next day
PAYOUT_HOUR = 1          # 01:00 next day

def parse_market_date_from_ticker(ticker: str):
    # Finds the "25DEC16" token inside ticker
    parts = ticker.strip().split('-')
    for p in parts:
        if len(p) == 7 and p[:2].isdigit():
            try:
                return datetime.strptime(p, "%y%b%d")
            except:
                pass
    return None

def market_end_time_from_ticker(ticker: str):
    d = parse_market_date_from_ticker(ticker)
    if d is None:
        return None
    # Market ends at 00:00 the NEXT day (end of market-date)
    end_dt = (d + timedelta(days=1)).replace(hour=MARKET_END_HOUR, minute=0, second=0, microsecond=0)
    return end_dt

def payout_time_from_ticker(ticker: str):
    d = parse_market_date_from_ticker(ticker)
    if d is None:
        return None
    pay_dt = (d + timedelta(days=1)).replace(hour=PAYOUT_HOUR, minute=0, second=0, microsecond=0)
    return pay_dt

# --- Wallet Class ---
class Wallet:
    def __init__(self, initial_capital):
        self.available_cash = initial_capital
        self.unsettled_positions = [] 
        
    def get_total_equity(self):
        unsettled_total = sum(p['amount'] for p in self.unsettled_positions)
        return self.available_cash + unsettled_total

    def check_settlements(self, current_time):
        remaining_unsettled = []
        for p in self.unsettled_positions:
            if p['settle_time'] <= current_time:
                self.available_cash += p['amount']
            else:
                remaining_unsettled.append(p)
        self.unsettled_positions = remaining_unsettled

    def spend(self, amount):
        if amount > self.available_cash + 0.0001:
            return False
        self.available_cash -= amount
        return True

    def add_cash(self, amount):
        self.available_cash += amount

    def add_unsettled(self, amount, settle_time):
        self.unsettled_positions.append({'amount': amount, 'settle_time': settle_time})

def calculate_convex_fee(price, qty):
    """0.07 * qty * p * (1-p) - Kalshi style fee"""
    p = price / 100.0
    raw_fee = 0.07 * qty * p * (1 - p)
    fee = math.ceil(raw_fee * 100) / 100.0
    return fee

def sanitize_price(p):
    if pd.isna(p): return p
    if p > 95: return 100.0
    if p < 5: return 0.0
    return p

# --- Complex Strategy Base Class ---
class ComplexStrategy:
    def __init__(self, name, risk_pct=0.5):
        self.name = name
        self.risk_pct = risk_pct
        
    def on_market_update(self, ticker, market_state, current_time, inventory, active_orders, wallet_equity, idx=0):
        """
        Returns: 
           list of dicts: New state (Replace current active orders)
           None: Keep current orders (Persistence)
        """
        return None

# --- Implementation of Strategy 2.5 (V2 Refined) ---

class InventoryAwareMarketMaker(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5, max_inventory=50, inventory_penalty=0.1, max_offset=2, alpha=0.1):
        super().__init__(name, risk_pct)
        self.max_inventory = max_inventory
        self.inventory_penalty = inventory_penalty
        self.max_offset = max_offset
        self.alpha = alpha
        
        self.fair_prices = {} 
        self.last_quote_time = {} 
        self.last_mid_snapshot = {} 

    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, wallet_equity, idx=0):
        yes_ask = market_state.get('yes_ask')
        no_ask = market_state.get('no_ask')
        yes_bid = market_state.get('yes_bid') 
        
        # Calculate Best Bid/Ask
        if pd.isna(yes_ask):
            return None # Can't price without ask

        cur_bid = yes_bid if not pd.isna(yes_bid) else (100 - no_ask if not pd.isna(no_ask) else np.nan)
        if pd.isna(cur_bid): return None

        mid = (cur_bid + yes_ask) / 2.0
        self.last_mid_snapshot[ticker] = mid
        self.last_quote_time[ticker] = current_time

        # --- PHASE 7: VAMR SIGNAL (Volatility-Adjusted Mean Reversion) ---
        hist = self.fair_prices.get(ticker, [])
        hist.append(mid)
        if len(hist) > 20: hist.pop(0)
        self.fair_prices[ticker] = hist
        
        if len(hist) < 20: return None # Warmup
        
        mean_price = np.mean(hist)
        
        # --- PHASE 8 FIX: VAMR PROBABILITY (Mean-Based) ---
        # Old: 1 - CDF(z) was a tail prob.
        # New: Expected Reversion Price = Mean Price
        fair_prob = mean_price / 100.0
        
        # --- PHASE 8 FIX: EXECUTABLE EDGE ---
        # Compare Fair Value vs. The Price We Pay (Ask)
        exec_yes_prob_for_yes = yes_ask / 100.0
        exec_yes_prob_for_no = 1.0 - (no_ask / 100.0) # Paying for NO at no_ask implies buying YES short at this prob
        
        edge = 0
        action = None
        price_to_pay = 0
        
        # Check Long YES
        edge_yes = fair_prob - exec_yes_prob_for_yes
        # Check Long NO (Short YES)
        edge_no =  (1.0 - fair_prob) - (no_ask / 100.0)
        
        if edge_yes > 0:
            edge = edge_yes
            action = 'BUY_YES'
            price_to_pay = yes_ask
        elif edge_no > 0:
            edge = edge_no
            action = 'BUY_NO'
            price_to_pay = no_ask
            
        if action is None: return None
        
        # --- PHASE 8 FIX: FEE/SPREAD GATE ---
        # Fee Barrier = Convex Fee + Spread Cost + Safety
        # Spread cost is implicit in "Executable Price" (we already paid the spread by crossing), 
        # so we just need Fee + Safety Margin.
        
        dummy_qty = 10
        fee_est = calculate_convex_fee(price_to_pay, dummy_qty) / dummy_qty # $ per contract
        fee_cents = fee_est * 100
        
        # Spread analysis (informational, or extra buffer)
        # spread_cents = max(0, yes_ask - cur_bid) / 2.0
        
        required_edge_cents = fee_cents + 1.0 # Fee + 1c Margin
        
        if (edge * 100) < required_edge_cents: return None
        
        # --- PHASE 8 FIX: SIZING (Edge/Cash Cap) ---
        # Cap at 5% of Equity
        max_dollars = wallet_equity * 0.05
        qty = int(max_dollars / (price_to_pay / 100.0))
        qty = max(1, qty) # Ensure at least 1 contract if affordable
        
        orders = []
        
        # --- EXECUTION ---
        if action == 'BUY_YES':
            # INVARIANT: Cannot buy YES if we hold NO
            if inventories['NO'] > 0: return None
            
            if inventories['YES'] < self.max_inventory:
                 # Price at market ask to capture
                 orders.append({'action': 'BUY_YES', 'ticker': ticker, 'qty': qty, 'price': yes_ask, 'expiry': current_time + timedelta(seconds=15), 'source': 'MM', 'time': current_time})
        
        elif action == 'BUY_NO':
            # INVARIANT: Cannot buy NO if we hold YES
            if inventories['YES'] > 0: return None
            
            if inventories['NO'] < self.max_inventory:
                # Price at market ask for NO
                orders.append({'action': 'BUY_NO', 'ticker': ticker, 'qty': qty, 'price': no_ask, 'expiry': current_time + timedelta(seconds=15), 'source': 'MM', 'time': current_time})
            
        return orders

class MicroScalper(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5, threshold=1.0, profit_target=1):
        super().__init__(name, risk_pct)
        self.threshold = threshold
        self.profit_target = profit_target
        self.last_mids = {}
        
    def on_market_update(self, ticker, market_state, current_time, inventories, active_orders, wallet_equity, idx=0):
        yes_ask = market_state.get('yes_ask')
        cur_bid = market_state.get('yes_bid', (100 - market_state.get('no_ask')) if not pd.isna(market_state.get('no_ask')) else np.nan)
        
        if pd.isna(yes_ask) or pd.isna(cur_bid): return None
        mid = (cur_bid + yes_ask) / 2.0
        
        # Fair Price Snapshot
        last_mid = self.last_mids.get(ticker)
        self.last_mids[ticker] = mid
        
        # Entry Logic - NO EXITS
        if last_mid is None: return None
        
        # Persistence: If we are already resting, don't re-enter
        if active_orders: return None
        
        delta = mid - last_mid
        
        spread = yes_ask - cur_bid
        if spread > 10 or spread <= 1: return None 
        
        if delta >= self.threshold:
            # Spike UP -> Expect Reversion Down -> BUY NO
            return [{'action': 'BUY_NO', 'ticker': ticker, 'qty': 10, 'price': int(100 - yes_ask + 1), 'expiry': current_time + timedelta(seconds=60), 'source': 'Scalper', 'time': current_time}]
        elif delta <= -self.threshold:
            # Spike DOWN -> Expect Reversion Up -> BUY YES
            return [{'action': 'BUY_YES', 'ticker': ticker, 'qty': 10, 'price': int(cur_bid + 1), 'expiry': current_time + timedelta(seconds=60), 'source': 'Scalper', 'time': current_time}]
            
        return None

class RegimeSwitcher(ComplexStrategy):
    def __init__(self, name, risk_pct=0.5):
        super().__init__(name, risk_pct)
        self.mm = InventoryAwareMarketMaker("Sub-MM", risk_pct)
        self.scalper = MicroScalper("Sub-Scalper", risk_pct)
        self.spread_histories = defaultdict(list)
        # Shadow Inventories for attribution/logic
        self.mm_inventory = defaultdict(int) 
        self.sc_inventory = defaultdict(int)
        
    def on_market_update(self, ticker, market_state, current_time, portfolios_inventories, active_orders, wallet_equity, idx=0):
        # portfolios_inventories is dict { 'MM': {'YES': qty, 'NO': qty}, 'Scalper': {'YES': qty, 'NO': qty} }
        
        yes_ask = market_state.get('yes_ask')
        no_ask = market_state.get('no_ask')
        if pd.isna(yes_ask) or pd.isna(no_ask): return None
        
        spread = yes_ask - (100 - no_ask)
        hist = self.spread_histories[ticker]
        hist.append(spread)
        if len(hist) > 500: hist.pop(0)
        
        # Relax Gating: Use 50th percentile (Median) for "tightness"
        tight_threshold = np.percentile(hist, 50) if len(hist) > 100 else sum(hist)/len(hist)
        is_tight = spread <= tight_threshold
        
        h = current_time.hour
        is_active_hour = (5 <= h <= 8) or (13 <= h <= 17) or (21 <= h <= 23)
        
        # Partition active orders by source
        mm_active = [o for o in active_orders if o.get('source') == 'MM']
        sc_active = [o for o in active_orders if o.get('source') == 'Scalper']
        
        # Isolated Routing
        mm_inv = portfolios_inventories.get('MM', {'YES': 0, 'NO': 0})
        # sc_inv = portfolios_inventories.get('Scalper', {'YES': 0, 'NO': 0}) # Scalper Disabled in V7
        
        # MM is the sole Accumulator in Phase 7
        mm_orders = self.mm.on_market_update(ticker, market_state, current_time, mm_inv, mm_active, wallet_equity, idx) if is_active_hour and is_tight else (None if not is_active_hour else [])
        scalper_orders = None # self.scalper.on_market_update(...) # Disabled
        
        if mm_orders is None and scalper_orders is None: return None
        
        combined = []
        if mm_orders is not None: combined.extend(mm_orders)
        else: combined.extend(mm_active)
        
        if scalper_orders is not None: combined.extend(scalper_orders)
        else: combined.extend(sc_active)
        
        return combined

# --- Complex Backtester ---
class ComplexBacktester:
    def __init__(self):
        self.strategies = [RegimeSwitcher("Algo 3: Regime Switcher (Meta)")]
        self.performance_history = []
        self.portfolios = {}
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(INITIAL_CAPITAL),
                'inventory_yes': defaultdict(lambda: defaultdict(int)), # source -> ticker -> qty
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'pnl_by_source': defaultdict(float) 
            }
            
    def handle_market_expiries(self, portfolio, current_time, last_prices):
        """
        When a market ends, we convert held positions into an unsettled payout
        that becomes cash at 1AM next day (per your assumption).
        """
        wallet = portfolio['wallet']

        # Helper to queue payout and clear position
        def queue_payout(ticker, qty, is_yes: bool):
            if qty <= 0:
                return
            end_time = market_end_time_from_ticker(ticker)
            pay_time = payout_time_from_ticker(ticker)
            if end_time is None or pay_time is None:
                return
            if current_time < end_time:
                return  # not ended yet

            # Use last known mid as a proxy "final value" at expiry
            mid = sanitize_price(last_prices.get(ticker, 50.0))
            if is_yes:
                value_per_contract = mid / 100.0
            else:
                value_per_contract = (100.0 - mid) / 100.0

            payout_amount = qty * value_per_contract

            # Money is locked until pay_time
            wallet.add_unsettled(payout_amount, pay_time)

        # YES inventories
        for src in list(portfolio['inventory_yes'].keys()):
            for tkr, qty in list(portfolio['inventory_yes'][src].items()):
                if qty > 0:
                    queue_payout(tkr, qty, is_yes=True)
                    # If it ended, queue_payout already passed the time check;
                    # so clear it only if ended:
                    if current_time >= (market_end_time_from_ticker(tkr) or datetime.max):
                        portfolio['inventory_yes'][src][tkr] = 0
                        portfolio['active_limit_orders'][tkr] = []  # cancel any lingering orders

        # NO inventories
        for src in list(portfolio['inventory_no'].keys()):
            for tkr, qty in list(portfolio['inventory_no'][src].items()):
                if qty > 0:
                    queue_payout(tkr, qty, is_yes=False)
                    if current_time >= (market_end_time_from_ticker(tkr) or datetime.max):
                        portfolio['inventory_no'][src][tkr] = 0
                        portfolio['active_limit_orders'][tkr] = []

    def check_limit_fills(self, portfolio, ticker, market_state, timestamp, viz_list, strat_name):
        active = portfolio['active_limit_orders'][ticker]
        if not active: return
        
        y_ask = market_state.get('yes_ask')
        n_ask = market_state.get('no_ask')
        y_bid = market_state.get('yes_bid', 100-n_ask if not pd.isna(n_ask) else np.nan)
        n_bid = market_state.get('no_bid', 100-y_ask if not pd.isna(y_ask) else np.nan)
        
        # Calculate current spread for regime-aware fill probabilities
        spread_val = np.nan
        if not pd.isna(y_ask) and not pd.isna(y_bid):
            spread_val = y_ask - y_bid
            
        def get_fill_prob(s):
            if pd.isna(s): return 0.15
            if s <= 4: return 0.85
            if s <= 8: return 0.55
            return 0.15

        still_active = []
        for o in active:
            if 'expiry' in o and timestamp >= o['expiry']: continue
            
            filled = False
            l_price = o['price']
            action = o['action']
            qty = o['qty']
            source = o.get('source', 'Unknown')
            ticker = o['ticker'].strip()
            
            # Simple Fill Rule (Phase 6): If price crosses limit, fill.
            # Phase 7.5: Mutual Exclusivity Safety Net
            if action == 'BUY_YES':
                # Reject if we hold NO (Safety Net)
                if portfolio['inventory_no'][source][ticker] > 0:
                    still_active.append(o)
                    continue
                    
                if not pd.isna(y_ask) and y_ask <= l_price:
                    filled = True
            elif action == 'BUY_NO': 
                # Reject if we hold YES (Safety Net)
                if portfolio['inventory_yes'][source][ticker] > 0:
                    still_active.append(o)
                    continue
                    
                if not pd.isna(n_ask) and n_ask <= l_price:
                    filled = True
                            
            if filled:
                fee = calculate_convex_fee(l_price, qty)
                notional = (qty * (l_price / 100.0))
                cost = notional + fee
                
                # Check Cash
                if portfolio['wallet'].spend(cost):
                    # Update Inventory (Separate YES/NO)
                    if action == 'BUY_YES': 
                        portfolio['inventory_yes'][source][ticker] += qty
                    elif action == 'BUY_NO': 
                        portfolio['inventory_no'][source][ticker] += qty
                    
                    spread_val = np.nan
                    if not pd.isna(y_ask) and not pd.isna(y_bid): spread_val = y_ask - y_bid

                    trade = {
                        'time': timestamp, 
                        'action': action, 
                        'ticker': ticker, 
                        'price': l_price, 
                        'qty': qty, 
                        'fee': fee, 
                        'cost': cost,
                        'source': source, 
                        'spread': spread_val, 
                        'capital_after': portfolio['wallet'].get_total_equity()
                    }
                    portfolio['trades'].append(trade)
                    viz_list.append({**trade, 'strategy': strat_name, 'viz_y': 100-l_price if 'YES' in action else l_price})
                else: still_active.append(o)
            else: still_active.append(o)
        portfolio['active_limit_orders'][ticker] = still_active

    def run(self):
        print("[ComplexBacktester] V3 Starting...")
        files = sorted(glob.glob(os.path.join(LOG_DIR, "market_data_*.csv")))
        target_files = [f for f in files if (START_DATE is None or f.split('-')[-1].replace('.csv', '') >= START_DATE) and (END_DATE is None or f.split('-')[-1].replace('.csv', '') <= END_DATE)]
        
        last_prices = {}
        equity_history = []
        
        for f in target_files:
            try:
                date_str = os.path.basename(f).split('-')[-1].replace('.csv', '')
                print(f"Processing {date_str} ({target_files.index(f)+1}/{len(target_files)})...")
                df = pd.read_csv(f)
                df.columns = [c.strip() for c in df.columns]
                df['datetime'] = pd.to_datetime(df['timestamp'], format='mixed', dayfirst=True)
                df.sort_values('datetime', inplace=True)
            except Exception as e:
                print(f"FAILED to process {f}: {e}")
                continue
            
            daily_trades_viz = []
            
            for idx, row in df.iterrows():
                current_time, ticker = row['datetime'], row['market_ticker'].strip()
                ms = {'yes_ask': row.get('implied_yes_ask', np.nan), 'no_ask': row.get('implied_no_ask', np.nan), 'yes_bid': row.get('best_yes_bid', np.nan), 'no_bid': row.get('best_no_bid', np.nan)}
                
                yask, ybid = ms['yes_ask'], ms['yes_bid'] if not pd.isna(ms['yes_bid']) else (100 - ms['no_ask'] if not pd.isna(ms['no_ask']) else np.nan)
                if not pd.isna(yask) and not pd.isna(ybid): 
                    mid = (yask + ybid) / 2.0
                    last_prices[ticker] = mid
                
                # Prevent trading on ended markets
                end_t = market_end_time_from_ticker(ticker)
                if end_t is not None and current_time >= end_t:
                    continue  # market ended; ignore any late rows / prevent new orders

                for s in self.strategies:
                    p = self.portfolios[s.name]
                    p['wallet'].check_settlements(current_time)
                    self.handle_market_expiries(p, current_time, last_prices)
                    self.check_limit_fills(p, ticker, ms, current_time, daily_trades_viz, s.name)
                    

                    # Pass source-specific inventories (YES/NO separated)
                    src_invs = {
                        'MM': {'YES': p['inventory_yes']['MM'][ticker], 'NO': p['inventory_no']['MM'][ticker]},
                        'Scalper': {'YES': p['inventory_yes']['Scalper'][ticker], 'NO': p['inventory_no']['Scalper'][ticker]}
                    }
                    new_orders = s.on_market_update(ticker, ms, current_time, src_invs, p['active_limit_orders'][ticker], p['wallet'].get_total_equity(), idx)
                    if new_orders is not None:
                         p['active_limit_orders'][ticker] = new_orders
                
                # Tick-by-tick MTM Equity Tracking (No Netting)
                current_equity = 0
                for s_name, p in self.portfolios.items():
                    cash = p['wallet'].get_total_equity()
                    holdings = 0
                    
                    # Sum all YES sources
                    for src in p['inventory_yes']:
                        for t, q in p['inventory_yes'][src].items():
                           mid = last_prices.get(t, 50)
                           holdings += q * (mid/100.0)

                    # Sum all NO sources
                    for src in p['inventory_no']:
                        for t, q in p['inventory_no'][src].items():
                           mid = last_prices.get(t, 50)
                           holdings += q * ((100-mid)/100.0)
                           
                    current_equity += (cash + holdings)
                equity_history.append(current_equity)
                
                if idx % 10000 == 0:
                    pass # Placeholder if needed for sparse logging
            
            # Post-Day Report for Viz (MTM Equity)
            daily_report = {}
            for s in self.strategies:
                p = self.portfolios[s.name]
                cash = p['wallet'].get_total_equity()
                holdings = 0
                for src in p['inventory_yes']:
                    for t, q in p['inventory_yes'][src].items():
                        mid = last_prices.get(t, 50)
                        holdings += q * (mid/100.0)
                for src in p['inventory_no']:
                    for t, q in p['inventory_no'][src].items():
                        mid = last_prices.get(t, 50)
                        holdings += q * ((100-mid)/100.0)
                
                total_equity = cash + holdings
                daily_report[s.name] = {'start': INITIAL_CAPITAL, 'equity': total_equity}
                
                # Track for performance chart
                if not hasattr(self, 'daily_equity_history'):
                    self.daily_equity_history = defaultdict(list)
                self.daily_equity_history[s.name].append({
                    'date': date_str, 
                    'equity': total_equity,
                    'spendable_cash': p['wallet'].available_cash
                })
                
            self.generate_daily_chart(df, daily_trades_viz, daily_report, date_str, last_prices)
            
        print("\n=== FINAL RESULTS (V6 KALSHI REALITY) ===")
        for s in self.strategies:
            p = self.portfolios[s.name]
            cash_eq = p['wallet'].get_total_equity()
            holdings_val = 0
            
            # Sum all YES sources
            for src in p['inventory_yes']:
                for t, q in p['inventory_yes'][src].items():
                   mid = last_prices.get(t, 50)
                   holdings_val += q * (mid/100.0)

            # Sum all NO sources
            for src in p['inventory_no']:
                for t, q in p['inventory_no'][src].items():
                   mid = last_prices.get(t, 50)
                   holdings_val += q * ((100-mid)/100.0)
            
            total = cash_eq + holdings_val
            roi = (total / INITIAL_CAPITAL - 1) * 100
            
            trade_sources = defaultdict(int)
            for t in p['trades']: trade_sources[t['source']] += 1
            
            print(f"Strategy {s.name}: Total ${total:.2f} | ROI {roi:+.1f}% | Trades {len(p['trades'])}")
            print(f"  PnL Source Mix (Trade Count): {dict(trade_sources)}")
            
            if p['trades']: pd.DataFrame(p['trades']).to_csv("debug_trades_v8_victory.csv", index=False)
            
        if equity_history:
            peak = equity_history[0]
            max_dd = 0
            for val in equity_history:
                if val > peak: peak = val
                dd = (peak - val) / peak
                if dd > max_dd: max_dd = dd
            print(f"Portfolio Max Drawdown: {max_dd*100:.1f}%")
            
        self.generate_performance_chart()

    def generate_performance_chart(self):
        if not hasattr(self, 'daily_equity_history'): return
        
        fig = go.Figure()
        
        for strat_name, history in self.daily_equity_history.items():
            dates = [h['date'] for h in history]
            equities = [h['equity'] for h in history]
            spendable = [h['spendable_cash'] for h in history]
            
            # Plot NAV
            fig.add_trace(go.Scatter(
                x=dates, 
                y=equities, 
                mode='lines+markers', 
                name=f"{strat_name} (NAV)"
            ))
            
            # Plot Spendable Cash
            fig.add_trace(go.Scatter(
                x=dates, 
                y=spendable, 
                mode='lines+markers', 
                name=f"{strat_name} (Spendable Cash)",
                line=dict(dash='dot')
            ))
            
        fig.update_layout(
            title="Strategy Value Over Time (Daily MTM Equity)",
            xaxis_title="Date",
            yaxis_title="Total Equity ($)",
            hovermode="x unified",
            height=800
        )
        
        # Add baseline
        fig.add_hline(y=INITIAL_CAPITAL, line_dash="dash", line_color="gray", annotation_text="Initial Capital")
        
        filename = os.path.join(CHARTS_DIR, "final_performance_v3.html")
        fig.write_html(filename)
        print(f"Generated final performance chart: {filename}")

    def generate_daily_chart(self, df, trades, daily_report, date_str, last_prices):
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.6, 0.15, 0.25], subplot_titles=(f"V3 Market & Trades - {date_str}", "Daily Performance", "Trade Log"), specs=[[{"type": "xy"}], [{"type": "table"}], [{"type": "table"}]])
        tickers = df['market_ticker'].unique()[:15]
        for t in tickers:
            m = df[df['market_ticker'] == t]
            fig.add_trace(go.Scatter(x=m['timestamp'], y=m['implied_no_ask'], mode='lines', name=t, opacity=0.4), row=1, col=1)
        for t in trades[:500]:
            color = 'blue' if 'BUY' in t['action'] else 'red'
            symbol = 'circle' if t['source'] == 'MM' else 'diamond'
            fig.add_trace(go.Scatter(x=[t['time']], y=[t['viz_y']], mode='markers', marker=dict(color=color, size=9, symbol=symbol), name=f"{t['source']} {t['action']}"), row=1, col=1)
        fig.add_trace(go.Table(header=dict(values=["Strategy", "End Equity (MTM)"]), cells=dict(values=list(zip(*[[s, f"${d['equity']:.2f}"] for s, d in daily_report.items()])))), row=2, col=1)
        
        # Trade Log
        trade_data = []
        chart_time = df['datetime'].max() if not df.empty else datetime.now()
        
        for t in trades:
            end_price = last_prices.get(t['ticker'], np.nan)
            
            # Sanitize only if market has ended
            end_t = market_end_time_from_ticker(t['ticker'])
            if end_t and chart_time >= end_t:
                end_price = sanitize_price(end_price)
            
            roi = np.nan
            if not pd.isna(end_price):
                val = end_price if 'YES' in t['action'] else (100 - end_price)
                roi = ((val / 100.0 * t['qty']) - t['cost']) / t['cost']
            
            trade_data.append([
                t['time'].strftime("%H:%M"), 
                t['ticker'], 
                t['source'],
                t['action'], 
                f"{t['price']}c", 
                t['qty'],
                f"${t['cost']:.2f}",
                f"{end_price:.1f}c" if not pd.isna(end_price) else "-",
                f"{roi*100:+.1f}%" if not pd.isna(roi) else "-"
            ])
            
        fig.add_trace(go.Table(
            header=dict(values=["Time", "Ticker", "Source", "Action", "Price", "Qty", "Cost", "End Price", "ROI"]),
            cells=dict(values=list(zip(*trade_data)))
        ), row=3, col=1)
        
        fig.update_layout(height=1000, title_text=f"Complex V3: {date_str}")
        fig.write_html(os.path.join(CHARTS_DIR, f"complex_v3_{date_str}.html"))

if __name__ == "__main__":
    ComplexBacktester().run()
