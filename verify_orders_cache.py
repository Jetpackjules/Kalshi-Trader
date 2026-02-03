import time
import unittest
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'server_mirror'))
from unittest.mock import MagicMock, patch
from datetime import datetime
from unified_engine.adapters import LiveAdapter

# Mock the LiveAdapter to avoid file I/O for keys and real requests
class MockLiveAdapter(LiveAdapter):
    def __init__(self):
        # Skip super init to avoid key loading
        self._diag_log = None
        self._fills_log = None
        self.private_key = MagicMock()
        self._session = MagicMock()
        
        # Init caches manually (copied from actual class)
        self._open_orders_cache = {} 
        self._cached_all_orders = (0.0, []) # The new cache we will add
        self._orders_cache_ttl = 2.0
        self._orders_last_fetch = 0.0

    # We will inject the NEW methods here to test them BEFORE modifying the real file
    # This simulates the "Proposed Change"
    
    def _fetch_active_orders_global(self) -> list[dict]:
        """Fetch ALL active orders from API and cache them globally."""
        # Check global cache
        ts, orders = self._cached_all_orders
        if time.time() - ts < self._orders_cache_ttl:
            return orders

        print("DEBUG: API CALL HIT (Fetching all orders)")
        # Fetch from API
        path = "/trade-api/v2/portfolio/orders?status=resting,open"
        
        # MOCK RESPONSE
        # We assume self._session.get returns a mock with .json()
        resp = self._session.get("MOCK_URL" + path)
        if resp.status_code == 200:
            data = resp.json()
            new_orders = data.get("orders", [])
            # Update Global Cache
            self._cached_all_orders = (time.time(), new_orders)
            return new_orders
        return []

    def get_open_orders(self, ticker: str, market_state: dict, current_time: datetime) -> list[dict]:
        # Uses the global cache now
        all_orders = self._fetch_active_orders_global()
        # Filter for this specific ticker
        return [o for o in all_orders if o.get("ticker") == ticker]


class TestOrderCache(unittest.TestCase):
    def test_global_cache_hit(self):
        adapter = MockLiveAdapter()
        
        # Setup Mock API Response
        mock_orders = [
            {"ticker": "TICKER_A", "order_id": "1", "status": "open", "remaining_count": 10},
            {"ticker": "TICKER_B", "order_id": "2", "status": "resting", "remaining_count": 5},
            {"ticker": "TICKER_A", "order_id": "3", "status": "executed", "remaining_count": 0}, # Should be filtered by API usually, but if present logic handles it?
        ]
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"orders": mock_orders}
        adapter._session.get.return_value = mock_resp
        
        # 1. First Call for Ticker A
        print("\n--- Requesting Ticker A ---")
        orders_a = adapter.get_open_orders("TICKER_A", {}, datetime.now())
        self.assertEqual(len(orders_a), 2) # Should find order 1 and 3 (we logic filter later in real app, but here simple filter)
        # Wait, the simple filter in get_open_orders just checks ticker.
        # The API call is supposed to do status filtering.
        
        # Verify API called
        self.assertEqual(adapter._session.get.call_count, 1)
        
        # 2. Second Call for Ticker B (Immediate)
        print("\n--- Requesting Ticker B ---")
        orders_b = adapter.get_open_orders("TICKER_B", {}, datetime.now())
        self.assertEqual(len(orders_b), 1)
        
        # Verify API NOT called again (Cache Hit)
        self.assertEqual(adapter._session.get.call_count, 1)
        print("SUCCESS: API was only called once for multiple tickers!")

        # 3. Third Call for Ticker A after sleep (Cache Expired)
        print("\n--- Sleeping 2.1s ---")
        time.sleep(2.1)
        
        print("--- Requesting Ticker A again ---")
        orders_a_2 = adapter.get_open_orders("TICKER_A", {}, datetime.now())
        
        # Verify API Called again
        self.assertEqual(adapter._session.get.call_count, 2)
        print("SUCCESS: API called again after TTL expired.")

if __name__ == '__main__':
    unittest.main()
