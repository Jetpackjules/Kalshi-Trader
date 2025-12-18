import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
from datetime import datetime

def visualize():
    try:
        df = pd.read_csv("backtest_results.csv")
    except FileNotFoundError:
        print("No results file found.")
        return

    if df.empty:
        print("No trades to visualize.")
        return

    # Convert timestamps
    df['time'] = pd.to_datetime(df['time'])
    df['date'] = df['time'].dt.date

    # 1. Cumulative PnL
    df['cumulative_pnl'] = df['profit'].cumsum()
    
    plt.figure(figsize=(10, 6))
    plt.plot(range(len(df)), df['cumulative_pnl'], marker='o', linestyle='-')
    plt.title("Cumulative PnL (Compounding Strategy)")
    plt.xlabel("Trade Number")
    plt.ylabel("Profit ($)")
    plt.grid(True)
    plt.savefig("pnl_curve.png")
    print("Saved pnl_curve.png")

    # 2. Trade Entry Analysis
    # Scatter plot of Temp vs Price (if we had price variation, but here price is mostly 1 or 99)
    # Instead, let's plot Temp vs Time of Day
    
    df['hour'] = df['time'].dt.hour
    
    plt.figure(figsize=(10, 6))
    # Map actions to colors/markers
    colors = {'BUY_YES': 'green', 'BUY_NO': 'red'}
    markers = {'BUY_YES': '^', 'BUY_NO': 'v'}
    
    for action in ['BUY_YES', 'BUY_NO']:
        subset = df[df['action'] == action]
        if not subset.empty:
            plt.scatter(subset['hour'], subset['temp'], 
                       c=colors.get(action, 'blue'), 
                       marker=markers.get(action, 'o'),
                       label=action, s=100)
            
    plt.title("Trade Entry: Time of Day vs Temperature")
    plt.xlabel("Hour of Day (UTC)")
    plt.ylabel("Temperature (F)")
    plt.legend()
    plt.grid(True)
    plt.savefig("trade_entry.png")
    print("Saved trade_entry.png")

if __name__ == "__main__":
    visualize()
