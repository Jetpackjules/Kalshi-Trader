
import pandas as pd
import re

debug_path = "vm_logs/unified_engine_out/trade_debug.csv"

def parse_kv(note):
    # MM_CLOSE(ge=-1.0c fee=1.63c ne=-2.63c mid=12.5 micro=12.7 sp=8)
    # Extract fee, ne
    data = {}
    
    # fee
    m = re.search(r'fee=([\d\.-]+)c', note)
    if m: data['fee'] = float(m.group(1))
    
    # ne
    m = re.search(r'ne=([\d\.-]+)c', note)
    if m: data['ne'] = float(m.group(1))
    
    return data

def main():
    print("--- Analyzing Trade Decisions (Direct) ---")
    try:
        df = pd.read_csv(debug_path, header=None)
    except:
        print("No debug log.")
        return
        
    opens = []
    closes = []
    
    for idx, row in df.iterrows():
        # Last col is note
        note = str(row.values[-1])
        
        metrics = parse_kv(note)
        # Some might not parse if format changed, skip
        if not metrics: continue
        
        if "MM_OPEN" in note:
            opens.append(metrics)
        elif "MM_CLOSE" in note:
            closes.append(metrics)
            
    # Stats
    print(f"Total Decisions: {len(df)}")
    print(f"Opens: {len(opens)}")
    print(f"Closes: {len(closes)}")
    
    if opens:
        df_open = pd.DataFrame(opens)
        print("\n[MM_OPEN Stats]")
        print(f"  Avg Fee: {df_open['fee'].mean():.2f}c")
        print(f"  Avg Net Edge: {df_open['ne'].mean():.2f}c")
        print(f"  Max Fee: {df_open['fee'].max():.2f}c")
        
        # High fee check (>1.5c implies Taker usually?)
        high_fee = df_open[df_open['fee'] > 1.2]
        print(f"  High Fee Opens (>1.2c): {len(high_fee)} / {len(opens)}")

    if closes:
        df_close = pd.DataFrame(closes)
        print("\n[MM_CLOSE Stats]")
        print(f"  Avg Fee: {df_close['fee'].mean():.2f}c")
        print(f"  Avg Net Edge: {df_close['ne'].mean():.2f}c")
        print(f"  Min Net Edge: {df_close['ne'].min():.2f}c")
        
        # Negative Edge check
        neg_edge = df_close[df_close['ne'] < 0]
        print(f"  Negative Edge Closes: {len(neg_edge)} / {len(closes)}")
        print(f"  Avg Neg Edge Loss: {neg_edge['ne'].mean():.2f}c" if not neg_edge.empty else "0.00c")
        
if __name__ == "__main__":
    main()
