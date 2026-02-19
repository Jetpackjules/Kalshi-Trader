import pandas as pd
import matplotlib.pyplot as plt
import argparse
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out_dir = args.out_dir
    equity_path = os.path.join(out_dir, "equity_history.csv")
    trades_path = os.path.join(out_dir, "unified_trades.csv")

    equity_df = pd.read_csv(equity_path)
    if "date" in equity_df.columns:
        equity_df["date"] = pd.to_datetime(equity_df["date"], utc=True, errors='coerce').dt.tz_localize(None)
        equity_df = equity_df.dropna(subset=["date"])

    trades_df = pd.read_csv(trades_path) if os.path.exists(trades_path) else pd.DataFrame()
    if not trades_df.empty and "time" in trades_df.columns:
        trades_df["time"] = pd.to_datetime(trades_df["time"], utc=True, errors='coerce').dt.tz_localize(None)
        trades_df = trades_df.dropna(subset=["time"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # Plot Equity
    ax1.plot(equity_df["date"], equity_df["equity"], label="Total Equity", color="blue")
    ax1.plot(equity_df["date"], equity_df["cash"], label="Cash", color="green", linestyle="--")
    ax1.set_ylabel("Value ($)")
    ax1.set_title("Backtest Equity Curve")
    ax1.legend()
    ax1.grid(True)

    # Plot Trades on Equity
    if not trades_df.empty:
        buys = trades_df[trades_df["action"].str.contains("BUY")]
        if not buys.empty:
            ax1.scatter(buys["time"], [equity_df.iloc[equity_df["date"].searchsorted(t)]["equity"] if t in equity_df["date"].values else equity_df["equity"].iloc[-1] for t in buys["time"]], marker="^", color="green", label="Buy", zorder=5)

    # Plot Positions (Inventory)
    # We can infer inventory from equity history "holdings" or just assume from trades if we track it. 
    # But for now let's just plot Cash vs Equity spread which implies exposure.
    # Actually, let's just do Cash vs Equity on top is good enough.
    
    # Plot Holdings Value
    ax2.plot(equity_df["date"], equity_df["holdings"], label="Holdings Value", color="orange")
    ax2.set_ylabel("Holdings ($)")
    ax2.set_title("Portfolio Exposure")
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout()
    plt.savefig(args.out)
    print(f"Saved static graph to {args.out}")

if __name__ == "__main__":
    main()
