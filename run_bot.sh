#!/bin/bash
pkill -f unified_engine.runner
nohup ~/venv/bin/python -u -m unified_engine.runner --live --key-file ~/kalshi_prod_private_key.pem --strategy backtesting.strategies.champion_f6_0322_cold_only:champion_cold_only --strategy-kwargs '{"cash_fraction":0.5}' --log-dir market_logs --file-pattern "market_data_KXHIGHNY-*.csv" --follow --diag-log --status-every-ticks 10 --min-requote-interval 5.0 --amend-price-tolerance 1 --amend-qty-tolerance 0 --live-trade-window-s 60 --max-order-age-s 3600 --disable-trading-windows --disable-fills-log >> ~/output.log 2>&1 &
