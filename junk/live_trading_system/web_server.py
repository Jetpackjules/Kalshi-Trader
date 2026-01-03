import http.server
import socketserver
import os

PORT = 80

class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers just in case
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

print(f"Starting Web Server on port {PORT}...")
print(f"Access dashboard at: http://<YOUR-VM-IP>:{PORT}/dashboard.html")

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
