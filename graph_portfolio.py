import os
import glob
import json
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from datetime import datetime

def main():
    snapshot_dir = os.path.join('vm_logs', 'snapshots')
    files = glob.glob(os.path.join(snapshot_dir, 'snapshot_*.json'))
    
    data = []
    for f in files:
        with open(f, 'r') as fp:
            try:
                snap = json.load(fp)
            except:
                continue
            
            # The timestamp is either in 'timestamp' or encoded in the filename
            ts_str = snap.get('timestamp')
            if not ts_str:
                # parsed from filename: snapshot_YYYY-MM-DD_HHMMSS.json
                basename = os.path.basename(f)
                parts = basename.replace('snapshot_', '').replace('.json', '')
                try:
                    ts = datetime.strptime(parts, '%Y-%m-%d_%H%M%S')
                except ValueError:
                    try:
                        ts = datetime.strptime(parts, '%Y-%m-%d_%H-%M-%S')
                    except ValueError:
                        continue
            else:
                try:
                    ts = datetime.fromisoformat(ts_str)
                except ValueError:
                    continue

            balance = snap.get('balance', 0) / 100.0
            
            # Extract positions value
            positions = snap.get('positions', {})
            # We don't have exact market prices in the snapshot itself easily, 
            # but usually kalshi's API returns portfolio_value if we pulled it, or we can use the snapshot's portfolio_value.
            port_val = snap.get('portfolio_value', 0)
            if port_val > 1000: # it might be in cents
                port_val /= 100.0
                
            data.append({
                'time': ts,
                'cash': balance,
                'portfolio_value': port_val, # Kalshi API often gives portfolio_value tracking total equity
                'total_equity': balance + port_val if port_val < balance else port_val # simple fallback
            })

    if not data:
        print("No valid snapshot data found.")
        return

    df = pd.DataFrame(data)
    df.sort_values('time', inplace=True)
    df.set_index('time', inplace=True)

    # Clean up any anomalies
    # Kalshi API balance is total liquid cash.
    # Total Equity is usually what we care about. 
    # Because portfolio_value from Kalshi API is often just the value of positions in cents, or total equity, 
    # let's assume total_equity is cash + (positions valued at cost or market).
    # If portfolio_value from API is total equity, we just plot that.
    # Let's plot both Cash and Total Equity.

    plt.figure(figsize=(12, 6))
    plt.plot(df.index, df['cash'], label='Liquid Cash', color='blue', alpha=0.7)
    
    # Check if portfolio_value looks like positions only or total.
    # If portfolio_value is exactly balance, then it's just balance.
    # Let's plot the computed total equity (we assume port_val is positions if it's small, otherwise total).
    
    # We will compute estimated total equity:
    # If port_val == balance, then pos_val = 0
    # If port_val > balance, maybe port_val is total equity.
    df['calculated_equity'] = df.apply(lambda row: row['portfolio_value'] if row['portfolio_value'] > row['cash'] * 1.5 else (row['cash'] + row['portfolio_value']), axis=1)

    plt.plot(df.index, df['calculated_equity'], label='Total Equity (Est.)', color='green', linewidth=2)

    plt.title('Kalshi Portfolio Value Over Time')
    plt.xlabel('Date / Time')
    plt.ylabel('Value ($)')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    
    # Format X axis
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    plt.gcf().autofmt_xdate()

    artifact_dir = r"c:\Users\jetpa\.gemini\antigravity\brain\ee128949-623f-450e-bf02-ff310b11c893"
    out_path = os.path.join(artifact_dir, "portfolio_history.png")
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"Graph saved to {out_path}")

    # Also save a zoomed-in version for the last 7 days
    if len(df) > 0:
        last_time = df.index[-1]
        recent_df = df[df.index >= last_time - pd.Timedelta(days=7)]
        if len(recent_df) > 0:
            plt.clf()
            plt.figure(figsize=(10, 5))
            plt.plot(recent_df.index, recent_df['cash'], label='Liquid Cash', color='blue', alpha=0.7)
            plt.plot(recent_df.index, recent_df['calculated_equity'], label='Total Equity (Est.)', color='green', linewidth=2)
            plt.title('Kalshi Portfolio Value (Last 7 Days)')
            plt.xlabel('Date / Time')
            plt.ylabel('Value ($)')
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.legend()
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            plt.gcf().autofmt_xdate()
            out_recent = os.path.join(artifact_dir, "portfolio_history_recent.png")
            plt.savefig(out_recent, dpi=150, bbox_inches='tight')
            print(f"Recent graph saved to {out_recent}")

if __name__ == '__main__':
    main()
