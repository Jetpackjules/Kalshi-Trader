
def calc_maker_fee(price_cents):
    p = price_cents / 100.0
    return 1.75 * p * (1-p) # Cents

price = 50
fee_one_side = calc_maker_fee(price)
fee_round_trip = fee_one_side * 2

print(f"Price: {price}c")
print(f"Maker Fee (1 side): {fee_one_side:.4f}c")
print(f"Round Trip Fee:     {fee_round_trip:.4f}c")

slippage = 1.0 # 1 cent
buffer = 4.0   # Current setting

cost = fee_round_trip + slippage + buffer
print(f"Current Required Gap (Buffer={buffer}): {cost:.4f}c")
print(f"Is 5c Gap Profitable? {'YES' if 5 > cost else 'NO'}")

# What buffer allows 5c?
max_buffer_for_5c = 5.0 - (fee_round_trip + slippage)
print(f"\nMax Buffer for 5c Gap: {max_buffer_for_5c:.4f}c")
