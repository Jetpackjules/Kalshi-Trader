import pandas as pd

def find_hedged_trades():
    try:
        df = pd.read_csv("vm_logs/unified_engine_out/trades.csv")
        
        # Ensure columns exist
        required = {'ticker', 'action', 'time', 'price', 'qty'}
        if not required.issubset(df.columns):
            print(f"Missing columns. Found: {df.columns}")
            return

        # Group by ticker
        grouped = df.groupby('ticker')
        
        found_example = False
        
        print("Searching for tickers with both BUY_YES and BUY_NO...")
        
        for ticker, group in grouped:
            actions = set(group['action'].unique())
            if 'BUY_YES' in actions and 'BUY_NO' in actions:
                print(f"\nFOUND MATCH: {ticker}")
                print("-" * 40)
                
                # Show the buys
                yes_trades = group[group['action'] == 'BUY_YES'].sort_values('time')
                no_trades = group[group['action'] == 'BUY_NO'].sort_values('time')
                
                print("BUY YES Trades:")
                print(yes_trades[['time', 'price', 'qty', 'cost']].head(3).to_string(index=False))
                
                print("\nBUY NO Trades:")
                print(no_trades[['time', 'price', 'qty', 'cost']].head(3).to_string(index=False))
                
                # Calculate rough PnL for this ticker
                # Cost is positive for buys.
                # If we bought YES at 30 and NO at 60, total cost 90. Payout 100. Profit 10.
                total_cost = group['cost'].sum()
                
                # Count completed pairs (roughly)
                yes_vol = yes_trades['qty'].sum()
                no_vol = no_trades['qty'].sum()
                matched_vol = min(yes_vol, no_vol)
                
                print(f"\nStats for {ticker}:")
                print(f"  Total YES Volume: {yes_vol}")
                print(f"  Total NO Volume:  {no_vol}")
                print(f"  Matched Volume:   {matched_vol}")
                print(f"  Total Spent:      ${total_cost:.2f}")
                
                # If we matched volume, we got $1.00 per matched contract back?
                # Wait, payout is $1.00 per YES+NO pair.
                # So Revenue = matched_vol * 1.00
                revenue = matched_vol * 1.00
                
                # But we might still hold the unmatched portion.
                # Value of unmatched = unmatched_vol * current_price (unknown)
                # But let's look at Realized PnL on the matched portion.
                # Avg YES price
                avg_yes = (yes_trades['price'] * yes_trades['qty']).sum() / yes_vol if yes_vol else 0
                avg_no = (no_trades['price'] * no_trades['qty']).sum() / no_vol if no_vol else 0
                
                print(f"  Avg YES Price:    {avg_yes:.1f} cents")
                print(f"  Avg NO Price:     {avg_no:.1f} cents")
                print(f"  Implied Spread:   {100 - (avg_yes + avg_no):.1f} cents (Profit per pair)")
                
                found_example = True
                break # Just show one good example
        
        if not found_example:
            print("No tickers found with both BUY_YES and BUY_NO trades.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_hedged_trades()
