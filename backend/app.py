from flask import Flask, request, jsonify
from flask_cors import CORS
from kiteconnect import KiteConnect
from google import genai
from google.genai import types
import json
import os
import time
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
    return storage.get(key)

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
            else:
                enhanced_holding['has_saved_analysis'] = False
            
            enhanced_holdings.append(enhanced_holding)
        
        return jsonify({
            'success': True,
            'holdings': enhanced_holdings
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/portfolio/summary', methods=['POST'])
def get_portfolio_summary():
    """Get portfolio summary"""
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
        positions = kite.positions()
        
        # Calculate summary
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
            }
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
        # Return demo data on error
        return jsonify({
            'success': True,
            'nifty': {
                'name': 'NIFTY 50',
                'value': 21731.45,
                'change': 125.30,
                'change_percent': 0.58,
                'high': 21755.20,
                'low': 21650.10,
                'volume': 0
            },
            'sensex': {
                'name': 'SENSEX',
                'value': 71752.11,
                'change': 234.12,
                'change_percent': 0.33,
                'high': 71850.45,
                'low': 71600.30,
                'volume': 0
            },
            'note': f'Demo data - Error: {str(e)}'
        })

@app.route('/api/market/top-stocks', methods=['GET'])
def get_top_stocks():
    """Get top 10 gainers and losers from Nifty 50"""
    # Return demo data immediately since Yahoo Finance is unavailable
    return jsonify({
        'success': True,
        'top_gainers': [
            {'symbol': 'ADANIENT', 'name': 'ADANIENT', 'price': 2891.50, 'change': 89.50, 'change_percent': 3.19, 'volume': 5234567, 'high': 2910.00, 'low': 2850.00},
            {'symbol': 'TATAMOTORS', 'name': 'TATAMOTORS', 'price': 965.25, 'change': 28.75, 'change_percent': 3.07, 'volume': 8976543, 'high': 972.00, 'low': 945.00},
            {'symbol': 'HINDALCO', 'name': 'HINDALCO', 'price': 638.90, 'change': 17.40, 'change_percent': 2.80, 'volume': 6543210, 'high': 642.50, 'low': 625.00},
            {'symbol': 'TATASTEEL', 'name': 'TATASTEEL', 'price': 148.75, 'change': 3.75, 'change_percent': 2.58, 'volume': 12345678, 'high': 150.00, 'low': 146.00},
            {'symbol': 'JSWSTEEL', 'name': 'JSWSTEEL', 'price': 901.45, 'change': 20.95, 'change_percent': 2.38, 'volume': 7654321, 'high': 905.00, 'low': 885.00},
            {'symbol': 'BAJFINANCE', 'name': 'BAJFINANCE', 'price': 6789.30, 'change': 134.20, 'change_percent': 2.02, 'volume': 3456789, 'high': 6820.00, 'low': 6700.00},
            {'symbol': 'MARUTI', 'name': 'MARUTI', 'price': 10245.60, 'change': 185.40, 'change_percent': 1.84, 'volume': 2345678, 'high': 10280.00, 'low': 10150.00},
            {'symbol': 'M&M', 'name': 'M&M', 'price': 1678.25, 'change': 28.75, 'change_percent': 1.74, 'volume': 4567890, 'high': 1690.00, 'low': 1660.00},
            {'symbol': 'LT', 'name': 'LT', 'price': 3456.80, 'change': 55.30, 'change_percent': 1.63, 'volume': 3210987, 'high': 3470.00, 'low': 3420.00},
            {'symbol': 'RELIANCE', 'name': 'RELIANCE', 'price': 2934.65, 'change': 44.15, 'change_percent': 1.53, 'volume': 9876543, 'high': 2945.00, 'low': 2910.00}
        ],
        'top_losers': [
            {'symbol': 'NESTLEIND', 'name': 'NESTLEIND', 'price': 2345.80, 'change': -82.70, 'change_percent': -3.41, 'volume': 1234567, 'high': 2410.00, 'low': 2330.00},
            {'symbol': 'BRITANNIA', 'name': 'BRITANNIA', 'price': 4567.90, 'change': -125.60, 'change_percent': -2.68, 'volume': 987654, 'high': 4680.00, 'low': 4550.00},
            {'symbol': 'HINDUNILVR', 'name': 'HINDUNILVR', 'price': 2654.35, 'change': -65.40, 'change_percent': -2.40, 'volume': 5432109, 'high': 2705.00, 'low': 2640.00},
            {'symbol': 'ITC', 'name': 'ITC', 'price': 456.75, 'change': -10.85, 'change_percent': -2.32, 'volume': 15678901, 'high': 465.00, 'low': 454.00},
            {'symbol': 'SUNPHARMA', 'name': 'SUNPHARMA', 'price': 1543.20, 'change': -34.30, 'change_percent': -2.17, 'volume': 6789012, 'high': 1572.00, 'low': 1535.00},
            {'symbol': 'CIPLA', 'name': 'CIPLA', 'price': 1398.60, 'change': -28.90, 'change_percent': -2.02, 'volume': 4321098, 'high': 1422.00, 'low': 1390.00},
            {'symbol': 'DRREDDY', 'name': 'DRREDDY', 'price': 5432.75, 'change': -98.25, 'change_percent': -1.78, 'volume': 2109876, 'high': 5520.00, 'low': 5410.00},
            {'symbol': 'DIVISLAB', 'name': 'DIVISLAB', 'price': 3678.90, 'change': -62.10, 'change_percent': -1.66, 'volume': 1876543, 'high': 3730.00, 'low': 3665.00},
            {'symbol': 'APOLLOHOSP', 'name': 'APOLLOHOSP', 'price': 5789.45, 'change': -87.55, 'change_percent': -1.49, 'volume': 987654, 'high': 5865.00, 'low': 5760.00},
            {'symbol': 'TITAN', 'name': 'TITAN', 'price': 3234.60, 'change': -45.90, 'change_percent': -1.40, 'volume': 3456789, 'high': 3270.00, 'low': 3220.00}
        ],
        'note': 'Demo data - Market closed or Yahoo Finance API unavailable'
    })

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
