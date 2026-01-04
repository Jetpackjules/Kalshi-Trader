# How to Save a Live Snapshot (VM)

This captures the live trader’s current state (cash, positions, config, timestamp) into a JSON file you can use later for reference or for snapshot-seeded backtests.

## Prereqs
- VM: `jetpackjules@34.56.193.18`
- SSH key: `./keys/gcp_key`
- The live trader script supports `--snapshot` and optional `--snapshot-out`.

## 1) (Optional) Deploy updated trader files first
If you’re uploading a new trader version and want the snapshot to correspond to the deployed version, upload these first:

```powershell
scp -i .\keys\gcp_key -o StrictHostKeyChecking=no .\server_mirror\live_trader_v4.py jetpackjules@34.56.193.18:~/live_trader_v4.py
scp -i .\keys\gcp_key -o StrictHostKeyChecking=no .\server_mirror\live_trader_v6.py jetpackjules@34.56.193.18:~/live_trader_v6.py
```

## 2) Save a snapshot on the VM
This runs the script in “snapshot-only” mode (it writes a snapshot and exits).

```powershell
ssh -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18 "~/venv/bin/python ~/live_trader_v6.py --snapshot"
```

### Save to an explicit filename (recommended)
This makes it easy to keep snapshots organized:

```powershell
ssh -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18 "~/venv/bin/python ~/live_trader_v6.py --snapshot --snapshot-out ~/snapshot_$(date +%F_%H%M%S).json"
```

## 3) Download the snapshot to your local machine
If you used `--snapshot-out`, download that exact file:

```powershell
scp -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18:~/snapshot_YYYY-MM-DD_HHMMSS.json .\vm_logs\snapshots\
```

If you didn’t specify `--snapshot-out`, list recent snapshots on the VM and pick the newest:

```powershell
ssh -i .\keys\gcp_key -o StrictHostKeyChecking=no jetpackjules@34.56.193.18 "ls -lt ~/*.json | head"
```

## 4) Use the snapshot for backtesting (local)
Once the snapshot JSON is local, you can run a snapshot-seeded replay like:

```powershell
& ".\.venv\Scripts\python.exe" -m backtesting.runner \
  --strategy backtesting.strategies.v3_variants:baseline_v3 \
  --snapshot vm_logs/snapshots/snapshot_YYYY-MM-DD_HHMMSS.json \
  --end-ts "YYYY-MM-DD HH:MM:SS" \
  --log-dir vm_logs/market_logs \
  --out backtest_charts/snapshot_replay_YYYY-MM-DD_HHMMSS.html
```

Tip: For best-effort live parity (rounding + requote throttling), add `--simulate-live`.
