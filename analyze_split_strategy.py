import pandas as pd
import os

def analyze_strategy(strategy_name):
    print(f"Analyzing Strategy: {strategy_name}")
    
    if not os.path.exists("debug_trades.csv"):
        print("Error: debug_trades.csv not found.")
        return

    df = pd.read_csv("debug_trades.csv")
    
    # Filter for strategy
    strat_df = df[df['strategy'] == strategy_name].copy()
    
    if strat_df.empty:
        print(f"No trades found for {strategy_name}")
        return

    # Convert time
    strat_df['time'] = pd.to_datetime(strat_df['time'])
    strat_df['date'] = strat_df['time'].dt.date
    
    # Calculate PnL per trade
    # Note: 'pnl' column might be NaN for entry trades, only populated for SETTLE/SELL?
    # Let's check the structure. Usually 'cost' is positive for buys. 'proceeds' for sells/settles.
    # The backtester logic:
    # Entry: cost > 0, pnl = NaN (or 0?)
    # Settle: cost = 0, proceeds > 0, pnl = proceeds - original_cost (but original cost is hard to track here easily without linking)
    # Wait, the backtester appends 'pnl' to the trade dict in 'settle_eod' and 'execute_trade' (sell).
    # For BUY trades, pnl is likely NaN or 0.
    
    # Let's look at daily aggregation
    daily_stats = []
    
    grouped = strat_df.groupby('date')
    
    cumulative_pnl = 0
    
    print(f"\n{'Date':<12} | {'PnL':<10} | {'Trades':<6} | {'Wins':<5} | {'Losses':<6} | {'Win Rate':<8}")
    print("-" * 65)
    
    for date, group in grouped:
        # PnL is only recorded on EXIT (Settle or Sell)
        # We need to sum 'pnl' column.
        day_pnl = group['pnl'].sum()
        
        # Count trades (Entries)
        entries = group[group['action'].str.contains('BUY')]
        num_trades = len(entries)
        
        # Count Wins (PnL > 0) - this is on EXITS
        exits = group[group['action'].isin(['SETTLE', 'SELL_YES', 'SELL_NO'])]
        wins = len(exits[exits['pnl'] > 0])
        losses = len(exits[exits['pnl'] <= 0])
        
        win_rate = (wins / len(exits) * 100) if len(exits) > 0 else 0
        
        cumulative_pnl += day_pnl
        
        print(f"{str(date):<12} | ${day_pnl:<9.2f} | {num_trades:<6} | {wins:<5} | {losses:<6} | {win_rate:>6.1f}%")
        
    print("-" * 65)
    print(f"Total PnL: ${cumulative_pnl:.2f}")

    # Price Analysis
    entries = strat_df[strat_df['action'].str.contains('BUY')]
    if not entries.empty:
        min_price = entries['price'].min()
        max_price = entries['price'].max()
        avg_price = entries['price'].mean()
        print(f"\n>>> PRICE ANALYSIS ({strategy_name}) <<<")
        print(f"Min Price: {min_price} cents")
        print(f"Max Price: {max_price} cents")
        print(f"Avg Price: {avg_price:.1f} cents")
        
        print(f"Trades < 20c: {len(entries[entries['price'] < 20])}")
        print(f"Trades > 80c: {len(entries[entries['price'] > 80])}") # Changed to 80c for expensive check

    # Deep Dive into Big Wins
    print("\n=== Top 5 Biggest Wins ===")
    wins_df = strat_df[strat_df['pnl'] > 0].sort_values('pnl', ascending=False).head(5)
    for _, row in wins_df.iterrows():
        # Find entry trade for details (approximate)
        # We can't easily link, but we can print the exit details
        print(f"{row['date']} {row['ticker']} ({row['action']}): +${row['pnl']:.2f} | Exit Price: {row['price']} | Qty: {row['qty']} | Cost: ${row['cost']:.2f} (Wait, cost is 0 on settle)")

    # Deep Dive into Big Losses
    print("\n=== Top 5 Biggest Losses ===")
    losses_df = strat_df[strat_df['pnl'] < 0].sort_values('pnl', ascending=True).head(5)
    for _, row in losses_df.iterrows():
         print(f"{row['date']} {row['ticker']} ({row['action']}): ${row['pnl']:.2f} | Exit Price: {row['price']} | Qty: {row['qty']}")

if __name__ == "__main__":
    analyze_strategy("Sniper: Expensive")
    # print("\n" + "="*60 + "\n")
    # analyze_strategy("Split Exp NO -> Buy YES")
