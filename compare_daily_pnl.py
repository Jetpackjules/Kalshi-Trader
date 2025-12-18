import re

def parse_pnl(filename):
    daily_pnl = {}
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # Match: [Daily PnL] 25DEC17: $12.34 (End Equity: $112.34)
            match = re.search(r"\[Daily PnL\] (\w+): \$([-\d\.]+) \(End Equity: \$([-\d\.]+)\)", line)
            if match:
                date = match.group(1)
                pnl = float(match.group(2))
                equity = float(match.group(3))
                daily_pnl[date] = {'pnl': pnl, 'equity': equity}
    return daily_pnl

unrounded = parse_pnl("daily_pnl_unrounded.txt")
rounded = parse_pnl("daily_pnl_rounded.txt")

with open('comparison_report_utf8.txt', 'w', encoding='utf-8') as f:
    f.write(f"{'Date':<10} | {'Unrounded PnL':<15} | {'Rounded PnL':<15} | {'Diff':<10}\n")
    f.write("-" * 60 + "\n")

    all_dates = sorted(set(unrounded.keys()) | set(rounded.keys()))
    for date in all_dates:
        u_pnl = unrounded.get(date, {}).get('pnl', 0.0)
        r_pnl = rounded.get(date, {}).get('pnl', 0.0)
        diff = u_pnl - r_pnl
        f.write(f"{date:<10} | ${u_pnl:<14.2f} | ${r_pnl:<14.2f} | ${diff:<9.2f}\n")
