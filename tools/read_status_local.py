import json

try:
    with open("vm_logs/trader_status.json", "r") as f:
        data = json.load(f)
        
    print(f"Status: {data.get('status')}")
    print(f"Last Update: {data.get('last_update')}")
    print(f"Equity: {data.get('equity')}")
    print(f"Cash: {data.get('cash')}")
    print(f"Portfolio Value: {data.get('portfolio_value')}")
    print(f"Daily Budget: {data.get('daily_budget')}")
    print(f"Spent Today: {data.get('spent_today')}")
    print(f"Positions: {len(data.get('positions', {}))}")
    
except Exception as e:
    print(f"Error: {e}")
