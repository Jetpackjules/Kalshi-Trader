import time
import base64
import requests
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
KEY_PATH = "kalshi_prod_private_key.pem"

def sign_pss_text(private_key, text: str) -> str:
    message = text.encode('utf-8')
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

def create_headers(private_key, method: str, path: str) -> dict:
    timestamp = str(int(time.time() * 1000))
    msg_string = timestamp + method + path.split('?')[0]
    signature = sign_pss_text(private_key, msg_string)
    return {
        "Content-Type": "application/json",
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
    }

def check_balance(url):
    try:
        with open(KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
        
        path = "/trade-api/v2/portfolio/balance"
        headers = create_headers(private_key, "GET", path)
        resp = requests.get(url + path, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            balance = float(data.get("balance", 0.0)) / 100.0
            return f"Balance: ${balance:.2f}"
        else:
            return f"Error: {resp.status_code} {resp.text}"
    except Exception as e:
        return f"Exception: {e}"

print("Elections API:", check_balance("https://api.elections.kalshi.com"))
print("Main API:", check_balance("https://api.kalshi.com"))
