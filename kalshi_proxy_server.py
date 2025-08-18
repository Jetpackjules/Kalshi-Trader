#!/usr/bin/env python3
"""
Simple CORS proxy server to make Kalshi API calls work from browser
"""
import sys
import json
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
sys.path.append('BACKLOG!')
from kalshi_temp_backtest import KalshiClient

class KalshiProxyHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.kalshi_client = KalshiClient()
        super().__init__(*args, **kwargs)
    
    def do_OPTIONS(self):
        """Handle preflight CORS requests"""
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests and proxy to Kalshi API"""
        try:
            parsed_url = urlparse(self.path)
            
            if parsed_url.path == '/markets':
                self.handle_markets_request(parsed_url)
            elif parsed_url.path.startswith('/candlesticks/'):
                self.handle_candlesticks_request(parsed_url)
            else:
                self.send_error(404, "Endpoint not found")
                
        except Exception as e:
            print(f"Error handling request: {e}")
            self.send_error(500, str(e))
    
    def handle_markets_request(self, parsed_url):
        """Handle /markets requests"""
        query_params = parse_qs(parsed_url.query)
        
        # Get date parameter
        date_param = query_params.get('date', [None])[0]
        series = query_params.get('series_ticker', ['KXHIGHNY'])[0]
        
        print(f"📊 Fetching markets for date: {date_param}, series: {series}")
        
        # Get all KXHIGHNY markets
        all_markets = self.kalshi_client.list_markets_by_series(series, limit=2000)
        print(f"Found {len(all_markets)} total {series} markets")
        
        if date_param:
            # Convert date to Kalshi format (25AUG12)
            from datetime import datetime
            date_obj = datetime.strptime(date_param, '%Y-%m-%d')
            year = date_obj.strftime('%y')
            month = date_obj.strftime('%b').upper()
            day = date_obj.strftime('%d')
            kalshi_date = f"{year}{month}{day}"
            
            print(f"Looking for markets with date: {kalshi_date}")
            
            # Filter for the requested date
            date_markets = []
            for market in all_markets:
                ticker = market.get('ticker', '')
                if kalshi_date in ticker:
                    date_markets.append(market)
            
            print(f"Found {len(date_markets)} markets for {date_param}")
            filtered_markets = date_markets
        else:
            filtered_markets = all_markets
        
        # Return the markets data
        response_data = {
            'markets': filtered_markets,
            'total': len(filtered_markets),
            'date': date_param
        }
        
        self.send_response(200)
        self.send_cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_data).encode())
    
    def handle_candlesticks_request(self, parsed_url):
        """Handle /candlesticks/{market_id} requests"""
        # Extract market_id from path
        path_parts = parsed_url.path.split('/')
        market_id = path_parts[2] if len(path_parts) > 2 else None
        
        if not market_id:
            self.send_error(400, "Market ID required")
            return
        
        print(f"📈 Fetching candlestick data for market: {market_id}")
        
        try:
            # Get market history
            points = self.kalshi_client.get_market_history_cached(market_id)
            
            response_data = {
                'market_id': market_id,
                'points': points or [],
                'total': len(points) if points else 0
            }
            
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())
            
        except Exception as e:
            print(f"Error fetching candlestick data: {e}")
            self.send_error(500, str(e))
    
    def send_cors_headers(self):
        """Send CORS headers to allow browser requests"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')

def run_proxy_server(port=8083):
    """Start the CORS proxy server"""
    server = HTTPServer(('localhost', port), KalshiProxyHandler)
    print(f"🚀 Kalshi CORS Proxy Server running on http://localhost:{port}")
    print("This proxy allows browser API calls to Kalshi without CORS issues")
    print("Available endpoints:")
    print(f"  GET /markets?date=YYYY-MM-DD&series_ticker=KXHIGHNY")
    print(f"  GET /candlesticks/{{market_id}}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
        server.server_close()

if __name__ == '__main__':
    run_proxy_server()