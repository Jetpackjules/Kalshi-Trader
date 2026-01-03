import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import complex_strategy_backtest
from complex_strategy_backtest import ComplexBacktester, RegimeSwitcher

# --- Configuration ---
complex_strategy_backtest.LOG_DIR = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\vm_logs\market_logs"
START_DATE = "2025-12-24"
END_DATE = "2025-12-28"
INITIAL_CAPITAL = 21.24

# Real Equity Data (from extract_real_equity.py)
REAL_EQUITY = {
    "25DEC23": 21.24,
    "25DEC24": 54.99,
    "25DEC25": 45.24,
    "25DEC26": 73.85,
    "25DEC27": 42.82
}

class LiveBotStrategy(RegimeSwitcher):
    def __init__(self):
        # Use default params that match live bot
        super().__init__("Live Bot Strategy", risk_pct=0.5)

class ComparisonBacktester(ComplexBacktester):
    def __init__(self, initial_capital=54.99):
        super().__init__(initial_capital=initial_capital)
        self.strategies = [LiveBotStrategy()]
        self.portfolios = {}
        from complex_strategy_backtest import Wallet, defaultdict
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(initial_capital),
                'inventory_yes': defaultdict(lambda: defaultdict(int)),
                'inventory_no': defaultdict(lambda: defaultdict(int)),
                'active_limit_orders': defaultdict(list),
                'trades': [],
                'pnl_by_source': defaultdict(float),
                'paid_out': set(),
                'cost_basis': defaultdict(float)
            }

if __name__ == "__main__":
    print(f"=== BACKTEST VS REAL COMPARISON ({START_DATE} to {END_DATE}) ===")
    
    # Start from Dec 23rd at 14:48:55 (Live Bot Uptime)
    START_DATE_BT = "2025-12-23 14:48:55"
    INITIAL_CAPITAL_BT = 21.24
    
    print(f"Starting Capital: ${INITIAL_CAPITAL_BT}")
    
    # Configure global params for backtester
    complex_strategy_backtest.START_DATE = START_DATE_BT
    complex_strategy_backtest.END_DATE = "25DEC30"
    complex_strategy_backtest.WARMUP_START_DATE = START_DATE_BT # Strict cold start
    complex_strategy_backtest.INITIAL_CAPITAL = INITIAL_CAPITAL_BT
    
    bt = ComparisonBacktester(initial_capital=INITIAL_CAPITAL_BT)
    bt.run()
    
    # Extract Backtest Daily Equity
    backtest_equity = {}
    if hasattr(bt, 'daily_equity_history'):
        history = bt.daily_equity_history["Live Bot Strategy"]
        for entry in history:
            backtest_equity[entry['date']] = entry['equity']
            
    # Combine Data
    all_dates = sorted(list(set(REAL_EQUITY.keys()) | set(backtest_equity.keys())))
    
    comparison_data = []
    for d in all_dates:
        real = REAL_EQUITY.get(d, np.nan)
        sim = backtest_equity.get(d, np.nan)
        diff = sim - real if not (np.isnan(sim) or np.isnan(real)) else np.nan
        comparison_data.append({
            'Date': d,
            'Real Equity': real,
            'Sim Equity': sim,
            'Difference': diff
        })
        
    df_comp = pd.DataFrame(comparison_data)
    print("\n=== COMPARISON TABLE ===")
    print(df_comp.to_string(index=False))
    
    # Generate Chart
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df_comp['Date'], 
        y=df_comp['Real Equity'], 
        mode='lines+markers', 
        name='Real Kalshi Equity',
        line=dict(color='green', width=4)
    ))
    
    fig.add_trace(go.Scatter(
        x=df_comp['Date'], 
        y=df_comp['Sim Equity'], 
        mode='lines+markers', 
        name='Backtester Equity (Immediate Fills)',
        line=dict(color='blue', width=4, dash='dash')
    ))
    
    fig.update_layout(
        title="Real Kalshi Market Values vs Backtester Performance",
        xaxis_title="Date",
        yaxis_title="Total Equity ($)",
        hovermode="x unified",
        template="plotly_dark"
    )
    
    chart_path = "real_vs_backtest_comparison.html"
    fig.write_html(chart_path)
    print(f"\nComparison chart saved to: {chart_path}")
