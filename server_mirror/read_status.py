import json
import os

try:
    with open("trader_status.json", "r") as f:
        data = json.load(f)
    
    print(f"DailyStartEquity: {data.get('daily_start_equity')}")
    print(f"DailyBudget: {data.get('daily_budget')}")
    print(f"Equity: {data.get('equity')}")
    print(f"Strategy: {data.get('strategy')}")
    
    # Calculate implied risk
    start = data.get('daily_start_equity', 0)
    budget = data.get('daily_budget', 0)
    if start > 0:
        print(f"ImpliedRiskPct: {budget / start}")
    else:
        print("ImpliedRiskPct: Undefined (Start=0)")

except Exception as e:
    print(f"Error: {e}")
