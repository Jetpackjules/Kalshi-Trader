
import os
import time
import csv
from pathlib import Path
from server_mirror.unified_engine.tick_sources import iter_ticks_from_market_logs

def test_safe_warmup():
    # Create a dummy market log
    log_dir = "debug_warmup"
    os.makedirs(log_dir, exist_ok=True)
    log_file = Path(log_dir) / "market_data_TEST.csv"
    
    # Write 100 lines
    with open(log_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp","market_ticker","best_yes_bid","best_no_bid","implied_no_ask","implied_yes_ask","last_trade_price"])
        for i in range(100):
            writer.writerow([f"2026-01-12T08:00:{i:02d}.000000", "TEST-TICKER", 10, 90, 91, 11, 0])

    print("Created dummy log with 100 lines.")

    # Run iter_ticks with follow=True (simulating Live Bot)
    # It should read the last ~8192 bytes. Since our file is small (<8192), it should read EVERYTHING (seek(0)).
    # If it was SEEK_END, it would read NOTHING.
    
    print("Starting tick iterator...")
    iterator = iter_ticks_from_market_logs(log_dir, follow=True, poll_s=0.1)
    
    count = 0
    start_time = time.time()
    for tick in iterator:
        count += 1
        print(f"Read tick: {tick['seq']} {tick['time']}")
        if count >= 100:
            break
        if time.time() - start_time > 2:
            break
            
    print(f"Total ticks read: {count}")
    
    if count == 100:
        print("SUCCESS: Read all lines (Safe Warmup worked for small file).")
    elif count == 0:
        print("FAILURE: Read 0 lines (SEEK_END bug still present).")
    else:
        print(f"PARTIAL: Read {count} lines.")

if __name__ == "__main__":
    test_safe_warmup()
