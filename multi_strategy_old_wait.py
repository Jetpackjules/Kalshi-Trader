import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import os
import glob
from datetime import datetime, timedelta
import sys

# --- Configuration ---
LOG_DIR = r"C:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
CHARTS_DIR = "backtest_charts"
INITIAL_CAPITAL = 100.0

# --- Strategies ---

class Strategy:
    def __init__(self, name, risk_pct=0.8):
        self.name = name
        self.risk_pct = risk_pct
        self.start_time = None
        
    def start_new_day(self, first_timestamp):
        self.start_time = first_timestamp
        
    def on_tick(self, market, current_temp, market_price, current_time):
        return "HOLD"

class ParametricStrategy(Strategy):
    """
    A configurable strategy that waits for X time and then trades based on logic.
    """
    def __init__(self, name, wait_minutes, risk_pct, logic_type="trend_no", greedy=False):
        super().__init__(name, risk_pct)
        self.wait_minutes = wait_minutes
        self.logic_type = logic_type
        self.greedy = greedy
        
    def on_tick(self, market, current_temp, market_price, current_time):
        # 1. Wait Logic
        if self.start_time is None: return "HOLD"
        if current_time < (self.start_time + timedelta(minutes=self.wait_minutes)):
            return "HOLD"
            
        # 2. Trade Logic
        if self.logic_type == "trend_no":
            no_price = 100 - market_price
            if 50 < no_price < 70: return "BUY_NO"
            
        return "HOLD"

class MarketConditionStrategy(Strategy):
    """
    Trigger based strategy. Example: If 3 markets > 40% NO, buy the cheapest one.
    (Placeholder for now, implementing basic logic)
    """
    def __init__(self, name, risk_pct):
        super().__init__(name, risk_pct)
        
    def on_tick(self, market, current_temp, market_price, current_time):
        # Placeholder logic
        return "HOLD"

# --- Helper Functions ---

def parse_ticker(ticker):
    """Extracts label, temp value, and type from ticker string."""
    try:
        parts = ticker.split('-')
        suffix = parts[-1]
        type_char = suffix[0] # T or B
        val = float(suffix[1:])
        label = f"{'≥' if type_char == 'T' else '<'}{val:.1f}°F"
        return label, val, type_char
    except:
        return ticker, 0, '?'

def get_market_details(ticker):
    try:
        parts = ticker.split('-')
        suffix = parts[-1]
        type_char = suffix[0]
        val = float(suffix[1:])
        if type_char == 'T': return {'strike_type': 'greater', 'floor_strike': val, 'cap_strike': None}
        else: return {'strike_type': 'less', 'floor_strike': None, 'cap_strike': val}
    except:
        return {}

def sanitize_data(df):
    """
    Forces EOD prices to 0 or 100 if they end near those values.
    Prevents fake 1% returns on losing bets.
    """
    sanitized_rows = []
    last_timestamp = df['timestamp'].iloc[-1]
    
    # Group by ticker to find the last known state of each market
    for ticker, group in df.groupby('market_ticker'):
        last_row = group.iloc[-1]
        no_ask = last_row.get('implied_no_ask', np.nan)
        
        if pd.isna(no_ask): continue
        
        new_row = last_row.copy()
        new_row['timestamp'] = last_timestamp # Align timestamps
        
        if no_ask > 95:
            # Market likely ended YES=0, NO=100
            new_row['implied_yes_ask'] = 0
            new_row['implied_no_ask'] = 100
            sanitized_rows.append(new_row)
        elif no_ask < 5:
            # Market likely ended YES=100, NO=0
            new_row['implied_yes_ask'] = 100
            new_row['implied_no_ask'] = 0
            sanitized_rows.append(new_row)
            
    if sanitized_rows:
        # Append sanitized rows to the dataframe
        sanitized_df = pd.DataFrame(sanitized_rows)
        df = pd.concat([df, sanitized_df], ignore_index=True)
        df = df.sort_values('timestamp')
        
    return df

# --- Main Backtester Class ---

class HumanReadableBacktester:
    def __init__(self):
        self.strategies = []
        
        # --- GENERATE STRATEGIES ---
        
        # --- SENSITIVITY MICRO-SWEEP ---
        # Testing the "Cliff" around 8.5 hours
        wait_times = [480, 495, 510, 525, 540] # 8h, 8.25h, 8.5h, 8.75h, 9h
        wait_times = [t + (60*24) for t in wait_times]
        risk = 0.8
        
        for wait in wait_times:
            name = f"Wait {wait}m ({wait/60:.2f}h) | Risk 80% | GREEDY"
            self.strategies.append(ParametricStrategy(name, wait, risk, "trend_no", greedy=True))
            
        # Add Safe Baseline
        self.strategies.append(ParametricStrategy("Safe Baseline (Wait 120m | Risk 50%)", 120, 0.5, "trend_no", greedy=False))
                
        # 2. Original Best Performers (for comparison)
        self.strategies.append(ParametricStrategy("Original Trend Follow (No Wait)", 0, 0.8, "trend_no"))

        print(f"Generated {len(self.strategies)} strategies.")

        # Portfolio: {StrategyName: {'cash': 100.0, 'holdings': [], 'history': []}}
        self.portfolios = {
            s.name: {'cash': INITIAL_CAPITAL, 'holdings': [], 'trades': [], 'spent_today': 0.0} 
            for s in self.strategies
        }
        if not os.path.exists(CHARTS_DIR): os.makedirs(CHARTS_DIR)

    def run(self):
        print("=== Starting Parametric Backtest ===")
        
        # 1. Find Log Files (Specific Range: Dec 07 - Dec 11)
        files = sorted(glob.glob(os.path.join(LOG_DIR, "market_data_*.csv")))
        if not files:
            print("No log files found!")
            return
            
        # Filter for specific dates
        target_dates = ["25DEC17"]
        recent_files = [f for f in files if any(d in f for d in target_dates)]
        
        print(f"Processing {len(recent_files)} days of data (Dec 17)...")

        # 2. Loop Through Each Day
        for csv_file in recent_files:
            self.process_day(csv_file)

        self.generate_report()
        
        # Save Trades to CSV
        all_trades = []
        for name, p in self.portfolios.items():
            for t in p['trades']:
                t['strategy'] = name
                all_trades.append(t)
        
        if all_trades:
            pd.DataFrame(all_trades).to_csv("trades_og.csv", index=False)
            print("Saved trades to trades_og.csv")
            
        print("=== Backtest Complete ===")

    def process_day(self, csv_file):
        date_str = os.path.basename(csv_file).split('-')[-1].replace('.csv', '')
        print(f"Processing {date_str}...", end='\r')
        
        # Load Data
        try:
            df = pd.read_csv(csv_file, on_bad_lines='skip')
        except:
            return

        if df.empty: return

        # Preprocess Data
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')
        
        # SANITIZE DATA (Force 0/100)
        df = sanitize_data(df)
        
        # Notify strategies of new day start & Reset Daily Spend
        first_timestamp = df['timestamp'].iloc[0]
        for s in self.strategies:
            s.start_new_day(first_timestamp)
            self.portfolios[s.name]['spent_today'] = 0.0 # Reset daily budget tracker
            # Set start cash for today (for reporting and budget)
            self.portfolios[s.name]['daily_start_cash'] = self.portfolios[s.name]['cash']

        # Track trades for viz
        daily_trades_viz = []

        # --- SIMULATION LOOP ---
        # To speed up, we iterate row by row.
        
        # We will track trades for visualization
        daily_trades_viz = []
        
        for index, row in df.iterrows():
            ticker = row['market_ticker']
            current_temp = -999 
            current_time = row['timestamp']
            yes_ask = row.get('implied_yes_ask', np.nan)
            no_ask = row.get('implied_no_ask', np.nan)
            market_info = get_market_details(ticker)
            
            for strategy in self.strategies:
                if pd.isna(yes_ask) and pd.isna(no_ask): continue
                price_for_strat = yes_ask if not pd.isna(yes_ask) else (100 - no_ask)
                
                action = strategy.on_tick(market_info, current_temp, price_for_strat, current_time)
                
                if action != "HOLD":
                    self.execute_trade(strategy, action, ticker, yes_ask, no_ask, current_time, daily_trades_viz)

        # End of Day Settlement
        self.settle_eod(df, daily_trades_viz)
        
        # Generate Chart for this day (Only for key strategies)
        # We focus on the "Winner" strategies to keep chart readable
        key_strategies = ["Wait 510m (8.50h) | Risk 80% | GREEDY", "Safe Baseline (Wait 120m | Risk 50%)"]
        
        # Filter portfolios for report
        daily_report = {name: {'start': p['daily_start_cash'], 'end': p['cash']} 
                        for name, p in self.portfolios.items() if name in key_strategies}
                        
        self.generate_daily_chart(df, daily_trades_viz, daily_report, date_str, key_strategies)
        
    def execute_trade(self, strategy, action, ticker, yes_ask, no_ask, timestamp, daily_trades_viz):
        portfolio = self.portfolios[strategy.name]
        cash = portfolio['cash']
        
        # Determine Cost and Price
        if action == "BUY_YES":
            if pd.isna(yes_ask): return
            price = yes_ask
            side = 'yes'
        elif action == "BUY_NO":
            if pd.isna(no_ask): return
            price = no_ask
            side = 'no'
        else:
            return

        # --- DAILY BUDGET CAP LOGIC ---
        # Max spend per day = Risk % of STARTING capital for that day.
        # But wait, 'cash' changes. We need to track 'starting_cash_today'.
        # Actually, simpler: Max spend = Current Cash * Risk %. 
        # BUT user said: "if we do 3 trades, they should never exceed a combined money down of 80 bucks"
        # So we need a fixed budget for the day based on the START of the day.
        # Let's approximate: Budget = (Cash at start of day) * Risk %.
        # We need to track 'cash_at_start_of_day'.
        # Let's add that to portfolio state.
        
        # For now, let's use the current cash implementation but enforce the "spent_today" limit.
        # If we haven't tracked start cash, let's assume Budget = Current Cash * Risk for the FIRST trade, 
        # and then subsequent trades share that budget?
        # No, user wants: "Max invested in a single day... scaled off 80 bucks".
        # So: Daily Budget = Portfolio Value * Risk %.
        # We need to calculate this at start of day.
        
        # Let's calculate budget dynamically:
        # Budget = (Cash + Invested) * Risk %.
        # Since we sell everything at EOD, Cash at start of day == Total Value.
        # So we can just use `portfolio['cash']` at the start of the day (before any trades).
        # We need to store `daily_start_cash`.
        
        daily_start_cash = portfolio.get('daily_start_cash', cash) # Default to current if not set
        # Wait, we need to set this in process_day.
        
        daily_budget = daily_start_cash * strategy.risk_pct
        spent_so_far = portfolio['spent_today']
        
        # GREEDY MODE: Ignore daily budget cap, just use current cash * risk
        if getattr(strategy, 'greedy', False):
            # Greedy: Spend risk_pct of CURRENT cash
            max_spend = cash * strategy.risk_pct
        else:
            # Normal: Cap total daily spend at daily_budget
            if spent_so_far >= daily_budget:
                return # Cap hit
            
            available_to_spend = daily_budget - spent_so_far
            if available_to_spend < 1.0: return # Too small
            max_spend = min(available_to_spend, cash)
        
        # Calculate Qty
        # Price is in cents. Cost = Qty * (Price/100).
        # Qty = Max Spend / (Price/100)
        qty = int(max_spend // (price / 100.0))
        cost = qty * (price / 100.0)
        
        if qty > 0:
            portfolio['cash'] -= cost
            portfolio['spent_today'] += cost
            portfolio['holdings'].append({
                'ticker': ticker, 'side': side, 'qty': qty, 'price': price, 'cost': cost
            })
            portfolio['trades'].append({
                'time': timestamp, 'action': action, 'ticker': ticker, 'price': price, 'qty': qty, 'cost': cost,
                'capital_after': portfolio['cash']
            })
            
            # Log for Viz
            daily_trades_viz.append({
                'time': timestamp, 'strategy': strategy.name, 'action': action, 'ticker': ticker,
                'price': price, 'qty': qty, 'cost': cost
            })

    def settle_eod(self, df, daily_trades_viz):
        last_prices = {}
        last_rows = df.groupby('market_ticker').last()
        for ticker, row in last_rows.iterrows():
            last_prices[ticker] = {
                'yes': row.get('implied_yes_ask', 0),
                'no': row.get('implied_no_ask', 0)
            }
            
        for name, p in self.portfolios.items():
            # Set daily start cash for NEXT day (since we are about to settle this one)
            # Actually, we should set it at the START of process_day.
            # But we can update it here for the next loop.
            
            new_holdings = []
            for pos in p['holdings']:
                ticker = pos['ticker']
                if ticker in last_prices:
                    prices = last_prices[ticker]
                    exit_price = prices['yes'] if pos['side'] == 'yes' else prices['no']
                    if pd.isna(exit_price): exit_price = 0
                    value = pos['qty'] * (exit_price / 100.0)
                    p['cash'] += value
                    
                    # Update Trade PnL
                    for t in p['trades']:
                        if t.get('pnl') is None and t['ticker'] == ticker:
                            t['exit_price'] = exit_price
                            t['pnl'] = value - t['cost']
                else:
                    new_holdings.append(pos)
            p['holdings'] = new_holdings
            
            p['holdings'] = new_holdings

        # Update Viz Trades PnL
        for t in daily_trades_viz:
            if t['ticker'] in last_prices:
                prices = last_prices[t['ticker']]
                exit_price = prices['yes'] if 'YES' in t['action'] else prices['no']
                if pd.isna(exit_price): exit_price = 0
                value = t['qty'] * (exit_price / 100.0)
                t['exit_price'] = exit_price
                t['pnl'] = value - t['cost']

    def generate_daily_chart(self, df, trades, daily_report, date_str, key_strategies):
        # Filter trades for key strategies
        trades = [t for t in trades if t['strategy'] in key_strategies]
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.6, 0.15, 0.25],
            subplot_titles=(f"Market Activity & Trades - {date_str}", "Daily Strategy Performance", "Detailed Trade Log"),
            specs=[[{"type": "xy"}], [{"type": "table"}], [{"type": "table"}]]
        )
        
        # 1. Market Lines (Step Chart)
        colors = px.colors.qualitative.Plotly
        ticker_map = {t: i for i, t in enumerate(df['market_ticker'].unique())}
        
        for ticker in df['market_ticker'].unique():
            market_data = df[df['market_ticker'] == ticker]
            if market_data.empty: continue
            
            # Use NO price (100 - YES) or direct NO ask
            # We want to show the price we are trading on.
            # Since we trade NO, let's show NO Ask.
            # If NO Ask is missing, use 100 - YES Ask.
            
            # Construct a continuous price series for plotting
            # We need to handle NaNs.
            # Let's just plot 'implied_no_ask'
            
            fig.add_trace(
                go.Scatter(
                    x=market_data['timestamp'], 
                    y=market_data['implied_no_ask'],
                    mode='lines',
                    name=ticker,
                    line_shape='hv', # Step chart
                    line=dict(width=1.5),
                    opacity=0.7
                ),
                row=1, col=1
            )
            
        # 2. Trade Markers
        for t in trades:
            color = 'red' if 'NO' in t['action'] else 'green'
            symbol = 'circle'
            
            # Tooltip
            hover_text = (
                f"<b>{t['strategy']}</b><br>"
                f"{t['action']} {t['ticker']}<br>"
                f"Price: {t['price']:.0f}¢<br>"
                f"Qty: {t['qty']}<br>"
                f"Cost: ${t['cost']:.2f}<br>"
            )
            
            fig.add_trace(
                go.Scatter(
                    x=[t['time']],
                    y=[t['price']],
                    mode='markers',
                    marker=dict(color=color, size=10, symbol=symbol, line=dict(width=2, color='black')),
                    name=f"Trade: {t['strategy']}",
                    text=hover_text,
                    hoverinfo='text',
                    showlegend=False
                ),
                row=1, col=1
            )

        # 3. Daily Report Table
        report_data = []
        for strat, data in daily_report.items():
            pnl = data['end'] - data['start']
            pnl_pct = (pnl / data['start']) * 100 if data['start'] > 0 else 0
            report_data.append([strat, f"${data['start']:.2f}", f"${data['end']:.2f}", f"${pnl:.2f} ({pnl_pct:.1f}%)"])
            
        fig.add_trace(
            go.Table(
                header=dict(values=["Strategy", "Start Capital", "End Capital", "PnL"],
                            fill_color='paleturquoise', align='left'),
                cells=dict(values=list(zip(*report_data)),
                           fill_color='lavender', align='left')
            ),
            row=2, col=1
        )

        # 4. Detailed Trade Table
        day_trades_data = []
        for t in trades:
            pnl_str = f"${t.get('pnl', 0):.2f}"
            day_trades_data.append([
                t['time'].strftime("%H:%M"),
                t['strategy'],
                t['ticker'],
                t['action'],
                f"{t['price']:.0f}¢",
                t['qty'],
                f"${t['cost']:.2f}",
                f"{t.get('exit_price', 0):.0f}¢",
                pnl_str
            ])
        
        day_trades_data.sort(key=lambda x: x[0])
        
        if day_trades_data:
            headers = ["Time", "Strategy", "Ticker", "Action", "Entry", "Qty", "Cost", "Exit (EOD)", "PnL"]
            fig.add_trace(
                go.Table(
                    header=dict(values=headers,
                                fill_color='paleturquoise', align='left'),
                    cells=dict(values=list(zip(*day_trades_data)),
                               fill_color='lavender', align='left')
                ),
                row=3, col=1
            )
        else:
            fig.add_trace(
                go.Table(
                    header=dict(values=["No Trades Executed Today"], fill_color='lightgrey', align='center'),
                    cells=dict(values=[], fill_color='white', align='center')
                ),
                row=3, col=1
            )

        fig.update_layout(
            height=1200,
            title_text=f"Backtest Report: {date_str}",
            hovermode="closest"
        )
        fig.update_yaxes(title_text="Price / Prob", range=[0, 100], row=1, col=1)
        
        filename = os.path.join(CHARTS_DIR, f"backtest_{date_str}.html")
        fig.write_html(filename)
        # print(f"Chart saved: {filename}")

    def generate_report(self):
        print("\n=== Final Leaderboard (Top 20) ===")
        print(f"\n{'Strategy':<40} | {'Final $':<10} | {'ROI':<8} | {'Trades':<7}")
        print("-" * 75)
        
        results = []
        for name, res in self.portfolios.items():
            final_capital = res['cash']
            pnl = final_capital - INITIAL_CAPITAL
            roi = (pnl / INITIAL_CAPITAL) * 100
            num_trades = len(res['trades'])
            results.append((name, final_capital, roi, num_trades))
            
        results.sort(key=lambda x: x[2], reverse=True)
        
        for name, final_capital, roi, num_trades in results[:20]:
            print(f"{name:<40} | ${final_capital:<9.2f} | {roi:>6.1f}% | {num_trades:<7}")
            
        # Save Full Report
        with open('backtest_report_parametric.txt', 'w') as f:
            f.write("=== PARAMETRIC BACKTEST REPORT ===\n")
            f.write(f"Strategies Tested: {len(self.strategies)}\n\n")
            f.write(f"{'Strategy':<40} | {'Final $':<10} | {'ROI':<8} | {'Trades':<7}\n")
            f.write("-" * 75 + "\n")
            for name, final_capital, roi, num_trades in results:
                f.write(f"{name:<40} | ${final_capital:<9.2f} | {roi:>6.1f}% | {num_trades:<7}\n")

if __name__ == "__main__":
    backtester = HumanReadableBacktester()
    backtester.run()
