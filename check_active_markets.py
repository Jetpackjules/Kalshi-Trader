#!/usr/bin/env python3
"""
Check what active markets are available
"""

import requests
import time
import base64
import json
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def check_markets():
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
    
    path = "/events"
    timestamp = str(int(time.time() * 1000))
    message = timestamp + "GET" + path
    
    signature = private_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature).decode()
    
    headers = {
        'KALSHI-ACCESS-KEY': api_key,
        'KALSHI-ACCESS-TIMESTAMP': timestamp,
        'KALSHI-ACCESS-SIGNATURE': signature_b64,
        'User-Agent': 'market-checker/1.0',
        'Accept': 'application/json'
    }
    
    url = f"https://api.elections.kalshi.com/trade-api/v2{path}"
    response = requests.get(url, headers=headers, params={'limit': 50})
    
    if response.status_code == 200:
        data = response.json()
        events = data.get('events', [])
        
        print(f"📊 Found {len(events)} events")
        
        temp_events = []
        for event in events:
            event_ticker = event.get('event_ticker', '')
            title = event.get('title', '')
            
            # Look for temperature-related events
            if any(keyword in event_ticker.upper() for keyword in ['HIGH', 'LOW', 'TEMP', 'KXHIGH', 'KXLOW']):
                temp_events.append(event)
                print(f"🌡️ Temperature event: {event_ticker} - {title}")
                
                markets = event.get('markets', [])
                for market in markets[:3]:  # Show first 3 markets
                    ticker = market.get('ticker', '')
                    status = market.get('status', '')
                    last_price = market.get('last_price', 'N/A')
                    print(f"   Market: {ticker} (Status: {status}, Price: ${last_price})")
                    
        if not temp_events:
            print("❌ No temperature events found")
            print("\nAll available events:")
            for event in events[:10]:  # Show first 10 events
                event_ticker = event.get('event_ticker', '')
                title = event.get('title', '')
                print(f"  {event_ticker} - {title}")
                
    else:
        print(f"Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    check_markets()