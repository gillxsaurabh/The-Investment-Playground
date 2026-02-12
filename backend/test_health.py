"""Test script to debug stock health service"""
import sys
sys.path.append('/Users/saurabhgill/Documents/Code Base/CogniCap/backend')

from stock_health_service import StockHealthService
from kiteconnect import KiteConnect
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Load access token
with open('access_token.json', 'r') as f:
    token_data = json.load(f)
    access_token = token_data['access_token']

# Setup Kite
API_KEY = os.getenv('KITE_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

kite = KiteConnect(api_key=API_KEY)
kite.set_access_token(access_token)

# Test with a single stock
print("Testing stock health analysis...")
print(f"Gemini API Key present: {bool(GEMINI_API_KEY)}")

# Create service
service = StockHealthService(kite_instance=kite, gemini_api_key=GEMINI_API_KEY)

# Get one holding
holdings = kite.holdings()
print(f"\nTotal holdings: {len(holdings)}")

if holdings:
    test_holding = holdings[0]
    print(f"\nTesting with: {test_holding['tradingsymbol']}")
    
    # Test individual components
    print("\n1. Testing yfinance symbol mapping...")
    yf_symbol = service._map_to_yfinance_symbol(
        test_holding['tradingsymbol'], 
        test_holding['exchange']
    )
    print(f"   Mapped to: {yf_symbol}")
    
    print("\n2. Testing technical analysis...")
    technical = service._get_technical_analysis(yf_symbol, test_holding['tradingsymbol'])
    print(f"   Momentum: {technical.get('momentum_score')} - {technical.get('momentum_detail')}")
    print(f"   Trend: {technical.get('trend_score')} - {technical.get('trend_direction')}")
    
    print("\n3. Testing fundamental analysis...")
    fundamental = service._get_fundamental_data(test_holding['tradingsymbol'])
    print(f"   Score: {fundamental.get('score')}")
    print(f"   Summary: {fundamental.get('summary')}")
    
    print("\n4. Testing AI sentiment...")
    ai = service._get_ai_sentiment(test_holding['tradingsymbol'])
    print(f"   Score: {ai.get('score')}")
    print(f"   Summary: {ai.get('summary')}")
    
    print("\n5. Full report test...")
    report = service._analyze_stock(test_holding)
    print(json.dumps(report, indent=2, default=str))
