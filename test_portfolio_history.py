import requests
import time
import base64
import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization

with open('keys/kalshi_prod_private_key.pem', 'rb') as f:
    priv_key = serialization.load_pem_private_key(f.read(), password=None)

current_time = int(time.time() * 1000)
method = 'GET'
path = '/trade-api/v2/portfolio/history?period=1d'
msg_string = str(current_time) + method + path.split('?')[0]
signature = priv_key.sign(msg_string.encode('utf-8'), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
sig_b64 = base64.b64encode(signature).decode('utf-8')

headers = {
    'KALSHI-ACCESS-KEY': 'ab739236-261e-4130-bd46-2c0330d0bf57',
    'KALSHI-ACCESS-SIGNATURE': sig_b64,
    'KALSHI-ACCESS-TIMESTAMP': str(current_time)
}

r = requests.get('https://api.elections.kalshi.com' + path, headers=headers)
print(r.status_code)
print(json.dumps(r.json(), indent=2)[:500])
