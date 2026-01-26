import pandas as pd
from datetime import datetime, timedelta
import pytz

def compare_trades():
    print("Loading files...")
    
    # 1. Load Kalshi Trades
    # Header: "type","Market_Ticker","Market_Id","Original_Date","Price_In_Cents","Amount_In_Dollars","Fee_In_Dollars","Traded_Time","Direction","Order_Type"
    try:
        k_df = pd.read_csv("activity (manually saved)/Kalshi-Recent-Activity-Trade today.csv")
    except Exception as e:
        print(f"Failed to load Kalshi trades: {e}")
        return

    # 2. Load Bot Trades
    # Header: time,order_time,fill_time,fill_delay_s,place_time,action,ticker,price,qty,fee,cost,source,order_id
    try:
        b_df = pd.read_csv("vm_logs/unified_engine_out/trades.csv")
    except Exception as e:
        print(f"Failed to load Bot trades: {e}")
        return

    print(f"Loaded {len(k_df)} Kalshi trades and {len(b_df)} Bot trades.")

    # 3. Normalize Kalshi Data
    # Timestamp: 2026-01-21T20:13:07.376Z (UTC)
    # We need to convert to match Bot Time.
    # Bot Time seems to be UTC (based on previous logs showing 01:xx for 1am ET? Wait. 1am ET is 06:00 UTC).
    # Let's check Bot Time format again.
    # Bot log: 2026-01-21 01:18:47.981391
    # If this was 1am ET, and server is UTC, it should be 06:00.
    # If server is ET, it is 01:00.
    # The user said "The current local time is: 2026-01-21T12:23:00-08:00" (PST).
    # 12:23 PST = 20:23 UTC.
    # Kalshi file has 20:13 UTC.
    # So Kalshi is UTC.
    # Bot log has 10:11 (last trade).
    # If Bot is UTC, 10:11 UTC = 02:11 PST.
    # But user is at 12:23 PST.
    # So Bot is NOT UTC?
    # Wait, if Bot log is 10:11, and current time is 12:23 PST (20:23 UTC).
    # 10:11 PST?
    # If Bot is running on GCP in us-central1 (Iowa), it might be UTC.
    # Let's assume Bot Time is UTC for now, but the values look like PST?
    # 10:11 PST = 18:11 UTC.
    # If Bot log says 10:11, and it's 12:23 PST now.
    # That matches "recent".
    # So Bot Time is likely Local Server Time (UTC? or System Time?).
    # GCP VMs usually default to UTC.
    # But 10:11 UTC would be 02:11 PST. That was 10 hours ago.
    # If the bot was trading "just now" (10:11 log time), and user is at 12:23 PST.
    # 10:11 PST is plausible.
    # So Bot Time might be PST? Or the server is in a timezone matching PST?
    # Wait, us-central1 is Central Time.
    # 12:23 PST = 14:23 CST.
    # 10:11 CST = 08:11 PST.
    # This is confusing.
    # Let's look at the Kalshi timestamp: 20:13 UTC.
    # 20:13 UTC = 12:13 PST.
    # If Bot has a trade at 10:11...
    # Maybe Bot is UTC and the log I saw earlier (10:11) was actually 10:11 UTC?
    # But 10:11 UTC is 02:11 PST.
    # The user said "take a look at the trades... I just ran sync vm logs".
    # If the bot was running all morning...
    # Let's try to match patterns.

    k_df['dt'] = pd.to_datetime(k_df['Original_Date']) # UTC
    b_df['dt'] = pd.to_datetime(b_df['time'])

    # Convert Kalshi to naive UTC (remove timezone info for comparison if Bot is naive)
    k_df['dt'] = k_df['dt'].dt.tz_localize(None)

    # Check offset
    # Let's find the latest trade in both.
    k_last = k_df['dt'].max()
    b_last = b_df['dt'].max()
    
    print(f"Latest Kalshi Trade (UTC): {k_last}")
    print(f"Latest Bot Trade (Raw):    {b_last}")
    
    # Calculate offset
    diff = k_last - b_last
    print(f"Time Difference: {diff}")
    
    # If diff is ~8 hours, Bot is PST.
    # If diff is ~0 hours, Bot is UTC.
    
    # Normalize Bot to UTC
    # If diff is > 1 hour, adjust.
    if abs(diff.total_seconds()) > 3600:
        # Round to nearest hour
        hours = round(diff.total_seconds() / 3600)
        print(f"Adjusting Bot Time by {hours} hours to match UTC...")
        b_df['dt'] = b_df['dt'] + timedelta(hours=hours)

    # 4. Matching Logic (Improved)
    
    # Map columns first
    k_df['action_mapped'] = k_df['Direction'].apply(lambda x: 'BUY_YES' if x == 'Yes' else ('BUY_NO' if x == 'No' else x))
    k_df['qty_mapped'] = k_df['Amount_In_Dollars'].astype(int)
    
    print("\nMatching trades (Loose Mode)...")
    
    matched_count = 0
    partial_fill_matches = 0
    
    # We will try to "consume" bot trades.
    b_remaining = b_df.copy()
    b_remaining['matched_qty'] = 0
    
    # Sort Kalshi by time
    k_df = k_df.sort_values('dt')
    
    for idx, k_row in k_df.iterrows():
        # Find candidates
        # Same Ticker, Same Action, Same Price
        # Time within 2 minutes (to account for clock drift/latency)
        
        candidates = b_remaining[
            (b_remaining['ticker'] == k_row['Market_Ticker']) &
            (b_remaining['action'] == k_row['action_mapped']) &
            (b_remaining['price'] == k_row['Price_In_Cents']) &
            (b_remaining['matched_qty'] < b_remaining['qty']) # Still has quantity to match
        ]
        
        candidates = candidates[
            (candidates['dt'] - k_row['dt']).abs() < timedelta(minutes=2)
        ]
        
        if not candidates.empty:
            # Pick closest time
            best_idx = (candidates['dt'] - k_row['dt']).abs().idxmin()
            
            # "Fill" this bot trade
            needed = k_row['qty_mapped']
            available = b_remaining.at[best_idx, 'qty'] - b_remaining.at[best_idx, 'matched_qty']
            
            filled = min(needed, available)
            b_remaining.at[best_idx, 'matched_qty'] += filled
            
            if filled > 0:
                matched_count += 1
                # print(f"Matched Kalshi {k_row['dt']} {k_row['qty_mapped']} -> Bot {b_remaining.at[best_idx, 'dt']} (Took {filled})")
        else:
            # Debug why no match
            # Find candidates ignoring price
            candidates_any_price = b_remaining[
                (b_remaining['ticker'] == k_row['Market_Ticker']) &
                (b_remaining['action'] == k_row['action_mapped'])
            ]
            candidates_any_price = candidates_any_price[
                (candidates_any_price['dt'] - k_row['dt']).abs() < timedelta(minutes=2)
            ]
            
            if not candidates_any_price.empty:
                best = candidates_any_price.iloc[0]
                # print(f"MISMATCH: Kalshi {k_row['dt']} {k_row['Market_Ticker']} P={k_row['Price_In_Cents']} Q={k_row['qty_mapped']} | Bot P={best['price']} Q={best['qty']}")
                pass
            else:
                # print(f"MISSING: Kalshi {k_row['dt']} {k_row['Market_Ticker']} P={k_row['Price_In_Cents']} Q={k_row['qty_mapped']} | No Bot trade found nearby")
                pass

    print(f"\n--- Results (Loose Matching) ---")
    print(f"Total Kalshi Trades: {len(k_df)}")
    print(f"Total Bot Trades:    {len(b_df)}")
    print(f"Matched Kalshi Rows: {matched_count}")
    
    # Check total volume
    k_vol = k_df['qty_mapped'].sum()
    b_vol = b_df['qty'].sum()
    b_matched_vol = b_remaining['matched_qty'].sum()
    
    print(f"\nVolume Analysis:")
    print(f"Kalshi Total Volume: {k_vol}")
    print(f"Bot Total Volume:    {b_vol}")
    print(f"Bot Matched Volume:  {b_matched_vol}")
    print(f"Coverage:            {b_matched_vol / k_vol * 100:.1f}% of Kalshi volume found in Bot")

    # Mismatch Analysis
    print("\n--- Mismatch Analysis ---")
    # 1. Price Mismatch
    # 2. Missing Trades
    
    # Re-run loop for debug stats
    price_mismatch = 0
    missing_trade = 0
    
    for idx, k_row in k_df.iterrows():
         # Find candidates ignoring price
        candidates_any_price = b_remaining[
            (b_remaining['ticker'] == k_row['Market_Ticker']) &
            (b_remaining['action'] == k_row['action_mapped'])
        ]
        candidates_any_price = candidates_any_price[
            (candidates_any_price['dt'] - k_row['dt']).abs() < timedelta(minutes=2)
        ]
        
        # Check if we matched this row previously (hard to track without ID)
        # Let's just check if a price match exists
        candidates_exact = candidates_any_price[candidates_any_price['price'] == k_row['Price_In_Cents']]
        
        if candidates_exact.empty and not candidates_any_price.empty:
            price_mismatch += 1
            if price_mismatch < 5:
                best = candidates_any_price.iloc[0]
                print(f"PRICE DIFF: Kalshi {k_row['dt']} {k_row['Market_Ticker']} P={k_row['Price_In_Cents']} | Bot P={best['price']}")
        elif candidates_any_price.empty:
            missing_trade += 1
            if missing_trade < 5:
                print(f"MISSING: Kalshi {k_row['dt']} {k_row['Market_Ticker']} P={k_row['Price_In_Cents']}")
                
    print(f"Total Price Mismatches: {price_mismatch}")
    print(f"Total Missing Trades:   {missing_trade}")

    # Time Range Check
    print(f"\nTime Range:")
    print(f"Kalshi: {k_df['dt'].min()} to {k_df['dt'].max()}")
    print(f"Bot:    {b_df['dt'].min()} to {b_df['dt'].max()}")
    
    if k_df['dt'].max() > b_df['dt'].max() + timedelta(minutes=10):
        print("\nWARNING: Kalshi has trades AFTER the Bot logs end.")
        print(f"Bot stopped logging {k_df['dt'].max() - b_df['dt'].max()} before the last Kalshi trade.")
    
compare_trades()
