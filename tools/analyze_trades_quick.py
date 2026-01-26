import pandas as pd
import sys

try:
    # Read CSV
    df = pd.read_csv("vm_logs/unified_engine_out/trades.csv")
    
    print(f"Total Trades: {len(df)}")
    
    if len(df) > 0:
        # Sort by time just in case
        if 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
            df = df.sort_values('time')
            print(f"First Trade: {df.iloc[0]['time']}")
            print(f"Last Trade: {df.iloc[-1]['time']}")
        
        # Summary by Action
        print("\n--- By Action ---")
        if 'action' in df.columns:
            print(df['action'].value_counts())
        
        # Summary by Ticker
        print("\n--- By Ticker (Top 5) ---")
        if 'ticker' in df.columns:
            print(df['ticker'].value_counts().head(5))
        
        # Financials
        print("\n--- Financials ---")
        if 'cost' in df.columns:
            total_cost = df['cost'].sum()
            print(f"Total Spent (Cost): ${total_cost:.2f}")
            print(f"Avg Cost per Trade: ${df['cost'].mean():.2f}")
        
        if 'qty' in df.columns:
            print(f"Total Volume (Contracts): {df['qty'].sum()}")
            
        if 'price' in df.columns:
            print(f"Avg Price (Cents): {df['price'].mean():.2f}")

        # Position Estimate (Rough)
        # YES buys add to YES inventory. NO buys add to NO inventory.
        # We don't have sells here? Or does 'action' include SELL?
        # Usually MarketMaker only BUYS (to open) and holds to expiry?
        # Or does it sell?
        # The log showed BUY_YES and BUY_NO.
        # If it sells, it would be SELL_YES / SELL_NO.
        
        print("\n--- Last 10 Trades ---")
        cols = [c for c in ['time', 'ticker', 'action', 'price', 'qty', 'cost'] if c in df.columns]
        print(df[cols].tail(10))

except Exception as e:
    print(f"Error: {e}")
