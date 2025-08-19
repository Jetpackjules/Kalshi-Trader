#!/usr/bin/env python3
"""Analyze potential returns for simple NO strategy using historical data.

This script scans candlestick price data and market outcomes to estimate
profits from buying NO shares. For each market that ultimately resolves to
"no", it records the highest observed YES price (since profit from buying NO
is equal to the YES price paid by counterparties). The script then reports the
average potential profit per contract across all such markets.

Required data files:
- data/candles/KXHIGHNY_candles_5m.csv
- data/markets.jsonl
"""

import csv
import json
import os
import statistics
from typing import Dict, List

CANDLES_FILE = "data/candles/KXHIGHNY_candles_5m.csv"
MARKETS_FILE = "data/markets.jsonl"


def load_max_yes_prices(path: str) -> Dict[str, float]:
    """Return max YES price per market ticker from candlestick CSV."""
    prices: Dict[str, List[float]] = {}
    if not os.path.exists(path):
        return {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get("ticker")
            try:
                close = float(row.get("close", "nan"))
            except ValueError:
                continue
            if ticker:
                prices.setdefault(ticker, []).append(close)
    return {t: max(vals) for t, vals in prices.items() if vals}


def load_markets(path: str) -> Dict[str, dict]:
    """Load markets information keyed by ticker."""
    markets: Dict[str, dict] = {}
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = json.loads(line)
            markets[m.get("ticker")] = m
    return markets


def analyze_no_strategy() -> None:
    max_prices = load_max_yes_prices(CANDLES_FILE)
    markets = load_markets(MARKETS_FILE)

    profits = []
    for ticker, info in markets.items():
        if info.get("result") == "no":
            yes_price = max_prices.get(ticker, float(info.get("last_price", 0)))
            profits.append(yes_price)
    if profits:
        avg_profit = statistics.mean(profits) / 100.0
        print(f"Average potential profit from NO strategy: ${avg_profit:.2f} per contract" )
        print(f"Markets analyzed: {len(profits)}")
    else:
        print("No markets with result 'no' found or data missing.")


if __name__ == "__main__":
    analyze_no_strategy()
