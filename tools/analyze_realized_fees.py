
import csv
import sys
from collections import defaultdict

FILLS_PATH = r"vm_logs/unified_engine_out/fills.csv"

def main():
    print(f"--- Analyzing Realized Fees in {FILLS_PATH} ---")
    
    taker_count = 0
    maker_count = 0
    unknown_count = 0
    
    taker_items = []
    maker_items = []
    
    try:
        with open(FILLS_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row: continue
                # Schema from runner.py:
                # 0:fill_time, 1:ticker, 2:side, 3:price, 4:qty, 5:liquidity, 6:order_id, 7:client_id, 8:fee, 9:raw_fee, 10:source
                if len(row) < 6:
                    continue
                    
                liquidity = row[5].lower()
                price_str = row[3]
                qty_str = row[4]
                
                # Check column 8 for fee
                fee_str = ""
                if len(row) > 8:
                    fee_str = row[8].strip()
                
                try:
                    price = float(price_str)
                    qty = float(qty_str)
                    if fee_str:
                        fee = float(fee_str)
                    else:
                        fee = None # Missing fee
                except ValueError:
                    continue
                    
                data_point = {
                    "price": price,
                    "qty": qty,
                    "fee": fee
                }
                
                if "taker" in liquidity:
                    taker_count += 1
                    if fee is not None: taker_items.append(data_point)
                elif "maker" in liquidity:
                    maker_count += 1
                    if fee is not None: maker_items.append(data_point)
                else:
                    unknown_count += 1

    except FileNotFoundError:
        print("File not found.")
        return

    print(f"Total Taker Fills: {taker_count}")
    print(f"Total Maker Fills: {maker_count}")
    print(f"Total Unknown:     {unknown_count}")
    
    def analyze_group(name, items):
        if not items:
            print(f"\nNo fee data for {name}.")
            return
            
        print(f"\n--- {name} Fee Analysis ({len(items)} samples) ---")
        
        # Just print first 5 examples
        for i, item in enumerate(items[:5]):
            p_val = item['price']   # Cents e.g. 50
            p = p_val / 100.0       # Dollars e.g. 0.50
            q = item['qty']
            f = item['fee']
            
            # Theoretical Fee (Standard 7%) dollars
            raw_fee_7pct = 0.07 * q * p * (1-p)
            
            print(f"Sample {i+1}: Price={p_val}c Qty={q} Fee_csv={f}")
            print(f"  Expected (7%): ${raw_fee_7pct:.4f}")
            
            # Implied Rate
            term = q * p * (1-p)
            if term > 0:
                implied_rate = f / term
                print(f"  Implied Rate: {implied_rate:.4f} (expected 0.07)")
            else:
                print("  Implied Rate: N/A")

    if taker_items:
        analyze_group("Taker", taker_items)
    else:
        print("\nNo Taker fees recorded.")

    if maker_items:
        analyze_group("Maker", maker_items)
    else:
        print("\nNo Maker fees recorded.")

if __name__ == "__main__":
    main()
