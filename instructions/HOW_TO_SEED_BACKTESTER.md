# How to Seed the Backtester with Live State

This process allows you to run a backtest starting from "Right Now", accounting for your existing Cash, Budget, and Inventory.

## Step 1: Export State from Server
Run this command to generate the state file on the server:
```bash
ssh -i "gcp_key" jetpackjules@34.56.193.18 "/home/jetpackjules/venv/bin/python export_live_state.py"
```
*This creates `live_state.json` on the server.*

## Step 2: Download State to Local Machine
Run this command to copy the file to your local folder:
```bash
scp -i "gcp_key" jetpackjules@34.56.193.18:~/live_state.json live_state.json
```

## Step 3: Run the Backtester
Run the backtester with the `--load-state` flag:
```bash
python complex_strategy_backtest.py --start=2025-12-31 --end=2026-01-07 --load-state=live_state.json
```
*(Replace dates as needed. Start date should be "Today".)*

## Why do this?
*   **Budget Accuracy:** The backtester knows you've already spent $X of your daily budget, so it won't over-trade.
*   **Inventory Safety:** It knows you already have 70 YES contracts on `B35.5`, so it won't buy more if you're at the limit.
*   **Realistic PnL:** It calculates future performance based on your *actual* starting point, not a theoretical $1000.
