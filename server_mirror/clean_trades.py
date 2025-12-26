import csv

input_file = 'trades_server.csv'
output_file = 'trades_cleaned.csv'

with open(input_file, 'r', newline='') as f:
    reader = csv.reader(f)
    header = next(reader)
    # Standardize header
    new_header = ["timestamp", "strategy", "ticker", "action", "price", "qty", "cost", "fee"]
    
    rows = []
    for row in reader:
        if not row: continue
        # Handle the messy row 6 and others
        if len(row) > 8:
            # Likely has extra fee or cost columns
            # We'll take the first 6 columns, then the last 2 if they look like cost/fee
            # Actually, let's just take the first 8 and hope for the best, or fix specifically
            new_row = row[:6]
            # Try to find cost and fee
            # In row 6: 1.1900000000000002,0.07 ,0.00
            # It seems cost is at index 6 and fee is at index 7 or 8.
            cost = row[6].strip()
            fee = row[7].strip() if len(row) > 7 else "0.00"
            new_row.extend([cost, fee])
            rows.append(new_row)
        elif len(row) == 7:
            row.append("0.00")
            rows.append(row)
        elif len(row) == 8:
            rows.append(row)
        else:
            # Too short, skip or pad
            while len(row) < 8:
                row.append("0.00")
            rows.append(row[:8])

with open(output_file, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(new_header)
    writer.writerows(rows)
