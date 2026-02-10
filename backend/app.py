from flask import Flask, request, jsonify
from flask_cors import CORS
from kiteconnect import KiteConnect
from google import genai
from google.genai import types
import json
import os
from datetime import datetime
from dotenv import load_dotenv

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
    """Get user holdings"""
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
        
        return jsonify({
            'success': True,
            'holdings': holdings
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
