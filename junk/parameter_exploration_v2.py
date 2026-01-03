import pandas as pd
import plotly.graph_objects as go
import complex_strategy_backtest as csb
from collections import defaultdict
import plotly.colors as pcolors

csb.INITIAL_CAPITAL = 1000.00
csb.START_DATE = None 
csb.END_DATE = None

# Custom Trading Windows
DEFAULT_HOURS = [5,6,7,8, 13,14,15,16,17, 21,22,23]
GOLDEN_HOURS = [9, 10, 15, 16] # EST roughly Open/Close volatility

scenarios = [
    # 1. BASELINE (Winner from Phase 12)
    {
        "name": "Baseline (Day-Only)", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": DEFAULT_HOURS,
            "risk_pct": 0.5
        }
    },
    
    # 2. SNIPER MODE (High Selectivity, High Conviction)
    {
        "name": "Sniper Mode", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": DEFAULT_HOURS,
            "tightness_percentile": 20, # Only top 20% tightest spreads
            "margin_cents": 1.5,        # Demand 1.5c edge
            "max_notional_pct": 0.50,   # Bet big when you shoot
            "scaling_factor": 1.0,      # Scale fast
            "max_inventory": 200        # Don't hold bag
        }
    },
    
    # 3. SPRAY & PRAY (High Volume, Low Edge)
    {
        "name": "Spray & Pray", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": DEFAULT_HOURS,
            "tightness_percentile": 90, # Trade almost always
            "margin_cents": 0.1,        # 0.1c edge is enough
            "max_inventory": 2000,      # Huge capacity
            "inventory_penalty": 0.01,  # Ignore inventory risk
            "max_notional_pct": 0.10    # Small individual bets
        }
    },
    
    # 4. THE WHALE (High Risk, Deep Pockets)
    {
        "name": "The Whale", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": DEFAULT_HOURS,
            "max_notional_pct": 0.80,   # Use 80% of cash
            "max_loss_pct": 0.40,       # Risk 40% of cash on one trade
            "risk_pct": 0.80,           # General risk scalar
            "margin_cents": 0.4         # Standard edge
        }
    },
    
    # 5. INVENTORY PHOBIC (Quick flip or nothing)
    {
        "name": "Inventory Phobic", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": DEFAULT_HOURS,
            "inventory_penalty": 10.0,  # Punishment factor for holding
            "max_inventory": 100,       # Hard cap
            "scaling_factor": 2.0
        }
    },
    
    # 6. GOLDEN HOURS (Vol Capture)
    {
        "name": "Golden Hours Only", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": GOLDEN_HOURS,
            "tightness_percentile": 60,
            "max_notional_pct": 0.40
        }
    }
]

results = {}

print("Starting Expanded Parameter Sweep (Phase 13)...")

for scen in scenarios:
    print(f"\n--- Running Scenario: {scen['name']} ---")
    
    # Instantiate Backtester with Filter and Kwargs
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
print("\nGenerating Phase 13 Chart...")
fig = go.Figure()

color_cycle = pcolors.qualitative.Bold + pcolors.qualitative.Prism

for i, (name, history) in enumerate(results.items()):
    dates = [h['date'] for h in history]
    rois = [((h['equity'] - csb.INITIAL_CAPITAL) / csb.INITIAL_CAPITAL) * 100.0 for h in history]
    
    # Highlight Baseline
    width = 4 if "Baseline" in name else 2
    dash = 'solid'
    if "Sniper" in name: dash = 'dot'
    if "Whale" in name: dash = 'dash'
    
    fig.add_trace(go.Scatter(
        x=dates, 
        y=rois, 
        mode='lines+markers', 
        name=name,
        line=dict(color=color_cycle[i % len(color_cycle)], width=width, dash=dash)
    ))

fig.update_layout(
    title="Phase 13: Extreme Parameter Sweep (Personality Test)",
    xaxis_title="Date",
    yaxis_title="ROI (%)",
    template="plotly_dark",
    hovermode="x unified",
    legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
)

output_file = "backtest_charts/parameter_sweep_v2_personalities.html"
fig.write_html(output_file)
print(f"Chart saved to: {output_file}")
