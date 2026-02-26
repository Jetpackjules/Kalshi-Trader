import requests
import time
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

with open('keys/kalshi_prod_private_key.pem', 'rb') as f:
    priv_key = serialization.load_pem_private_key(f.read(), password=None)

current_time = int(time.time() * 1000)
method = 'GET'
path = '/trade-api/v2/portfolio/orders?ticker=KXHIGHNY-26FEB24-B28.5'
msg_string = str(current_time) + method + path.split('?')[0]
signature = priv_key.sign(msg_string.encode('utf-8'), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
sig_b64 = base64.b64encode(signature).decode('utf-8')

headers = {
    'KALSHI-ACCESS-KEY': 'ab739236-261e-4130-bd46-2c0330d0bf57',
    'KALSHI-ACCESS-SIGNATURE': sig_b64,
    'KALSHI-ACCESS-TIMESTAMP': str(current_time)
}

r = requests.get('https://api.elections.kalshi.com' + path, headers=headers)
data = r.json()
if 'orders' not in data:
    print(r.text)
orders = data.get('orders', [])

sum_filled = 0
sum_cost = 0.0

print("Actual Kalshi Backend Order Ledger:")
for o in reversed(orders):  # Chronological
    side = o.get('side')
    price = o.get('yes_price') if side == 'yes' else o.get('no_price')
    count = o.get('count', 0)
    filled = o.get('filled_count', 0)
    status = o.get('status')
    fee = o.get('taker_fees', 0)
    
    # Calculate exactly what was spent
    cost = (filled * (price/100.0)) + (fee/100.0)
    sum_filled += filled
    sum_cost += cost
    
    print(f"{o.get('created_time')} | {side.upper()} {o.get('action').upper()} | Req: {count}, Filled: {filled} @ Limit {price}c | Status: {status} | Cost: ${cost:.2f}")

print(f'\nTotal Filled Contracts: {sum_filled}')
print(f'Total True Spend: ${sum_cost:.2f}')
