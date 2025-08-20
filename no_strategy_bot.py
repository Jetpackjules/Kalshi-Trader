#!/usr/bin/env python3
"""
no_strategy_bot.py
Runs once, scans temperature markets, places cheap NO orders.
Designed for Kalshi's demo environment (no real money).
"""
import logging
import os
import requests
from kalshi_monitor.auth_config import (
    get_kalshi_api_credentials,
    generate_kalshi_headers,
)

API_BASE = os.getenv("KALSHI_API_BASE", "https://demo-api.kalshi.com/trade-api/v2")

session = requests.Session()
session.headers.update({
    "User-Agent": "no-strategy-bot/0.1",
    "Accept": "application/json",
})

api_key, private_key = get_kalshi_api_credentials()

def sign(method: str, path: str) -> None:
    headers = generate_kalshi_headers(method, path, api_key, private_key)
    session.headers.update(headers)

def fetch_temperature_markets():
    path = "/events"
    sign("GET", path)
    r = session.get(API_BASE + path, params={"status": "open", "limit": 1000}, timeout=10)
    r.raise_for_status()
    temp_keys = ("HIGH", "LOW", "TEMP", "KXHIGH", "KXLOW")
    markets = []
    for event in r.json().get("events", []):
        for m in event.get("markets", []):
            if any(k in m.get("ticker", "").upper() for k in temp_keys):
                markets.append(m)
    return markets

def place_no_order(ticker: str, price_cents: int, qty: int = 1) -> None:
    path = "/orders"
    sign("POST", path)
    order = {
        "ticker": ticker,
        "type": "limit",
        "side": "no",
        "action": "buy",
        "order_type": "good_til_cancel",
        "price": price_cents,
        "quantity": qty,
    }
    r = session.post(API_BASE + path, json=order, timeout=10)
    logging.info("order %s -> %s %s", ticker, r.status_code, r.text)
    r.raise_for_status()

def run_once() -> None:
    for m in fetch_temperature_markets():
        no_ask = m.get("no_ask")
        if no_ask is None:
            continue
        price_cents = int(no_ask * 100)
        if price_cents <= 2:
            try:
                place_no_order(m["ticker"], price_cents)
            except Exception as e:
                logging.error("could not place order for %s: %s", m["ticker"], e)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_once()
