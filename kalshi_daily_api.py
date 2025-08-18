#!/usr/bin/env python3
"""
Simple API server to fetch Kalshi market data for a single day
Uses the same working code from kalshi_temp_backtest.py
"""

import json
import sys
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path

# Import the working Kalshi client from backtest
sys.path.append('BACKLOG!')
from kalshi_temp_backtest import KalshiClient, build_candles, infer_price_field

class KalshiDailyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests for market data"""
        try:
            # Parse URL and query parameters
            parsed = urlparse(self.path)
            if parsed.path != '/markets':
                self.send_error(404, "Not Found")
                return
            
            params = parse_qs(parsed.query)
            date = params.get('date', [None])[0]
            
            if not date:
                self.send_error(400, "Missing 'date' parameter (format: YYYY-MM-DD)")
                return
            
            # Validate date format
            try:
                date_obj = datetime.strptime(date, '%Y-%m-%d')
            except ValueError:
                self.send_error(400, "Invalid date format. Use YYYY-MM-DD")
                return
            
            print(f"Fetching Kalshi markets for {date}...")
            
            # Use the working Kalshi client
            client = KalshiClient()
            
            # Get all KXHIGHNY markets
            print("Fetching all KXHIGHNY markets...")
            all_markets = client.list_markets_by_series('KXHIGHNY', limit=2000)
            
            # Convert date to Kalshi format (25AUG12)
            kalshi_date = date_obj.strftime('%y%b%d').upper()
            print(f"Looking for markets with date: {kalshi_date}")
            
            # Filter for the requested date
            date_markets = []
            for market in all_markets:
                ticker = market.get('ticker', '')
                if kalshi_date in ticker:
                    date_markets.append(market)
            
            print(f"Found {len(date_markets)} markets for {date}")
            
            # Get market history for each market
            markets_with_data = []
            for market in date_markets:
                market_id = market.get('id') or market.get('ticker')
                ticker = market.get('ticker', str(market_id))
                
                print(f"Fetching history for {ticker}...")
                
                try:
                    # Get candlestick data using the working method (same as backtest)
                    points = client.get_market_history_cached(str(market_id))
                    print(f"  -> Got {len(points) if points else 0} data points from get_market_history_cached")
                    
                    # If no points, try the same fallback as backtest file
                    if not points:
                        print(f"  -> Trying trades fallback for {ticker}...")
                        market_uuid = None
                        if len(str(market_id)) >= 36 and str(market_id).count("-") >= 4:
                            market_uuid = str(market_id)
                        else:
                            try:
                                r = client.session.get(
                                    f"https://api.elections.kalshi.com/v1/markets_by_ticker/{ticker}",
                                    timeout=client.timeout_s,
                                )
                                if r.status_code < 400:
                                    market_uuid = r.json().get("market", {}).get("id")
                                    print(f"  -> Resolved {ticker} to UUID: {market_uuid}")
                            except Exception as e:
                                print(f"  -> UUID resolution failed: {e}")
                        
                        if market_uuid:
                            # Import the trades function from backtest
                            from kalshi_temp_backtest import fetch_public_trades_elections_v1
                            trades = fetch_public_trades_elections_v1(client.session, market_uuid, limit=1000)
                            print(f"  -> Got {len(trades)} trades from elections v1")
                            # Map to points compatible with candle builder
                            points = [
                                {"ts": t.get("create_date"), "last_price": float(t.get("price", 0))}
                                for t in trades
                                if t.get("create_date") is not None and isinstance(t.get("price"), (int, float))
                            ]
                            print(f"  -> Converted to {len(points)} price points")
                    
                    # Convert to our format
                    if points:
                        # Build candles with 5-minute intervals
                        candles = build_candles(points, interval_seconds=300)
                        
                        # Convert to website format
                        market_data = {
                            'ticker': ticker,
                            'id': market_id,
                            'status': market.get('status', 'unknown'),
                            'result': market.get('result'),
                            'settlement_value': market.get('settlement_value'),
                            'expiration_value': market.get('expiration_value'),
                            'last_price': market.get('last_price'),
                            'title': market.get('title', ''),
                            'data': []
                        }
                        
                        # Add candlestick data
                        for candle in candles:
                            market_data['data'].append({
                                'timestamp': candle['start'],
                                'open': candle['open'],
                                'high': candle['high'], 
                                'low': candle['low'],
                                'close': candle['close'],
                                'count': candle['count']
                            })
                        
                        markets_with_data.append(market_data)
                    else:
                        print(f"  -> No data points for {ticker}")
                        
                except Exception as e:
                    print(f"  -> Error fetching history for {ticker}: {e}")
                
                # If no market data was added above, add market without data
                if not any(m['ticker'] == ticker for m in markets_with_data):
                    markets_with_data.append({
                        'ticker': ticker,
                        'id': market_id,
                        'status': market.get('status', 'unknown'),
                        'result': market.get('result'),
                        'settlement_value': market.get('settlement_value'),
                        'expiration_value': market.get('expiration_value'),
                        'last_price': market.get('last_price'),
                        'title': market.get('title', ''),
                        'data': []
                    })
            
            # Return JSON response
            response_data = {
                'date': date,
                'kalshi_date': kalshi_date,
                'markets_found': len(date_markets),
                'markets_with_data': len([m for m in markets_with_data if m['data']]),
                'markets': markets_with_data
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')  # Allow CORS
            self.send_header('Access-Control-Allow-Methods', 'GET')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            self.wfile.write(json.dumps(response_data, indent=2).encode())
            
        except Exception as e:
            print(f"Server error: {e}")
            self.send_error(500, f"Internal server error: {str(e)}")
    
    def do_OPTIONS(self):
        """Handle preflight CORS requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def run_server(port=8082):
    """Run the API server"""
    server = HTTPServer(('localhost', port), KalshiDailyHandler)
    print(f"🚀 Kalshi Daily API server running on http://localhost:{port}")
    print(f"📊 Example: http://localhost:{port}/markets?date=2025-08-12")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
        server.shutdown()

if __name__ == '__main__':
    run_server()