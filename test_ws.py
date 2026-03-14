import asyncio, json, time, websockets, base64
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
import requests

KEY_ID = 'ab739236-261e-4130-bd46-2c0330d0bf57'
PRIVATE_KEY_PATH = 'kalshi_prod_private_key.pem'
WS_URL = 'wss://api.elections.kalshi.com/trade-api/ws/v2'

def sign_pss_text(private_key, text: str) -> str:
    message = text.encode('utf-8')
    signature = private_key.sign(
        message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256()
    )
    return base64.b64encode(signature).decode('utf-8')

async def run():
    with open(PRIVATE_KEY_PATH, 'rb') as f:
        pk = serialization.load_pem_private_key(f.read(), password=None)
    ts = str(int(time.time() * 1000))
    sig = sign_pss_text(pk, ts + 'GET' + '/trade-api/ws/v2')
    headers = {'KALSHI-ACCESS-KEY': KEY_ID, 'KALSHI-ACCESS-SIGNATURE': sig, 'KALSHI-ACCESS-TIMESTAMP': ts}
    
    r = requests.get('https://api.elections.kalshi.com/trade-api/v2/markets', params={'series_ticker': 'KXHIGHNY', 'status': 'open'})
    tickers = [m['ticker'] for m in r.json().get('markets', [])][:5]
    
    async with websockets.connect(WS_URL, additional_headers=headers) as ws:
        await ws.send(json.dumps({'id': 1, 'cmd': 'subscribe', 'params': {'channels': ['orderbook_delta'], 'market_tickers': tickers}}))
        count = 0
        while count < 3:
            msg_str = await ws.recv()
            try:
                msg = json.loads(msg_str)
                if msg.get('type') == 'orderbook_delta':
                    print(msg)
                    count += 1
            except Exception as e:
                print('Error:', e)

asyncio.run(run())
