with open('extracted_pnl.txt', 'w', encoding='utf-8') as out:
    out.write("=== UNROUNDED ===\n")
    try:
        with open('daily_pnl_unrounded.txt', 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if "Daily PnL" in line:
                    out.write(line)
    except Exception as e:
        out.write(f"Error reading unrounded: {e}\n")

    out.write("\n=== ROUNDED ===\n")
    try:
        with open('daily_pnl_rounded.txt', 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if "Daily PnL" in line:
                    out.write(line)
    except Exception as e:
        out.write(f"Error reading rounded: {e}\n")
