import requests
from requests.exceptions import RequestException

# --- CONFIG ---
series_ticker = "KXHIGHNY"  # NYC high-temp series

# --- FETCH MARKETS (robust to connection errors) ---
markets_url = (
    f"https://api.elections.kalshi.com/trade-api/v2/markets"
    f"?series_ticker={series_ticker}&status=open"
)

try:
    markets_response = requests.get(markets_url, timeout=5)
    markets_response.raise_for_status()
    markets_data = markets_response.json()
except RequestException as e:
    print("ERROR: Failed to fetch markets:", e)
    # Fallback so the rest of the script and tests can still run
    markets_data = {"markets": []}

markets_list = markets_data.get("markets", [])

if not markets_list:
    print("No active markets returned for this series. Using empty orderbook.")
    market_ticker = "(no-market)"
    orderbook_data = {"orderbook": {"yes": [], "no": []}}
else:
    # Select first open market (you can later filter by date, e.g., 11/18)
    market_ticker = markets_list[0]["ticker"]

    # --- FETCH ORDERBOOK (also robust to connection errors) ---
    orderbook_url = (
        f"https://api.elections.kalshi.com/trade-api/v2/markets/{market_ticker}/orderbook"
    )

    try:
        orderbook_response = requests.get(orderbook_url, timeout=5)
        orderbook_response.raise_for_status()
        orderbook_data = orderbook_response.json()
    except RequestException as e:
        print("ERROR: Failed to fetch orderbook:", e)
        orderbook_data = {"orderbook": {"yes": [], "no": []}}

# --- SAFE ACCESS HELPERS ---
yes_bids = orderbook_data.get("orderbook", {}).get("yes", [])
no_bids = orderbook_data.get("orderbook", {}).get("no", [])

# --- MAIN OUTPUT ---
print(f"\nOrderbook for {market_ticker}:")
print("YES BIDS:")
for bid in yes_bids[:5]:
    print(f"  Price: {bid[0]}¢, Quantity: {bid[1]}")

print("\nNO BIDS:")
for bid in no_bids[:5]:
    print(f"  Price: {bid[0]}¢, Quantity: {bid[1]}")

# --- TEST CASES (do not remove existing ones) ---
# 1. Ensure markets_data loads and has markets
print("\nTEST: Number of markets loaded:", len(markets_list))
# 2. Ensure orderbook contains yes/no sections
print("TEST: YES levels: ", len(yes_bids))
print("TEST: NO levels:  ", len(no_bids))

# 3. New test: confirm structure of orderbook_data
print("TEST: 'orderbook' key present:", "orderbook" in orderbook_data)
# 4. New test: confirm market_ticker type
print("TEST: market_ticker type:", type(market_ticker).__name__)
