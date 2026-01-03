import json
import time
import requests
import base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

KEY_ID = "ab739236-261e-4130-bd46-2c0330d0bf57"
PRIVATE_KEY_PATH = r"c:\Users\jetpa\OneDrive - UW\Google_Grav_Onedrive\kalshi_weather_data\live_trading_system\kalshi_prod_private_key.pem"
API_URL = "https://api.elections.kalshi.com"

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

def get_orders():
    try:
        with open(PRIVATE_KEY_PATH, 'rb') as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    except:
        return

    path = "/trade-api/v2/portfolio/orders"
    method = "GET"
    headers = create_headers(private_key, method, path)
    
    try:
        response = requests.get(f"{API_URL}{path}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            orders = data.get("orders", [])
            
            unique_statuses = set(o.get('status') for o in orders)
            print(f"Unique statuses found: {unique_statuses}")
            
            canceled_orders = [o for o in orders if o.get('status') == 'canceled']
            print(f"Found {len(canceled_orders)} CANCELED orders (Total).")
            
            # Sort by created_time descending
            canceled_orders.sort(key=lambda x: x.get('created_time'), reverse=True)
            
            print("Top 5 Canceled Orders:")
            for o in canceled_orders[:5]:
                print(f"Time: {o.get('created_time')} | Ticker: {o.get('ticker')} | ID: {o.get('order_id')}")
                
    except Exception as e:
        print(e)

if __name__ == "__main__":
    get_orders()
