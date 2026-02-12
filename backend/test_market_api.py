"""
Test script for Yahoo Finance integration
Run this to test the new market data endpoints
"""

import requests
import json

BASE_URL = "http://localhost:5000/api"

def test_market_indices():
    """Test the market indices endpoint"""
    print("\n=== Testing Market Indices ===")
    try:
        response = requests.get(f"{BASE_URL}/market/indices")
        data = response.json()
        
        if data['success']:
            print("✓ Market indices endpoint working!")
            print(f"\nNIFTY 50: {data['nifty']['value']}")
            print(f"Change: {data['nifty']['change']} ({data['nifty']['change_percent']}%)")
            print(f"\nSENSEX: {data['sensex']['value']}")
            print(f"Change: {data['sensex']['change']} ({data['sensex']['change_percent']}%)")
        else:
            print(f"✗ Error: {data.get('error')}")
    except Exception as e:
        print(f"✗ Error connecting to server: {e}")
        print("Make sure the Flask backend is running on port 5000")

def test_top_stocks():
    """Test the top stocks endpoint"""
    print("\n=== Testing Top Stocks ===")
    try:
        response = requests.get(f"{BASE_URL}/market/top-stocks")
        data = response.json()
        
        if data['success']:
            print("✓ Top stocks endpoint working!")
            print(f"\nTop 3 Gainers:")
            for stock in data['top_gainers'][:3]:
                print(f"  {stock['symbol']}: ₹{stock['price']} (+{stock['change_percent']}%)")
            
            print(f"\nTop 3 Losers:")
            for stock in data['top_losers'][:3]:
                print(f"  {stock['symbol']}: ₹{stock['price']} ({stock['change_percent']}%)")
        else:
            print(f"✗ Error: {data.get('error')}")
    except Exception as e:
        print(f"✗ Error connecting to server: {e}")
        print("Make sure the Flask backend is running on port 5000")

if __name__ == "__main__":
    print("\n" + "="*50)
    print("Yahoo Finance Integration Test")
    print("="*50)
    
    test_market_indices()
    test_top_stocks()
    
    print("\n" + "="*50)
    print("Test completed!")
    print("="*50 + "\n")
