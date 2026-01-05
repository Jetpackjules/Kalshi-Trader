# Unified Engine Prototype

Goal: one shared engine loop for both live and backtest, with pluggable
adapters and tick sources. This folder is a standalone prototype and does
not touch the live server code.

What it does now
- Shared engine loop (strategy eval + order reconciliation).
- Sim adapter with immediate fills when limit >= ask.
- Tick sources:
  - Historical market logs (market_data_*.csv)
  - Live tick logs (live_ticks_*.csv or live_ticks_ingest_*.csv)
- Outputs trades and orders to CSV.

What it does not model (yet)
- Partial fills, queue position, cancels from exchange.
- Live budget/exposure checks.
- Inventory limits from the live engine.

Quick start

1) Historical run
   python -m unified_engine.runner --strategy backtesting.strategies.v3_variants:hb_notional_010 \
     --log-dir vm_logs/market_logs --out-dir unified_engine_out

2) Live tick replay (tick timestamp)
   python -m unified_engine.runner --strategy backtesting.strategies.v3_variants:hb_notional_010 \
     --tick-log vm_logs/live_ticks_2026-01-05.csv --out-dir unified_engine_out

3) Live tick replay (ingest timestamp)
   python -m unified_engine.runner --strategy backtesting.strategies.v3_variants:hb_notional_010 \
     --tick-log vm_logs/live_ticks_ingest_2026-01-05.csv --use-ingest --out-dir unified_engine_out

4) Seed from snapshot
   python -m unified_engine.runner --strategy backtesting.strategies.v3_variants:hb_notional_010 \
     --tick-log vm_logs/live_ticks_ingest_2026-01-05.csv --use-ingest \
     --snapshot vm_logs/snapshots/snapshot_2026-01-05_115639.json \
     --out-dir unified_engine_out

Outputs
- unified_engine_out/unified_trades.csv
- unified_engine_out/unified_orders.csv
- unified_engine_out/unified_positions.json
