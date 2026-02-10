import os
from dotenv import load_dotenv

load_dotenv()

# Zerodha Kite API credentials
API_KEY = os.getenv('KITE_API_KEY', 'REDACTED_KITE_API_KEY')
API_SECRET = os.getenv('KITE_API_SECRET', 'REDACTED_KITE_API_SECRET')

# File paths
TOKEN_FILE = 'access_token.json'