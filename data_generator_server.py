#!/usr/bin/env python3
"""
Simple server to handle data generation requests from the UI
"""
import json
import subprocess
import time
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import threading

class DataGeneratorHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Serve the HTML file"""
        if self.path == '/' or self.path == '/data_generator_ui.html':
            self.serve_html()
        else:
            self.send_error(404, "File not found")
    
    def do_POST(self):
        """Handle data generation requests"""
        if self.path == '/generate-data':
            self.handle_generate_data()
        elif self.path == '/list-markets':
            self.handle_list_markets()
        elif self.path == '/get-market-data':
            self.handle_get_market_data()
        else:
            self.send_error(404, "Endpoint not found")
    
    def serve_html(self):
        """Serve the HTML UI file"""
        try:
            with open('data_generator_ui.html', 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(content.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
            
        except FileNotFoundError:
            self.send_error(404, "UI file not found")
        except Exception as e:
            self.send_error(500, f"Error serving file: {e}")
    
    def handle_generate_data(self):
        """Handle data generation request"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data.decode('utf-8'))
            
            outdir = request_data.get('outdir', './data')
            target_date = request_data.get('targetDate', '2025-08-12')
            interval = request_data.get('interval', '5m')
            
            print(f"🚀 Starting data generation: outdir={outdir}, targetDate={target_date}, interval={interval}")
            
            # Calculate days back from today to target date
            from datetime import datetime, date
            try:
                target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()
                today = date.today()
                days_back = (today - target_dt).days
                
                # Ensure we get at least the target date by adding a buffer
                days_back = max(days_back + 7, 7)  # At least 7 days, or days back + 7
                
                print(f"📅 Target date: {target_date}, Days back from today: {days_back}")
            except Exception as e:
                print(f"❌ Error parsing date, using default: {e}")
                days_back = 30
            
            # Build command using --days parameter
            cmd = [
                'python3', 
                'BACKLOG!/kalshi_temp_backtest.py',
                '--outdir', str(outdir),
                '--days', str(days_back),
                '--interval', str(interval)
            ]
            
            print(f"🔧 Running command: {' '.join(cmd)}")
            
            # Run the command
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            duration = time.time() - start_time
            
            print(f"⏱️ Command completed in {duration:.2f} seconds")
            print(f"📤 Return code: {result.returncode}")
            
            if result.returncode == 0:
                # Success
                response_data = {
                    'success': True,
                    'outdir': outdir,
                    'duration': f"{duration:.2f}s",
                    'stdout': result.stdout,
                    'stderr': result.stderr
                }
                
                # Count generated files
                try:
                    candles_dir = os.path.join(outdir, 'candles')
                    if os.path.exists(candles_dir):
                        files = [f for f in os.listdir(candles_dir) if f.endswith('.csv')]
                        response_data['files_created'] = len(files)
                except:
                    pass
                
                print(f"✅ Success: Generated data in {outdir}")
                
            else:
                # Error
                response_data = {
                    'success': False,
                    'error': f"Command failed with code {result.returncode}",
                    'stdout': result.stdout,
                    'stderr': result.stderr
                }
                print(f"❌ Error: Command failed with code {result.returncode}")
                print(f"stderr: {result.stderr}")
            
            # Send response
            response_json = json.dumps(response_data).encode('utf-8')
            self.send_response(200 if response_data['success'] else 500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_json)))
            self.end_headers()
            self.wfile.write(response_json)
            
        except subprocess.TimeoutExpired:
            error_response = {
                'success': False,
                'error': 'Command timed out after 5 minutes'
            }
            response_json = json.dumps(error_response).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_json)))
            self.end_headers()
            self.wfile.write(response_json)
            
        except Exception as e:
            print(f"❌ Server error: {e}")
            error_response = {
                'success': False,
                'error': str(e)
            }
            response_json = json.dumps(error_response).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_json)))
            self.end_headers()
            self.wfile.write(response_json)
    
    def handle_list_markets(self):
        """List available market CSV files"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data.decode('utf-8'))
            
            outdir = request_data.get('outdir', './data')
            candles_dir = os.path.join(outdir, 'candles')
            
            files = []
            if os.path.exists(candles_dir):
                files = [f for f in os.listdir(candles_dir) if f.endswith('.csv')]
                files.sort()
            
            response_data = {
                'success': True,
                'files': files,
                'directory': candles_dir
            }
            
            response_json = json.dumps(response_data).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_json)))
            self.end_headers()
            self.wfile.write(response_json)
            
        except Exception as e:
            error_response = {'success': False, 'error': str(e)}
            response_json = json.dumps(error_response).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_json)))
            self.end_headers()
            self.wfile.write(response_json)
    
    def handle_get_market_data(self):
        """Get candlestick data from CSV file"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data.decode('utf-8'))
            
            outdir = request_data.get('outdir', './data')
            filename = request_data.get('filename', '')
            
            if not filename:
                raise ValueError('Filename required')
            
            csv_path = os.path.join(outdir, 'candles', filename)
            
            if not os.path.exists(csv_path):
                raise FileNotFoundError(f'File not found: {csv_path}')
            
            # Read CSV data
            data = []
            with open(csv_path, 'r') as f:
                lines = f.readlines()
                header = lines[0].strip().split(',') if lines else []
                
                for line in lines[1:]:  # Skip header
                    if line.strip():
                        values = line.strip().split(',')
                        if len(values) >= 6:
                            try:
                                data.append({
                                    'timestamp': values[0],
                                    'open': float(values[1]),
                                    'high': float(values[2]),
                                    'low': float(values[3]),
                                    'close': float(values[4]),
                                    'volume': int(float(values[5])) if len(values) > 5 else 0
                                })
                            except (ValueError, IndexError):
                                continue
            
            response_data = {
                'success': True,
                'data': data,
                'filename': filename,
                'count': len(data)
            }
            
            response_json = json.dumps(response_data).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_json)))
            self.end_headers()
            self.wfile.write(response_json)
            
        except Exception as e:
            error_response = {'success': False, 'error': str(e)}
            response_json = json.dumps(error_response).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response_json)))
            self.end_headers()
            self.wfile.write(response_json)

def run_server(port=8086):
    """Start the data generator server"""
    server = HTTPServer(('localhost', port), DataGeneratorHandler)
    print(f"🚀 Kalshi Data Generator Server running on http://localhost:{port}")
    print("📊 Access the UI at: http://localhost:8086")
    print("🔧 Ready to generate candlestick data")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
        server.server_close()

if __name__ == '__main__':
    run_server()