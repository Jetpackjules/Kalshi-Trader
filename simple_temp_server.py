#!/usr/bin/env python3
"""
Simple Temperature API Server for testing
"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class SimpleTempHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/api/available_apis':
            response = {
                'success': True,
                'apis': [
                    {
                        'id': 'nws',
                        'name': 'NWS API',
                        'description': 'National Weather Service observations',
                        'real_time': True,
                        'delay_minutes': 60
                    },
                    {
                        'id': 'synoptic',
                        'name': 'Synoptic API',
                        'description': 'High-frequency weather station data',
                        'real_time': True,
                        'delay_minutes': 5
                    }
                ],
                'count': 2
            }
        elif parsed_path.path == '/api/temperature':
            params = parse_qs(parsed_path.query)
            api_name = params.get('api', ['nws'])[0]
            date_str = params.get('date', ['2025-08-11'])[0]
            
            # Mock temperature data
            temp_data = {
                'nws': 88.0,
                'synoptic': 87.5,
                'asos': 88.2
            }
            
            response = {
                'success': True,
                'api': api_name,
                'date': date_str,
                'max_temperature': temp_data.get(api_name, 85.0),
                'max_time': '2025-08-11T14:30:00',
                'observation_count': 25,
                'timeline': [],
                'source': f'{api_name.upper()} API'
            }
        else:
            response = {'success': False, 'error': 'Unknown endpoint'}
        
        self.wfile.write(json.dumps(response).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
    
    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    server = HTTPServer(('localhost', 8081), SimpleTempHandler)
    print("🌡️ Simple Temperature API running on http://localhost:8081")
    server.serve_forever()