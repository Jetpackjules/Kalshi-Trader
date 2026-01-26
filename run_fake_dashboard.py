import json
import time
import os
import threading
from server_mirror.server_app import app

# Mock Data Generator
def generate_mock_data():
    while True:
        status_data = {
            "status": "RUNNING",
            "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
            "equity": 105.50,
            "trades_today": 12,
            "daily_budget": 50.0,
            "spent_today": 15.20,
            "spent_pct": 30.4,
            "window_status": {"state": "OPEN", "message": "Closes in 04:20:00", "color": "#10B981"},
            "positions": {
                "KXHIGHNY-26JAN25-B23.5": {"yes": 0, "no": 0, "cost": 0},
                "KXHIGHNY-26JAN25-B25.5": {"yes": 10, "no": 0, "cost": 1.50}
            },
            "active_orders": [
                # Gap 1c (Bid 1, Ask 2)
                {"ticker": "KXHIGHNY-26JAN25-B23.5", "action": "BUY_YES", "price": 1, "qty": 100},
                {"ticker": "KXHIGHNY-26JAN25-B23.5", "action": "BUY_NO", "price": 98, "qty": 50}, # Ask 2c
                
                # Gap 4c (Bid 5, Ask 9)
                {"ticker": "KXHIGHNY-26JAN25-B25.5", "action": "BUY_YES", "price": 5, "qty": 20},
                {"ticker": "KXHIGHNY-26JAN25-B25.5", "action": "BUY_NO", "price": 91, "qty": 20}, # Ask 9c
                
                # Gap 10c (Bid 40, Ask 50)
                {"ticker": "KXHIGHNY-26JAN25-T23", "action": "BUY_YES", "price": 40, "qty": 10},
                {"ticker": "KXHIGHNY-26JAN25-T23", "action": "BUY_NO", "price": 50, "qty": 10}, # Ask 50c
            ]
        }
        
        with open("trader_status.json", "w") as f:
            json.dump(status_data, f)
            
        time.sleep(1)

if __name__ == "__main__":
    # Create required dirs
    if not os.path.exists("market_logs"):
        os.makedirs("market_logs")
    if not os.path.exists("unified_engine_out"):
        os.makedirs("unified_engine_out")
        
    # Start Mock Generator
    t = threading.Thread(target=generate_mock_data, daemon=True)
    t.start()
    
    print("Starting Fake Dashboard Server on http://localhost:8080")
    app.run(host='0.0.0.0', port=8080)
