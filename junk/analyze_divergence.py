import pandas as pd
import re

def analyze():
    print("Analyzing Real Trades from dump...")
    with open('dec24_trades_dump.txt', 'r') as f:
        content = f.read()
        
    # Parse the fixed width or just regex the lines
    lines = content.split('\n')
    dec24_trades = []
    for line in lines:
        if "2025-12-24" in line:
            dec24_trades.append(line)
            
    if not dec24_trades:
        print("No Dec 24 trades found in dump.")
    else:
        print(f"Found {len(dec24_trades)} trades on Dec 24.")
        print("First 3 Real Trades:")
        for t in dec24_trades[:3]:
            print(t)

if __name__ == "__main__":
    analyze()
