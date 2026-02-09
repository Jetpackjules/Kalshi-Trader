
def calculate_convex_fee(price_cents, qty, rate=0.07):
    # Rate * Qty * P * (1-P)
    p = price_cents / 100.0
    fee = rate * qty * p * (1-p)
    return fee * 100 # Cents

def get_min_gap(price_cents, fee_rate, buffer_cents=5):
    # Round Trip Fee + Buffer
    # We pay fee on Entry and Exit
    fee = calculate_convex_fee(price_cents, 1, fee_rate)
    round_trip_fee = 2 * fee
    return round_trip_fee + buffer_cents

print("--- Minimum Profitable Gap (Cents) vs Fee Rate ---")
print(f"{'Price':<6} | {'Taker (7%)':<12} | {'Maker (3.5%)':<12} | {'Maker (0%)':<12}")
print("-" * 50)

for price in [10, 25, 50, 75, 90]:
    gap_7 = get_min_gap(price, 0.07)
    gap_35 = get_min_gap(price, 0.035)
    gap_0 = get_min_gap(price, 0.0)
    
    print(f"{price:<6} | {gap_7:<12.2f} | {gap_35:<12.2f} | {gap_0:<12.2f}")

print("\nAssumptions:")
print("- Buffer: 5 cents (Risk/Profit)")
print("- Round Trip: Entry + Exit")
