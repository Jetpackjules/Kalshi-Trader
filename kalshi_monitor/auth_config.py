"""
Kalshi API Key Authentication Configuration

Instructions:
1. Sign up for Kalshi account at https://kalshi.com
2. Go to Account Settings → Profile Settings
3. Click "Create New API Key"
4. Save the Key ID and Private Key
5. Set environment variables:
   export KALSHI_API_KEY="your-key-id"
   export KALSHI_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----..."
   
Or create a .env file with:
   KALSHI_API_KEY=your-key-id
   KALSHI_PRIVATE_KEY_FILE=path/to/private_key.pem
"""

import os
import base64
import hashlib
import hmac
import time
from typing import Optional, Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def get_kalshi_api_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Get Kalshi API key and private key from environment variables"""
    
    # Try environment variables first
    api_key = os.getenv('KALSHI_API_KEY')
    private_key = os.getenv('KALSHI_PRIVATE_KEY')
    private_key_file = os.getenv('KALSHI_PRIVATE_KEY_FILE')
    
    # If private key file specified, read it
    if private_key_file and os.path.exists(private_key_file):
        with open(private_key_file, 'r') as f:
            private_key = f.read()
    
    if api_key and private_key:
        return api_key, private_key
    
    # Try .env file
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        env_vars = {}
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key] = value
        
        api_key = env_vars.get('KALSHI_API_KEY')
        private_key = env_vars.get('KALSHI_PRIVATE_KEY')
        private_key_file = env_vars.get('KALSHI_PRIVATE_KEY_FILE')
        
        # If private key file specified, read it
        if private_key_file and os.path.exists(private_key_file):
            with open(private_key_file, 'r') as f:
                private_key = f.read()
        
        if api_key and private_key:
            return api_key, private_key
    
    return None, None

def api_credentials_available() -> bool:
    """Check if Kalshi API credentials are available"""
    api_key, private_key = get_kalshi_api_credentials()
    return api_key is not None and private_key is not None

def generate_kalshi_headers(method: str, path: str, api_key: str, private_key_str: str) -> dict:
    """Generate required Kalshi API authentication headers"""
    
    # Get current timestamp in milliseconds
    timestamp = str(int(time.time() * 1000))
    
    # Create message to sign: timestamp + method + path
    message = timestamp + method.upper() + path
    
    try:
        # Load private key
        private_key = serialization.load_pem_private_key(
            private_key_str.encode(),
            password=None
        )
        
        # Sign the message
        signature = private_key.sign(
            message.encode(),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        
        # Base64 encode the signature
        signature_b64 = base64.b64encode(signature).decode()
        
        return {
            'KALSHI-ACCESS-KEY': api_key,
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'KALSHI-ACCESS-SIGNATURE': signature_b64
        }
        
    except Exception as e:
        raise Exception(f"Failed to generate Kalshi auth headers: {e}")