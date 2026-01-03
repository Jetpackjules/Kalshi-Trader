import pandas as pd
import os
import glob
from datetime import timedelta
from multi_strategy_backtest import (
    HumanReadableBacktester, 
    Strategy, 
    ParametricStrategy, 
    MomentumStrategy, 
    Wallet, 
    INITIAL_CAPITAL, 
    CHARTS_DIR
)

# --- Configuration ---
OPTIMIZATION_RESULTS_FILE = "optimization_results.csv"
FAST_MODE = True # Set to False for FULL Grid Search (Takes Hours)

class OptimizerBacktester(HumanReadableBacktester):
    def __init__(self, strategies):
        # Initialize parent but don't let it set up default strategies
        self.strategies = strategies
        
        # Initialize Portfolios
        self.portfolios = {}
        for s in self.strategies:
            self.portfolios[s.name] = {
                'wallet': Wallet(INITIAL_CAPITAL),
                'cash': INITIAL_CAPITAL,
                'holdings': [],
                'trades': [],
                'daily_start_cash': INITIAL_CAPITAL,
                'spent_today': 0.0
            }
        
        if not os.path.exists(CHARTS_DIR): os.makedirs(CHARTS_DIR)
        self.performance_history = []

    def generate_report(self):
        # Override to save CSV results
        results = []
        for name, p in self.portfolios.items():
            final_capital = p['wallet'].get_total_equity()
            roi = ((final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
            num_trades = len(p['trades'])
            results.append({
                'Strategy': name,
                'Final Capital': final_capital,
                'ROI': roi,
                'Trades': num_trades
            })
        
        df = pd.DataFrame(results)
        df = df.sort_values('ROI', ascending=False)
        
        print("\n=== Optimization Results (Top 10) ===")
        print(df.head(10).to_string(index=False))
        
        df.to_csv(OPTIMIZATION_RESULTS_FILE, index=False)
        print(f"\nFull results saved to {OPTIMIZATION_RESULTS_FILE}")

def generate_strategies():
    strategies = []
    
    if FAST_MODE:
        print("⚠️  FAST_MODE is ON. Running small grid for testing.")
        # 1. Momentum Surfer (Small)
        drop_thresholds = [10, 15]
        lookback_minutes = [30, 60]
        # 2. OG Fast (Small)
        wait_times = [90, 120]
        max_prices = [60, 70, 80]
    else:
        print("🚀 FAST_MODE is OFF. Running FULL Grid Search.")
        # 1. Momentum Surfer (Full)
        drop_thresholds = [5, 8, 10, 12, 15]
        lookback_minutes = [15, 30, 45, 60, 90, 120]
        # 2. OG Fast (Full)
        wait_times = [30, 60, 90, 120, 150, 180, 240]
        max_prices = [60, 65, 70, 75, 80, 85]
    
    for drop in drop_thresholds:
        for lookback in lookback_minutes:
            name = f"Momentum_Drop{drop}c_Look{lookback}m"
            strategies.append(MomentumStrategy(
                name,
                drop_threshold=drop,
                lookback_minutes=lookback,
                risk_pct=0.5,
                freshness_tolerance=None
            ))
            
    for wait in wait_times:
        for max_p in max_prices:
            name = f"OG_Fast_Wait{wait}m_Max{max_p}"
            strategies.append(ParametricStrategy(
                name,
                wait_minutes=wait,
                risk_pct=0.5,
                logic_type="trend_no",
                freshness_tolerance=timedelta(seconds=1),
                min_price=50,
                max_price=max_p
            ))
        
    # 3. Baseline (Originals)
    strategies.append(ParametricStrategy(
        "BASELINE_OG_Fast_120m", 
        wait_minutes=120, 
        risk_pct=0.5, 
        logic_type="trend_no", 
        freshness_tolerance=timedelta(seconds=1)
    ))
    
    strategies.append(MomentumStrategy(
        "BASELINE_Momentum_10c_60m",
        drop_threshold=10,
        lookback_minutes=60,
        risk_pct=0.5,
        freshness_tolerance=None
    ))

    return strategies

if __name__ == "__main__":
    print("Generating optimization grid...")
    strategies = generate_strategies()
    print(f"Created {len(strategies)} strategy variants.")
    
    print("Initializing Optimizer Backtester...")
    optimizer = OptimizerBacktester(strategies)
    
    print("Running optimization...")
    optimizer.run()
