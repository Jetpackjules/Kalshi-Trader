import complex_strategy_backtest
from complex_strategy_backtest import ComplexBacktester
import pandas as pd
import numpy as np

# Configure for Dec 24th
complex_strategy_backtest.START_DATE = "25DEC24"
complex_strategy_backtest.END_DATE = "25DEC24"
complex_strategy_backtest.WARMUP_START_DATE = "2025-12-22"
INITIAL_CAPITAL = 21.24

bt = ComplexBacktester(initial_capital=INITIAL_CAPITAL)
bt.run()

portfolio = bt.portfolios["Algo 3: Regime Switcher (Meta)"]
trades = portfolio["trades"]

print(f"\n=== DEC 24th TRADE ANALYSIS ===")
print(f"Initial Capital: ${INITIAL_CAPITAL}")
print(f"Final Equity: ${portfolio['wallet'].get_total_equity():.2f}")

if not trades:
    print("No trades executed on Dec 24th.")
else:
    df_trades = pd.DataFrame(trades)
    print(f"\nTotal Trades: {len(df_trades)}")
    
    # Group by ticker
    for ticker, group in df_trades.groupby('ticker'):
        total_qty = group['qty'].sum()
        total_cost = group['cost'].sum()
        avg_price = (total_cost / total_qty) * 100 if total_qty > 0 else 0
        print(f"\nTicker: {ticker}")
        print(f"  Total Qty: {total_qty}")
        print(f"  Total Cost: ${total_cost:.2f}")
        print(f"  Avg Price: {avg_price:.2f}c")
        
        # Show first few fills
        print("  First 5 fills:")
        for i, row in group.head(5).iterrows():
            print(f"    {row['time']} | {row['action']} | {row['qty']} @ {row['price']}c | Cost: ${row['cost']:.2f} | Cap After: ${row['capital_after']:.2f}")

# Check for Budget Rejects in output (captured by running the script)
