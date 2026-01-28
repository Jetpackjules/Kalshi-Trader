#!/bin/bash
pkill -f unified_engine.runner
nohup ~/venv/bin/python -u -m unified_engine.runner --live --key-file ~/kalshi_prod_private_key.pem --strategy backtesting.strategies.simple_market_maker:simple_mm_v2_fixed --strategy-kwargs '{"spread_cents":4,"qty":10,"max_price":99,"skew_factor":0.5}' --log-dir market_logs --file-pattern "market_data_KXHIGHNY-*.csv" --follow --diag-log --status-every-ticks 10 --min-requote-interval 5.0 --amend-price-tolerance 1 --amend-qty-tolerance 0 --live-trade-window-s 60 --max-order-age-s 900 --disable-trading-windows >> ~/output.log 2>&1 &
