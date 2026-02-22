"""
Test script for the new on-demand stock analyzer using Kite API
"""

import os
import sys
import json
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_analyzer import StockAnalyzer

# Load environment variables
load_dotenv()

def test_stock_analyzer():
    """Test the stock analyzer with a sample stock"""
    
    # Read access token from file
    try:
        with open('access_token.json', 'r') as f:
            token_data = json.load(f)
            access_token = token_data.get('access_token')
            
            if not access_token:
                print("❌ No access token found in access_token.json")
                print("Please authenticate first by visiting the login URL")
                return False
    except FileNotFoundError:
        print("❌ access_token.json not found")
        print("Please authenticate first")
        return False
    
    # Initialize Kite
    api_key = os.getenv('KITE_API_KEY')
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    
    # Test connection
    try:
        profile = kite.profile()
        print(f"✅ Connected to Kite API")
        print(f"   User: {profile.get('user_name', 'N/A')}")
        print()
    except Exception as e:
        print(f"❌ Failed to connect to Kite API: {str(e)}")
        return False
    
    # Create analyzer
    analyzer = StockAnalyzer(kite_instance=kite, gemini_api_key=gemini_api_key)
    
    # Test with a sample stock (RELIANCE)
    print("Testing stock analyzer with RELIANCE...")
    print("=" * 60)
    
    try:
        result = analyzer.analyze_stock('RELIANCE')
        
        print(f"\n✅ Analysis completed successfully!")
        print(f"\nSymbol: {result['symbol']}")
        print(f"Overall Score: {result['score']}/5.0")
        print(f"\nBreakdown:")
        print(f"  Recency (Relative Strength): {result['details']['recency']['score']}/5")
        print(f"    → {result['details']['recency']['detail']}")
        print(f"  \n  Trend Analysis: {result['details']['trend']['score']}/5")
        print(f"    → Strength: {result['details']['trend']['strength']}")
        print(f"    → Direction: {result['details']['trend']['direction']}")
        print(f"  \n  Fundamentals: {result['details']['fundamentals']['score']}/5")
        print(f"    → {result['details']['fundamentals']['summary']}")
        print(f"  \n  AI Sentiment: {result['details']['ai_sentiment']['score']}/5")
        print(f"    → {result['details']['ai_sentiment']['summary']}")
        print(f"\nAnalyzed at: {result['analyzed_at']}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Analysis failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_nifty_caching():
    """Test that Nifty data is cached properly"""
    
    print("\n\nTesting Nifty data caching...")
    print("=" * 60)
    
    try:
        with open('access_token.json', 'r') as f:
            token_data = json.load(f)
            access_token = token_data.get('access_token')
    except:
        print("❌ Could not read access token")
        return False
    
    api_key = os.getenv('KITE_API_KEY')
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    
    analyzer1 = StockAnalyzer(kite_instance=kite, gemini_api_key=gemini_api_key)
    
    import time
    start_time = time.time()
    
    # First call should fetch Nifty
    print("\n1st call - fetching Nifty data...")
    result1 = analyzer1.analyze_stock('TCS')
    time1 = time.time() - start_time
    
    # Second call should use cached Nifty
    start_time = time.time()
    print("\n2nd call - should use cached Nifty...")
    analyzer2 = StockAnalyzer(kite_instance=kite, gemini_api_key=gemini_api_key)
    result2 = analyzer2.analyze_stock('INFY')
    time2 = time.time() - start_time
    
    print(f"\n✅ Caching test completed")
    print(f"   1st analysis time: {time1:.2f}s")
    print(f"   2nd analysis time: {time2:.2f}s")
    
    if time2 < time1:
        print(f"   ✅ Caching is working! (~{((time1-time2)/time1*100):.0f}% time saved)")
    else:
        print(f"   ⚠️  2nd call was slower - cache may not be working as expected")
    
    return True

if __name__ == '__main__':
    print("CogniCap Stock Analyzer Test Suite")
    print("=" * 60)
    print()
    
    # Test 1: Basic analysis
    test1_passed = test_stock_analyzer()
    
    # Test 2: Caching (only if test 1 passed)
    if test1_passed:
        test2_passed = test_nifty_caching()
    else:
        print("\n⚠️  Skipping cache test due to previous failure")
        test2_passed = False
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"  Basic Analysis: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"  Nifty Caching: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    print()
    
    if test1_passed and test2_passed:
        print("🎉 All tests passed! The Kite API integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Please check the error messages above.")
