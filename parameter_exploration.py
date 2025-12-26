import pandas as pd
import plotly.graph_objects as go
import complex_strategy_backtest as csb
from collections import defaultdict

# --- CONFIGURATION OVERRIDES ---
csb.INITIAL_CAPITAL = 1000.00
csb.START_DATE = None 
csb.END_DATE = None

# Custom Trading Windows
# Default: (5 <= h <= 8) or (13 <= h <= 17) or (21 <= h <= 23)
# Approx: 5,6,7,8, 13,14,15,16,17, 21,22,23
DEFAULT_HOURS = [5,6,7,8, 13,14,15,16,17, 21,22,23]

# Extended: 5AM to Midnight
EXTENDED_HOURS = list(range(5, 24))

# Morning Only: 5AM - 10AM
MORNING_ONLY = [5,6,7,8,9,10]

scenarios = [
    # --- BASELINE SCENARIOS (From Previous Test) ---
    {"name": "Day-Only (Default Hours)", "midnight_filter": True, "kwargs": {"active_hours": DEFAULT_HOURS}},
    {"name": "Regular (Default Hours)", "midnight_filter": False, "kwargs": {"active_hours": DEFAULT_HOURS}},
    
    # --- RISK VARIATIONS (On top of Day-Only Winner) ---
    {"name": "Day-Only (Risk 10%)", "midnight_filter": True, "kwargs": {"active_hours": DEFAULT_HOURS, "risk_pct": 0.1}},
    {"name": "Day-Only (Risk 90%)", "midnight_filter": True, "kwargs": {"active_hours": DEFAULT_HOURS, "risk_pct": 0.9}},
    
    # --- TIME WINDOW VARIATIONS (On top of Day-Only Winner) ---
    {"name": "Day-Only (Extended 05:00-24:00)", "midnight_filter": True, "kwargs": {"active_hours": EXTENDED_HOURS}},
    {"name": "Day-Only (Morning Only 05:00-10:00)", "midnight_filter": True, "kwargs": {"active_hours": MORNING_ONLY}},
    
    # --- AGGRESSIVENESS VARIATIONS (On top of Day-Only Winner) ---
    # "inventory_penalty": Lower = More willing to hold inventory
    {"name": "Day-Only (Low Inv Penalty 0.01)", "midnight_filter": True, "kwargs": {"active_hours": DEFAULT_HOURS, "inventory_penalty": 0.01}},
    # "max_offset": Higher = Willing to quote further out? Actually used for skew logic.
]

results = {}

print("Starting Comparative Parameter Sweep...")

for scen in scenarios:
    print(f"\n--- Running Scenario: {scen['name']} ---")
    
    # Instantiate Backtester with Filter and Kwargs
    # Strategy args are passed via **scen['kwargs']
    bt = csb.ComplexBacktester(start_time_midnight_filter=scen["midnight_filter"], **scen['kwargs'])
    
    # Run
    bt.run()
    
    # Extract Equity Curve
    strat_name = "Algo 3: Regime Switcher (Meta)"
    if hasattr(bt, 'daily_equity_history') and strat_name in bt.daily_equity_history:
        results[scen['name']] = bt.daily_equity_history[strat_name]
    else:
        print(f"WARNING: No history found for scenario {scen['name']}")

# --- GENERATE CHART ---
print("\nGenerating Comprehensive Chart...")
fig = go.Figure()

# Auto-color generator
import plotly.colors as pcolors
color_cycle = pcolors.qualitative.Plotly + pcolors.qualitative.Bold

for i, (name, history) in enumerate(results.items()):
    dates = [h['date'] for h in history]
    rois = [((h['equity'] - csb.INITIAL_CAPITAL) / csb.INITIAL_CAPITAL) * 100.0 for h in history]
    
    # Highlight the Winner (Day-Only Default)
    width = 4 if "Day-Only (Default Hours)" in name else 2
    
    fig.add_trace(go.Scatter(
        x=dates, 
        y=rois, 
        mode='lines+markers', 
        name=name,
        line=dict(color=color_cycle[i % len(color_cycle)], width=width)
    ))

fig.update_layout(
    title="Comprehensive Parameter Sweep: ROI Analysis (20-Day Backtest)",
    xaxis_title="Date",
    yaxis_title="ROI (%)",
    template="plotly_dark",
    hovermode="x unified",
    legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
)

output_file = "backtest_charts/parameter_sweep_analysis.html"
fig.write_html(output_file)
print(f"Chart saved to: {output_file}")
