#!/usr/bin/env python3
"""
Temperature API Server for Kalshi Market Viewer
Provides real-time temperature data from weather APIs
"""

import json
import sys
import os
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import traceback

# Add modules directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

try:
    from modules.nws_api import NWSAPI
    from modules.synoptic_api import SynopticAPI  
    from modules.ncei_asos import NCEIASOS
except ImportError as e:
    print(f"Error importing weather APIs: {e}")
    sys.exit(1)

class TempAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        # Enable CORS
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        try:
            if parsed_path.path == '/api/temperature':
                self.handle_temperature_request(parsed_path.query)
            elif parsed_path.path == '/api/available_apis':
                self.handle_available_apis()
            else:
                self.send_error_response("Unknown endpoint")
                
        except Exception as e:
            print(f"Error handling request: {e}")
            traceback.print_exc()
            self.send_error_response(str(e))
    
    def do_OPTIONS(self):
        # Handle preflight requests
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def handle_available_apis(self):
        """Return list of available APIs that can provide real-time data"""
        apis = []
        
        # Test each API for real-time capability
        test_date = datetime.now().date() - timedelta(days=1)  # Yesterday for testing
        
        # NWS API - can get data within hours
        try:
            nws = NWSAPI()
            result = nws.get_daily_max_temperature(test_date)
            if result['success']:
                apis.append({
                    'id': 'nws',
                    'name': 'NWS API',
                    'description': 'National Weather Service observations',
                    'real_time': True,
                    'delay_minutes': 60  # Usually 1 hour delay
                })
        except Exception as e:
            print(f"NWS API test failed: {e}")
        
        # Synoptic API - real-time data
        try:
            synoptic = SynopticAPI()
            result = synoptic.get_daily_max_temperature(test_date)
            if result['success']:
                apis.append({
                    'id': 'synoptic',
                    'name': 'Synoptic API', 
                    'description': 'High-frequency weather station data',
                    'real_time': True,
                    'delay_minutes': 5  # Near real-time
                })
        except Exception as e:
            print(f"Synoptic API test failed: {e}")
        
        # ASOS - historical only, skip for real-time
        # NCEI ASOS has significant delay, not suitable for real-time
        
        response = {
            'success': True,
            'apis': apis,
            'count': len(apis)
        }
        
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def handle_temperature_request(self, query):
        """Handle temperature data request for a specific date and API"""
        params = parse_qs(query)
        
        # Parse parameters
        date_str = params.get('date', [None])[0]
        api_name = params.get('api', [None])[0]
        
        if not date_str or not api_name:
            self.send_error_response("Missing date or api parameter")
            return
        
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            self.send_error_response("Invalid date format. Use YYYY-MM-DD")
            return
        
        # Get temperature data
        temp_data = self.get_temperature_data(api_name, target_date)
        self.wfile.write(json.dumps(temp_data, indent=2).encode())
    
    def get_temperature_data(self, api_name, target_date):
        """Fetch temperature data from specified API"""
        
        if api_name == 'nws':
            api = NWSAPI()
        elif api_name == 'synoptic':
            api = SynopticAPI()
        elif api_name == 'asos':
            api = NCEIASOS()
        else:
            return {'success': False, 'error': f'Unknown API: {api_name}'}
        
        try:
            result = api.get_daily_max_temperature(target_date)
            
            if result.get('success'):
                # Get detailed temperature timeline if available
                timeline_data = []
                
                if hasattr(api, 'get_hourly_data'):
                    try:
                        hourly = api.get_hourly_data(target_date)
                        if hourly.get('success'):
                            timeline_data = hourly.get('data', [])
                    except:
                        pass  # Fallback to daily max only
                
                # Convert datetime to string if needed
                max_time = result.get('max_time')
                if hasattr(max_time, 'isoformat'):
                    max_time = max_time.isoformat()
                elif hasattr(max_time, 'strftime'):
                    max_time = max_time.strftime('%Y-%m-%d %H:%M:%S')
                
                response = {
                    'success': True,
                    'api': api_name,
                    'date': target_date.isoformat(),
                    'max_temperature': result.get('max_temperature'),
                    'max_time': str(max_time) if max_time else None,
                    'observation_count': result.get('observation_count', 0),
                    'timeline': timeline_data,
                    'source': result.get('source', 'Unknown')
                }
            else:
                response = {
                    'success': False,
                    'api': api_name,
                    'date': target_date.isoformat(),
                    'error': result.get('error', 'Unknown error')
                }
                
            return response
            
        except Exception as e:
            return {
                'success': False,
                'api': api_name,
                'date': target_date.isoformat(),
                'error': str(e)
            }
    
    def send_error_response(self, message):
        """Send JSON error response"""
        response = {
            'success': False,
            'error': message
        }
        self.wfile.write(json.dumps(response).encode())
    
    def log_message(self, format, *args):
        """Override to reduce logging noise"""
        return

def main():
    port = 8081
    server = HTTPServer(('localhost', port), TempAPIHandler)
    print(f"🌡️ Temperature API Server running on http://localhost:{port}")
    print("Available endpoints:")
    print(f"  GET /api/available_apis - List real-time capable APIs")
    print(f"  GET /api/temperature?date=YYYY-MM-DD&api=nws - Get temperature data")
    print("\nPress Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()

if __name__ == '__main__':
    main()