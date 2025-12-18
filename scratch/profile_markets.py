import time
from fetch_orderbook import get_all_markets

print("Starting get_all_markets...")
start = time.time()
markets = get_all_markets()
end = time.time()

print(f"Finished in {end - start:.2f} seconds")
print(f"Fetched {len(markets)} markets")
