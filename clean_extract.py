import re

def extract_pnl(filename, label):
    results = []
    try:
        with open(filename, 'r', encoding='utf-16', errors='ignore') as f:
            content = f.read()
            # Split by newline
            lines = content.split('\n')
            for line in lines:
                if "Daily PnL" in line:
                    # Clean up carriage returns and extra whitespace
                    clean_line = line.replace('\r', '').strip()
                    # Extract just the PnL part
                    match = re.search(r"\[Daily PnL\] (.*)", clean_line)
                    if match:
                        results.append(f"{label}: {match.group(1)}")
    except Exception as e:
        results.append(f"Error reading {filename}: {e}")
    return results

unrounded = extract_pnl("daily_pnl_unrounded.txt", "Unrounded")
rounded = extract_pnl("daily_pnl_rounded.txt", "Rounded")

with open("final_comparison.txt", "w", encoding="utf-8") as f:
    f.write("=== Daily PnL Comparison ===\n")
    for u, r in zip(unrounded, rounded):
        f.write(f"{u} | {r}\n")
    
    # If lengths differ, print the rest
    if len(unrounded) > len(rounded):
        for u in unrounded[len(rounded):]:
            f.write(f"{u}\n")
    elif len(rounded) > len(unrounded):
        for r in rounded[len(unrounded):]:
            f.write(f"{r}\n")
