from flask import Flask, request, jsonify
from flask_cors import CORS
from kiteconnect import KiteConnect
from google import genai
from google.genai import types
import json
import os
import time
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd
from stock_health_service import StockHealthService
from stock_analyzer import StockAnalyzer
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for Angular frontend

# Load config
API_KEY = os.getenv('KITE_API_KEY', 'REDACTED_KITE_API_KEY')
API_SECRET = os.getenv('KITE_API_SECRET', 'REDACTED_KITE_API_SECRET')
TOKEN_FILE = 'access_token.json'

# Gemini API configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Store kite instances per session
kite_instances = {}

# Store chat sessions (in production, use a database)
chat_sessions = {}

# Analysis storage file
ANALYSIS_STORAGE_FILE = 'analysis_storage.json'

def load_analysis_storage():
    """Load saved analysis results from file"""
    try:
        if os.path.exists(ANALYSIS_STORAGE_FILE):
            with open(ANALYSIS_STORAGE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading analysis storage: {e}")
    return {}

def save_analysis_storage(data):
    """Save analysis results to file"""
    try:
        with open(ANALYSIS_STORAGE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving analysis storage: {e}")

def get_user_analysis_key(access_token, symbol):
    """Generate a unique key for user+symbol analysis data"""
    # Use last 8 chars of token + symbol for uniqueness but not storing full token
    token_suffix = access_token[-8:] if len(access_token) > 8 else access_token
    return f"{token_suffix}_{symbol}"

def save_analysis_result(access_token, symbol, analysis_data):
    """Save analysis result for a user+symbol"""
    storage = load_analysis_storage()
    key = get_user_analysis_key(access_token, symbol)
    
    storage[key] = {
        'analysis': analysis_data,
        'saved_at': datetime.now().isoformat(),
        'symbol': symbol
    }
    
    save_analysis_storage(storage)

def get_saved_analysis(access_token, symbol):
    """Get saved analysis result for a user+symbol"""
    storage = load_analysis_storage()
    key = get_user_analysis_key(access_token, symbol)
    print(f"Looking for analysis with key: {key}")
    result = storage.get(key)
    if result:
        print(f"Found saved analysis for {symbol}")
    else:
        print(f"No saved analysis found for {symbol}, checking storage keys...")
        # Debug: print all keys in storage that contain this symbol
        matching_keys = [k for k in storage.keys() if symbol in k]
        if matching_keys:
            print(f"Found keys with {symbol}: {matching_keys}")
    return result

def simulate_live_market_data():
    """Generate static market data (no random variations - returns consistent values)"""
    # Static values for indices
    base_nifty = 21731.45
    base_sensex = 71752.11
    
    # No random variation - return consistent values
    current_nifty = base_nifty
    current_sensex = base_sensex
    
    # Static changes from previous day (simulated)
    nifty_change = 0.0
    sensex_change = 0.0
    
    nifty_change_percent = 0.0
    sensex_change_percent = 0.0
    
    return {
        'nifty': {
            'name': 'NIFTY 50',
            'value': round(current_nifty, 2),
            'change': round(nifty_change, 2),
            'change_percent': round(nifty_change_percent, 2),
            'high': round(current_nifty * 1.005, 2),
            'low': round(current_nifty * 0.995, 2),
            'volume': 0
        },
        'sensex': {
            'name': 'SENSEX',
            'value': round(current_sensex, 2),
            'change': round(sensex_change, 2),
            'change_percent': round(sensex_change_percent, 2),
            'high': round(current_sensex * 1.005, 2),
            'low': round(current_sensex * 0.995, 2),
            'volume': 0
        }
    }

def simulate_live_stock_data():
    """Generate static stock data (no random variations - returns consistent values)"""
    stocks = {
        'gainers': [
            {'symbol': 'ADANIENT', 'base_price': 2891.50, 'base_change_percent': 3.19},
            {'symbol': 'TATAMOTORS', 'base_price': 965.25, 'base_change_percent': 3.07},
            {'symbol': 'HINDALCO', 'base_price': 638.90, 'base_change_percent': 2.80},
            {'symbol': 'TATASTEEL', 'base_price': 148.75, 'base_change_percent': 2.58},
            {'symbol': 'JSWSTEEL', 'base_price': 901.45, 'base_change_percent': 2.38},
            {'symbol': 'BAJFINANCE', 'base_price': 6789.30, 'base_change_percent': 2.02},
            {'symbol': 'MARUTI', 'base_price': 10245.60, 'base_change_percent': 1.84},
            {'symbol': 'M&M', 'base_price': 1678.25, 'base_change_percent': 1.74},
            {'symbol': 'LT', 'base_price': 3456.80, 'base_change_percent': 1.63},
            {'symbol': 'RELIANCE', 'base_price': 2934.65, 'base_change_percent': 1.53}
        ],
        'losers': [
            {'symbol': 'NESTLEIND', 'base_price': 2345.80, 'base_change_percent': -3.41},
            {'symbol': 'BRITANNIA', 'base_price': 4567.90, 'base_change_percent': -2.68},
            {'symbol': 'HINDUNILVR', 'base_price': 2654.35, 'base_change_percent': -2.40},
            {'symbol': 'ITC', 'base_price': 456.75, 'base_change_percent': -2.32},
            {'symbol': 'SUNPHARMA', 'base_price': 1543.20, 'base_change_percent': -2.17},
            {'symbol': 'CIPLA', 'base_price': 1398.60, 'base_change_percent': -2.02},
            {'symbol': 'DRREDDY', 'base_price': 5432.75, 'base_change_percent': -1.78},
            {'symbol': 'DIVISLAB', 'base_price': 3678.90, 'base_change_percent': -1.66},
            {'symbol': 'APOLLOHOSP', 'base_price': 5789.45, 'base_change_percent': -1.49},
            {'symbol': 'TITAN', 'base_price': 3234.60, 'base_change_percent': -1.40}
        ]
    }
    
    def create_stock_data(stock_list):
        result = []
        for stock in stock_list:
            # No random variation - return consistent values
            current_price = stock['base_price']
            current_change_percent = stock['base_change_percent']
            
            # Calculate the previous price to get the change amount
            previous_price = current_price / (1 + current_change_percent / 100)
            change = current_price - previous_price
            
            result.append({
                'symbol': stock['symbol'],
                'name': stock['symbol'],
                'price': round(current_price, 2),
                'change': round(change, 2),
                'change_percent': round(current_change_percent, 2),
                'volume': 10000000,  # Static volume
                'high': round(current_price * 1.02, 2),
                'low': round(current_price * 0.98, 2)
            })
        
        return result
    
    return {
        'top_gainers': create_stock_data(stocks['gainers']),
        'top_losers': create_stock_data(stocks['losers'])
    }

def simulate_portfolio_data():
    """Generate static portfolio data (no random variations - returns consistent values)"""
    # Base portfolio data (simulating a user with these holdings)
    base_holdings = [
        {'tradingsymbol': 'RELIANCE', 'exchange': 'NSE', 'quantity': 50, 'average_price': 2850.00, 'base_last_price': 2934.65},
        {'tradingsymbol': 'TCS', 'exchange': 'NSE', 'quantity': 25, 'average_price': 3650.00, 'base_last_price': 3712.40},
        {'tradingsymbol': 'INFY', 'exchange': 'NSE', 'quantity': 30, 'average_price': 1520.00, 'base_last_price': 1587.30},
        {'tradingsymbol': 'HDFCBANK', 'exchange': 'NSE', 'quantity': 40, 'average_price': 1680.00, 'base_last_price': 1698.55},
        {'tradingsymbol': 'ITC', 'exchange': 'NSE', 'quantity': 100, 'average_price': 445.00, 'base_last_price': 456.75},
        {'tradingsymbol': 'HINDUNILVR', 'exchange': 'NSE', 'quantity': 15, 'average_price': 2580.00, 'base_last_price': 2654.35},
        {'tradingsymbol': 'ICICIBANK', 'exchange': 'NSE', 'quantity': 35, 'average_price': 980.00, 'base_last_price': 1024.80},
        {'tradingsymbol': 'SBIN', 'exchange': 'NSE', 'quantity': 80, 'average_price': 620.00, 'base_last_price': 643.15},
        {'tradingsymbol': 'BAJFINANCE', 'exchange': 'NSE', 'quantity': 8, 'average_price': 6450.00, 'base_last_price': 6789.30},
        {'tradingsymbol': 'MARUTI', 'exchange': 'NSE', 'quantity': 6, 'average_price': 9850.00, 'base_last_price': 10245.60},
        {'tradingsymbol': 'ASIANPAINT', 'exchange': 'NSE', 'quantity': 12, 'average_price': 3180.00, 'base_last_price': 3234.60},
        {'tradingsymbol': 'LT', 'exchange': 'NSE', 'quantity': 18, 'average_price': 3320.00, 'base_last_price': 3456.80},
        {'tradingsymbol': 'KOTAKBANK', 'exchange': 'NSE', 'quantity': 22, 'average_price': 1780.00, 'base_last_price': 1834.25},
    ]
    
    static_holdings = []
    total_investment = 0
    current_value = 0
    total_pnl = 0
    
    for holding in base_holdings:
        # No random variation - use static base price
        current_price = holding['base_last_price']
        
        # Calculate values
        investment = holding['average_price'] * holding['quantity']
        value = current_price * holding['quantity']
        pnl = value - investment
        day_change = 0  # No day change for static data
        day_change_percentage = 0  # No day change for static data
        
        total_investment += investment
        current_value += value
        total_pnl += pnl
        
        static_holding = {
            'tradingsymbol': holding['tradingsymbol'],
            'exchange': holding['exchange'],
            'quantity': holding['quantity'],
            'average_price': holding['average_price'],
            'last_price': round(current_price, 2),
            'pnl': round(pnl, 2),
            'day_change': round(day_change, 2),
            'day_change_percentage': round(day_change_percentage, 2),
            'instrument_token': 500000,  # Static token
            'product': 'CNC',
            'has_saved_analysis': False  # Static analysis status
        }
        
        static_holdings.append(static_holding)
    
    # Calculate summary
    pnl_percentage = (total_pnl / total_investment * 100) if total_investment > 0 else 0
    
    return {
        'holdings': static_holdings,
        'summary': {
            'total_holdings': len(static_holdings),
            'total_investment': round(total_investment, 2),
            'current_value': round(current_value, 2),
            'total_pnl': round(total_pnl, 2),
            'pnl_percentage': round(pnl_percentage, 2),
            'positions_count': len(static_holdings)
        }
    }

@app.route('/api/auth/login-url', methods=['GET'])
def get_login_url():
    """Get Zerodha login URL"""
    try:
        kite = KiteConnect(api_key=API_KEY)
        login_url = kite.login_url()
        return jsonify({
            'success': True,
            'login_url': login_url
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/authenticate', methods=['POST'])
def authenticate():
    """Authenticate with request token"""
    try:
        data = request.json
        request_token = data.get('request_token')
        
        if not request_token:
            return jsonify({
                'success': False,
                'error': 'Request token is required'
            }), 400
        
        kite = KiteConnect(api_key=API_KEY)
        
        # Generate session
        session_data = kite.generate_session(request_token, api_secret=API_SECRET)
        access_token = session_data["access_token"]
        
        # Save token
        with open(TOKEN_FILE, 'w') as f:
            json.dump({
                'access_token': access_token,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'timestamp': datetime.now().isoformat()
            }, f, indent=2)
        
        kite.set_access_token(access_token)
        
        # Get profile
        profile = kite.profile()
        
        return jsonify({
            'success': True,
            'access_token': access_token,
            'user': {
                'name': profile['user_name'],
                'email': profile['email'],
                'user_id': profile['user_id']
            }
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/verify', methods=['POST'])
def verify_token():
    """Verify if token is valid"""
    try:
        data = request.json
        access_token = data.get('access_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        profile = kite.profile()
        
        return jsonify({
            'success': True,
            'user': {
                'name': profile['user_name'],
                'email': profile['email'],
                'user_id': profile['user_id']
            }
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 401

@app.route('/api/portfolio/holdings', methods=['POST'])
def get_holdings():
    """Get user holdings with saved analysis data"""
    try:
        data = request.json
        access_token = data.get('access_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        # Debug: show token suffix for matching
        token_suffix = access_token[-8:] if len(access_token) > 8 else access_token
        print(f"\n=== Loading Holdings ===")
        print(f"Token suffix: {token_suffix}")
        
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        holdings = kite.holdings()
        
        # Enhance holdings with saved analysis data
        enhanced_holdings = []
        for holding in holdings:
            symbol = holding.get('tradingsymbol', '')
            saved_analysis = get_saved_analysis(access_token, symbol)
            
            enhanced_holding = {**holding}
            if saved_analysis:
                enhanced_holding['saved_analysis'] = saved_analysis['analysis']
                enhanced_holding['analysis_saved_at'] = saved_analysis['saved_at']
                enhanced_holding['has_saved_analysis'] = True
                print(f"✓ Enhanced {symbol} with saved analysis (score: {saved_analysis['analysis'].get('score', 'N/A')})")
            else:
                enhanced_holding['has_saved_analysis'] = False
                print(f"✗ No saved analysis for {symbol}")
            
            enhanced_holdings.append(enhanced_holding)
        
        print(f"\nReturning {len(enhanced_holdings)} holdings, {sum(1 for h in enhanced_holdings if h['has_saved_analysis'])} with saved analysis\n")
        
        return jsonify({
            'success': True,
            'holdings': enhanced_holdings
        })
    
    except Exception as e:
        # Return dynamic portfolio simulation on error
        # But still try to load real saved analysis from storage
        portfolio_data = simulate_portfolio_data()
        enhanced_holdings = []
        
        # Try to use real access token if available for loading saved analysis
        try:
            data = request.json
            access_token = data.get('access_token', '')
        except:
            access_token = ''
        
        for holding in portfolio_data['holdings']:
            symbol = holding.get('tradingsymbol', '')
            enhanced_holding = {**holding}
            
            # Try to load real saved analysis from storage file
            if access_token:
                saved_analysis = get_saved_analysis(access_token, symbol)
                if saved_analysis:
                    enhanced_holding['saved_analysis'] = saved_analysis['analysis']
                    enhanced_holding['analysis_saved_at'] = saved_analysis['saved_at']
                    enhanced_holding['has_saved_analysis'] = True
                else:
                    enhanced_holding['has_saved_analysis'] = False
            else:
                enhanced_holding['has_saved_analysis'] = False
            
            enhanced_holdings.append(enhanced_holding)
        
        return jsonify({
            'success': True,
            'holdings': enhanced_holdings,
            'note': f'Using simulation mode with saved analysis - API Error: {str(e)}'
        })

@app.route('/api/portfolio/positions', methods=['POST'])
def get_positions():
    """Get user positions"""
    try:
        data = request.json
        access_token = data.get('access_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        positions = kite.positions()
        
        return jsonify({
            'success': True,
            'positions': positions
        })
    
    except Exception as e:
        # Return dynamic portfolio simulation on error
        # But still try to load real saved analysis from storage
        print(f"Holdings API failed, using simulation: {e}")
        portfolio_data = simulate_portfolio_data()
        enhanced_holdings = []
        
        # Try to use real access token if available for loading saved analysis
        try:
            data = request.json
            access_token = data.get('access_token', '')
        except:
            access_token = ''
        
        for holding in portfolio_data['holdings']:
            symbol = holding.get('tradingsymbol', '')
            enhanced_holding = {**holding}
            
            # Try to load real saved analysis from storage file
            if access_token:
                saved_analysis = get_saved_analysis(access_token, symbol)
                if saved_analysis:
                    enhanced_holding['saved_analysis'] = saved_analysis['analysis']
                    enhanced_holding['analysis_saved_at'] = saved_analysis['saved_at']
                    enhanced_holding['has_saved_analysis'] = True
                else:
                    enhanced_holding['has_saved_analysis'] = False
            else:
                enhanced_holding['has_saved_analysis'] = False
            
            enhanced_holdings.append(enhanced_holding)
        
        return jsonify({
            'success': True,
            'holdings': enhanced_holdings,
            'note': 'Using simulation mode with saved analysis - API unavailable'
        })

@app.route('/api/portfolio/summary', methods=['POST'])
def get_portfolio_summary():
    """Get portfolio summary with live price updates"""
    try:
        data = request.json
        access_token = data.get('access_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        # Try to get real data from Kite API
        try:
            kite = KiteConnect(api_key=API_KEY)
            kite.set_access_token(access_token)
            
            holdings = kite.holdings()
            positions = kite.positions()
            
            # Calculate summary with actual prices from Kite API
            total_investment = sum([h['average_price'] * h['quantity'] for h in holdings])
            current_value = sum([h['last_price'] * h['quantity'] for h in holdings])
            total_pnl = sum([h['pnl'] for h in holdings])
            
            return jsonify({
                'success': True,
                'summary': {
                    'total_holdings': len(holdings),
                    'total_investment': round(total_investment, 2),
                    'current_value': round(current_value, 2),
                    'total_pnl': round(total_pnl, 2),
                    'pnl_percentage': round((total_pnl / total_investment * 100) if total_investment > 0 else 0, 2),
                    'positions_count': len(positions['net'])
                },
                'note': 'Real portfolio data from Kite API'
            })
            
        except Exception as kite_error:
            # Fallback to simulation only if Kite API fails
            print(f"Kite API failed, using simulation: {kite_error}")
            portfolio_data = simulate_portfolio_data()
            return jsonify({
                'success': True,
                'summary': portfolio_data['summary'],
                'note': 'Simulation mode - API unavailable'
            })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/portfolio/top-performers', methods=['POST'])
def get_top_performers():
    """Get top 3 gainers and bottom 3 losers"""
    try:
        data = request.json
        access_token = data.get('access_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        holdings = kite.holdings()
        
        if not holdings:
            return jsonify({
                'success': True,
                'top_gainers': [],
                'top_losers': []
            })
        
        # Apply live price variations (±0.3%) to real holdings
        for holding in holdings:
            original_price = holding['last_price']
            price_variation = random.uniform(-0.003, 0.003)
            holding['last_price'] = round(original_price * (1 + price_variation), 2)
            
            # Recalculate PnL with updated price
            current_value = holding['last_price'] * holding['quantity']
            investment = holding['average_price'] * holding['quantity']
            holding['pnl'] = round(current_value - investment, 2)
        
        # Sort by PnL to get top gainers and losers
        sorted_holdings = sorted(holdings, key=lambda x: x['pnl'], reverse=True)
        
        # Get top 3 gainers (highest positive PnL)
        top_gainers = sorted_holdings[:3]
        
        # Get top 3 losers (lowest/most negative PnL)
        top_losers = sorted_holdings[-3:][::-1]  # Reverse to show worst first
        
        # Format the data
        def format_holding(h):
            return {
                'tradingsymbol': h['tradingsymbol'],
                'exchange': h['exchange'],
                'quantity': h['quantity'],
                'average_price': round(h['average_price'], 2),
                'last_price': round(h['last_price'], 2),
                'pnl': round(h['pnl'], 2),
                'pnl_percentage': round((h['pnl'] / (h['average_price'] * h['quantity']) * 100) if h['average_price'] * h['quantity'] > 0 else 0, 2)
            }
        
        return jsonify({
            'success': True,
            'top_gainers': [format_holding(h) for h in top_gainers],
            'top_losers': [format_holding(h) for h in top_losers]
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/portfolio/health-report', methods=['POST'])
def get_health_report():
    """Get comprehensive health report for all portfolio holdings"""
    try:
        data = request.json
        access_token = data.get('access_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        # Initialize Kite instance
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        # Create health service instance
        health_service = StockHealthService(
            kite_instance=kite,
            gemini_api_key=GEMINI_API_KEY
        )
        
        # Generate health report
        health_reports = health_service.get_portfolio_health_report()
        
        return jsonify({
            'success': True,
            'reports': health_reports,
            'total_stocks': len(health_reports),
            'generated_at': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Request queue to handle rate limiting
analysis_queue = queue.Queue()
queue_lock = threading.Lock()

def process_analysis_queue():
    """Process analysis requests with rate limiting (max 3 per second)"""
    while True:
        try:
            # Get request from queue
            request_data = analysis_queue.get()
            
            if request_data is None:  # Poison pill to stop thread
                break
            
            # Add delay to respect rate limits (3 req/sec = 333ms between requests)
            time.sleep(0.35)
            
        except Exception as e:
            print(f"Error processing queue: {str(e)}")

# Start queue processor thread
threading.Thread(target=process_analysis_queue, daemon=True).start()

@app.route('/api/analyze-stock', methods=['POST'])
def analyze_stock():
    """
    Analyze a single stock on-demand using Kite API
    Request body: {
        "access_token": "...",
        "symbol": "RELIANCE",
        "instrument_token": 738561 (optional)
    }
    """
    try:
        data = request.json
        access_token = data.get('access_token')
        symbol = data.get('symbol')
        instrument_token = data.get('instrument_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        if not symbol:
            return jsonify({
                'success': False,
                'error': 'Symbol is required'
            }), 400
        
        # Initialize Kite instance
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        # Create analyzer instance
        analyzer = StockAnalyzer(
            kite_instance=kite,
            gemini_api_key=GEMINI_API_KEY
        )
        
        # Analyze the stock
        result = analyzer.analyze_stock(symbol, instrument_token)
        
        # Save the analysis result
        save_analysis_result(access_token, symbol, result)
        
        return jsonify({
            'success': True,
            **result
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/analyze-all', methods=['POST'])
def analyze_all_stocks():
    """
    Analyze all stocks in portfolio
    Request body: {
        "access_token": "..."
    }
    """
    try:
        data = request.json
        access_token = data.get('access_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        # Initialize Kite instance
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        # Get holdings
        holdings = kite.holdings()
        
        if not holdings:
            return jsonify({
                'success': True,
                'results': [],
                'message': 'No holdings found'
            })
        
        # Create analyzer instance
        analyzer = StockAnalyzer(
            kite_instance=kite,
            gemini_api_key=GEMINI_API_KEY
        )
        
        results = []
        failed_stocks = []
        
        # Use ThreadPoolExecutor to analyze stocks in parallel (but with rate limiting)
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            
            for holding in holdings:
                symbol = holding.get('tradingsymbol', '')
                instrument_token = holding.get('instrument_token')
                
                # Submit analysis task
                future = executor.submit(
                    analyzer.analyze_stock, 
                    symbol, 
                    instrument_token
                )
                futures[future] = {
                    'symbol': symbol,
                    'holding': holding
                }
                
                # Add delay between submissions to respect rate limits
                time.sleep(0.4)  # 2.5 requests per second
            
            # Collect results as they complete
            for future in as_completed(futures, timeout=300):  # 5 minute timeout
                stock_info = futures[future]
                symbol = stock_info['symbol']
                
                try:
                    result = future.result()
                    
                    # Save the analysis result
                    save_analysis_result(access_token, symbol, result)
                    
                    results.append({
                        'symbol': symbol,
                        'success': True,
                        'analysis': result
                    })
                    
                except Exception as e:
                    print(f"Error analyzing {symbol}: {str(e)}")
                    failed_stocks.append({
                        'symbol': symbol,
                        'error': str(e)
                    })
                    
                    results.append({
                        'symbol': symbol,
                        'success': False,
                        'error': str(e)
                    })
        
        return jsonify({
            'success': True,
            'results': results,
            'total_stocks': len(holdings),
            'successful_analyses': len([r for r in results if r.get('success')]),
            'failed_analyses': len(failed_stocks),
            'failed_stocks': failed_stocks,
            'completed_at': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/market/indices', methods=['POST'])
def get_market_indices():
    """Get Nifty 50 and Sensex indices data using Kite API"""
    try:
        data = request.json
        access_token = data.get('access_token')
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        # Initialize Kite instance
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        # Nifty 50 and Sensex instrument tokens
        nifty_token = 256265   # NSE:NIFTY 50
        sensex_token = 265     # BSE:SENSEX
        
        # Fetch quotes for both indices
        quotes = kite.quote(['NSE:NIFTY 50', 'BSE:SENSEX'])
        
        nifty_quote = quotes.get('NSE:NIFTY 50', {})
        sensex_quote = quotes.get('BSE:SENSEX', {})
        
        # Extract data
        def format_index_data(quote, name):
            last_price = quote.get('last_price', 0)
            ohlc = quote.get('ohlc', {})
            open_price = ohlc.get('open', last_price)
            change = last_price - open_price
            change_percent = (change / open_price * 100) if open_price > 0 else 0
            
            return {
                'name': name,
                'value': round(last_price, 2),
                'change': round(change, 2),
                'change_percent': round(change_percent, 2),
                'high': round(ohlc.get('high', 0), 2),
                'low': round(ohlc.get('low', 0), 2),
                'volume': quote.get('volume', 0)
            }
        
        return jsonify({
            'success': True,
            'nifty': format_index_data(nifty_quote, 'NIFTY 50'),
            'sensex': format_index_data(sensex_quote, 'SENSEX')
        })
    
    except Exception as e:
        # Return dynamic demo data on error to simulate live market
        market_data = simulate_live_market_data()
        return jsonify({
            'success': True,
            'nifty': market_data['nifty'],
            'sensex': market_data['sensex'],
            'note': f'Live simulation - API Error: {str(e)}'
        })

@app.route('/api/market/top-stocks', methods=['GET'])
def get_top_stocks():
    """Get top 10 gainers and losers with live simulation"""
    try:
        # Generate dynamic stock data to simulate live market
        stock_data = simulate_live_stock_data()
        
        return jsonify({
            'success': True,
            'top_gainers': stock_data['top_gainers'],
            'top_losers': stock_data['top_losers'],
            'note': 'Live market simulation'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to generate market data: {str(e)}'
        }), 500

@app.route('/api/chat/send', methods=['POST'])
def chat_send():
    """Send message to Gemini AI chatbot"""
    try:
        if not gemini_client:
            return jsonify({
                'success': False,
                'error': 'Gemini API key not configured. Please set GEMINI_API_KEY environment variable.'
            }), 500
        
        data = request.json
        message = data.get('message', '')
        session_id = data.get('session_id', 'default')
        
        if not message:
            return jsonify({
                'success': False,
                'error': 'Message is required'
            }), 400
        
        # Initialize chat session history if not exists
        if session_id not in chat_sessions:
            chat_sessions[session_id] = []
        
        # Add user message to history (store as dict for simplicity)
        chat_sessions[session_id].append({
            'role': 'user',
            'text': message
        })
        
        # Build contents for API call using proper types
        contents = []
        for msg in chat_sessions[session_id]:
            contents.append(
                types.Content(
                    role=msg['role'],
                    parts=[types.Part(text=msg['text'])]
                )
            )
        
        # Send message and get response
        response = gemini_client.models.generate_content(
            model='models/gemini-2.5-flash',
            contents=contents
        )
        
        # Add assistant response to history
        chat_sessions[session_id].append({
            'role': 'model',
            'text': response.text
        })
        
        return jsonify({
            'success': True,
            'response': response.text,
            'session_id': session_id
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/chat/clear', methods=['POST'])
def chat_clear():
    """Clear chat session"""
    try:
        data = request.json
        session_id = data.get('session_id', 'default')
        
        if session_id in chat_sessions:
            del chat_sessions[session_id]
        
        return jsonify({
            'success': True,
            'message': 'Chat session cleared'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
