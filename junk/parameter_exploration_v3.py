import pandas as pd
import plotly.graph_objects as go
import complex_strategy_backtest as csb
from collections import defaultdict
import plotly.colors as pcolors

# --- CONFIGURATION OVERRIDES ---
csb.INITIAL_CAPITAL = 1000.00
csb.START_DATE = None 
csb.END_DATE = None

# Custom Trading Windows
# DEFAULT_HOURS currently in csb are: [5,6,7,8, 13,14,15,16,17, 21,22,23] (Approx)
# We will explicitly define Active Hours here to be safe.
# Assuming "Trading Hours" means excluding sleep/low-liquidity times (e.g. 11pm-5am).
ACTIVE_HOURS = [5,6,7,8, 9,10,11,12,13,14,15,16,17,18,19,20, 21,22,23] # Broad active day
GOLDEN_HOURS = [9, 10, 15, 16] 

scenarios = [
    # --- PROVEN "CORE FOUR" ---
    
    # 1. DAY-ONLY / ALL HOURS
    # "Day Trader (Insomniac)"
    # Trades only the specific market day (Day-Ahead or Day-Of). 
    # Trades 24/7 if data exists.
    {
        "name": "Core 1: Day-Only / All Hours", 
        "midnight_filter": True, 
        "kwargs": {
            "active_hours": None, # No hour filter
            "risk_pct": 0.5
        }
    },
    
    # 2. DAY-ONLY / ACTIVE HOURS ("BASELINE")
    # "Day Trader (Normal)" - The verified Baseline.
    # Trades only specific market day.
    # Sleeps at night.
    {
        "name": "Core 2: Day-Only / Active Hours", 
        "midnight_filter": True, 
        "kwargs": {
            "active_hours": ACTIVE_HOURS,
            "risk_pct": 0.5
        }
    },
    
    # 3. FULL RANGE / ALL HOURS
    # "Swing Trader (Insomniac)"
    # Starts trading as soon as market exists (days ahead).
    # Trades 24/7.
    {
        "name": "Core 3: Full Range / All Hours", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": None,
            "risk_pct": 0.5
        }
    },
    
    # 4. FULL RANGE / ACTIVE HOURS
    # "Swing Trader (Normal)"
    # Starts trading days ahead.
    # Sleeps at night.
    {
        "name": "Core 4: Full Range / Active Hours", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": ACTIVE_HOURS,
            "risk_pct": 0.5
        }
    },

    # --- PERSONALITIES (Use Full Range / Active Hours base) ---
    
    # 5. THE WHALE (High Risk)
    {
        "name": "Personality: The Whale", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": ACTIVE_HOURS,
            "max_notional_pct": 0.80,   # 80% betting
            "max_loss_pct": 0.40,
            "risk_pct": 0.80,
            "margin_cents": 0.4
        }
    },
    
    # 6. SNIPER (High Selectivity)
    {
        "name": "Personality: Sniper", 
        "midnight_filter": False, 
        "kwargs": {
            "active_hours": ACTIVE_HOURS,
            "tightness_percentile": 20, # Top 20% tightest only
            "margin_cents": 1.5,        # High edge required
            "max_notional_pct": 0.50,
            "scaling_factor": 1.0,
            "max_inventory": 200
        }
    }
]

results = {}

print("Starting Core Four + Personality Sweep (Phase 16)...")

for scen in scenarios:
    print(f"\n--- Running Scenario: {scen['name']} ---")
    
    # Instantiate Backtester with Filter and Kwargs
    bt = csb.ComplexBacktester(start_time_midnight_filter=scen["midnight_filter"], **scen['kwargs'])
    
    # Run
    # Run runs the full loop on global data
    bt.run()
    
    # Extract Equity Curve
    strat_name = "Algo 3: Regime Switcher (Meta)"
    if hasattr(bt, 'daily_equity_history') and strat_name in bt.daily_equity_history:
        results[scen['name']] = bt.daily_equity_history[strat_name]
    else:
        print(f"WARNING: No history found for scenario {scen['name']}")

# --- GENERATE CHART ---
print("\nGenerating Phase 16 Chart...")
fig = go.Figure()

color_cycle = pcolors.qualitative.Bold + pcolors.qualitative.Prism

for i, (name, history) in enumerate(results.items()):
    dates = [h['date'] for h in history]
    rois = [((h['equity'] - csb.INITIAL_CAPITAL) / csb.INITIAL_CAPITAL) * 100.0 for h in history]
    
    # Style logic
    width = 2
    dash = 'solid'
    
    if "Core 2" in name: # Baseline
        width = 4
    
    if "Personality" in name:
        dash = 'dot' if "Sniper" in name else 'dash'
    
    # Colors: Core 1-4 get distinct, Personalities get distinct
    
    fig.add_trace(go.Scatter(
        x=dates, 
        y=rois, 
        mode='lines+markers', 
        name=name,
        line=dict(width=width, dash=dash)
    ))

fig.update_layout(
    title="Phase 16: 'Core Four' + Personalities Comparison (V14 Engine)",
    xaxis_title="Date",
    yaxis_title="ROI (%)",
    template="plotly_dark",
    hovermode="x unified",
    legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
)

output_file = "backtest_charts/parameter_sweep_v3_core_four.html"
fig.write_html(output_file)
print(f"Chart saved to: {output_file}")
