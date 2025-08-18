#!/usr/bin/env python3
"""
Test to examine actual Kalshi candlestick data structure
"""

import requests
import time
import base64
import json
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def test_candlestick_data():
    # Your credentials
    api_key = "8adbb05c-01ca-42cf-af00-f05e551f0c25"
    
    private_key_pem = """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAqkoVL0VKq0AqkfKcLVDpkEILw4WplKvecsDCsIwQnIK1qmtq
n2VH9IAy3H3ai7SeErNJvkcP//QGwQiGIwE4pcAtjz7zwX/gwdB9xiqWPUZ03Gps
navhaFF+SmJDDwov2Ksp4oGMHqz8hBXV6h2rfDb83xRfelpK8I6CdcKqJDk7CcRo
E5VhJm7eEf/UlnEU78HoTzRWeglP3aqnbGy1wI7XOnnsfHNET0nW6zlTXKu11/1V
A+6rmm6sRDaKxeRKB60G3SYdbW6lwnnP8WyXdut0aEFZ1JTeyoaWm/MypnUySAbW
SnpT8R1WlfYX0IaHiUAMRpUiFLTmYNW6hunBcwIDAQABAoIBAEstEVUg/enEFgcA
V7oZskKhJZhXdZnQlg+K0WgnLV4qxhBKA3QCvlVOEyYL2WM7hV00ESYTMRkJncGy
BaWGcH+b64EFhY6y6YImjJ/jRRgf9o8n3HNu4b+v2lT0NC57jMvWJFN+ZWFVdNTK
3vjPyFi53cCNuejF27d+8lEScxIyCS/c73OgseF6p/fqvnYDrh1E8RZOPGi84O/0
/k44uzjlFb9AonSzcdt+qV/N7SOW4MBlpsM4417VHPpCf4qSIpZYG5u1JV0NjtTn
PQAJCCRybmewVCJiHD4JNeJ5ry/IlxGHCPhOEA75j6rEH6qEpkkuPC+Z0RklP907
Eugy6KECgYEAxstFu7nYkRmtA7bMijLWomSQbv0p5sC1YYJ6m/+LpJ+27j26OjGw
OT/rek/kPccfXZhHmRrZnH80Aq/4Z9eEuVcctwtCGHXVqLQMHcL4Glbn4yI6gWoe
EJDLLoqKOsJYjsrv3yf1cEoEhBukHWsHsrK/Nb8L/IoMqJuqv/y6ZZ8CgYEA20rv
OujwDISPFgrDP+friE1elF4dqpeWLC5TxZnoc4rzLMxGNh7Saqq0kn0u9RRl1XEG
5fxEvwyScIfTBTD3/nnAQKNFYIKh1n3B82HmIpx4MtxaezyTD8XOV7gUwLw5vfrA
uaCHJrbDCm6JPbDzhB/5qKS3rsVRjdfmfcjiy60CgYAJscgIy5tgGBxz3epDow8M
hFL21qnAcw1lX/OSv/eTY6aMH76BMAMkB5X4NQUwbhF9gvua39BU7W8f4mz+w2fZ
kgH4ezgR8U0mGQGuQd/PiQVt8jFgNkiZDjaaYm8zRl8DN6pS+6PggfuOZbqvJJUP
heAFQvfWrPTJFC5ThoOgiQKBgQCts8WbnDfJMpdElnHihQqEhQSN8Z7+KeTCSlAB
DdCa9U16BrT22aNC6sTt5Er1xpqDX2xfcFvkGUlF6dC1I/zMjhRDHxEtSUx4YlTn
PHzWnap4XyMsyuaSb9Tqlt2ZbX8vhRhz8Twc5lfIQ5ZiT3AVEF7pvs/gmFvpR0NE
D4PWYQKBgEm1yavtAsOTAFVp5V2fQj3c46xY9hPrpxtKtYAa3C1/ymIB67Seqb4r
0xOgCgm7G76hwiIwinqR1OQEm2STc04vAC4Kz6q+B5/33lNDpB8O3WIKO6y9EhYo
hGQ70DBQdt74CM1k4mNehDs9afy1PTTksmHKx4f1uDt8xdqzkg0Q
-----END RSA PRIVATE KEY-----"""
    
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    
    # First, let's get active markets to find a current one
    path_events = "/events"
    timestamp = str(int(time.time() * 1000))
    message = timestamp + "GET" + path_events
    
    signature = private_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature).decode()
    
    headers = {
        'KALSHI-ACCESS-KEY': api_key,
        'KALSHI-ACCESS-TIMESTAMP': timestamp,
        'KALSHI-ACCESS-SIGNATURE': signature_b64,
        'User-Agent': 'candlestick-test/1.0',
        'Accept': 'application/json'
    }
    
    events_url = f"https://api.elections.kalshi.com/trade-api/v2{path_events}"
    events_response = requests.get(events_url, headers=headers, params={'limit': 100})
    
    # Find an active temperature market
    active_market = None
    if events_response.status_code == 200:
        events_data = events_response.json()
        for event in events_data.get('events', []):
            if 'HIGH' in event.get('event_ticker', ''):
                markets = event.get('markets', [])
                for market in markets:
                    if market.get('status') == 'open':
                        active_market = market
                        series_ticker = event.get('event_ticker', '')
                        ticker = market.get('ticker', '')
                        print(f"🎯 Found active market: {ticker}")
                        break
                if active_market:
                    break
    
    if not active_market:
        print("❌ No active temperature markets found")
        return
        
    # Get candlesticks for this active market
    now = int(time.time())
    start_ts = now - (24 * 3600)  # 24 hours ago
    end_ts = now
    
    path = f"/series/{series_ticker}/markets/{ticker}/candlesticks"
    timestamp = str(int(time.time() * 1000))
    message = timestamp + "GET" + path
    
    signature = private_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature).decode()
    
    headers = {
        'KALSHI-ACCESS-KEY': api_key,
        'KALSHI-ACCESS-TIMESTAMP': timestamp,
        'KALSHI-ACCESS-SIGNATURE': signature_b64,
        'User-Agent': 'candlestick-test/1.0',
        'Accept': 'application/json'
    }
    
    url = f"https://api.elections.kalshi.com/trade-api/v2{path}"
    params = {
        'start_ts': start_ts,
        'end_ts': end_ts,
        'period_interval': 60  # 1 hour
    }
    
    print(f"🔍 Testing candlesticks for {ticker}")
    print(f"Time range: {datetime.fromtimestamp(start_ts)} to {datetime.fromtimestamp(end_ts)}")
    
    response = requests.get(url, headers=headers, params=params)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        candlesticks = data.get('candlesticks', [])
        print(f"📊 Retrieved {len(candlesticks)} candlesticks")
        
        if candlesticks:
            print("\nFirst few candlesticks:")
            for i, candle in enumerate(candlesticks[:3]):
                print(f"  {i+1}. {json.dumps(candle, indent=2)}")
        else:
            print("No candlestick data found")
            
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    test_candlestick_data()