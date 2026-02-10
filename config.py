import os
from dotenv import load_dotenv

load_dotenv()

# Zerodha Kite API credentials
API_KEY = os.getenv('KITE_API_KEY', 'bi56trp8ev6rdy9d')
API_SECRET = os.getenv('KITE_API_SECRET', 'zxulw382p4qm0k3yzcmwkec1su5fprrs')

# File paths
TOKEN_FILE = 'access_token.json'