from kiteconnect import KiteConnect
import json
import os
from datetime import datetime
from config import API_KEY, API_SECRET, TOKEN_FILE

class KiteAuth:
    def __init__(self):
        self.kite = KiteConnect(api_key=API_KEY)
        self.access_token = None
    
    def load_access_token(self):
        """Load saved access token if exists and valid for today"""
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                    if data.get('date') == datetime.now().strftime('%Y-%m-%d'):
                        return data.get('access_token')
            except Exception as e:
                print(f"Error loading token: {e}")
        return None
    
    def save_access_token(self, token):
        """Save access token with current date"""
        try:
            with open(TOKEN_FILE, 'w') as f:
                json.dump({
                    'access_token': token,
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'timestamp': datetime.now().isoformat()
                }, f, indent=2)
            print("✓ Access token saved successfully!")
        except Exception as e:
            print(f"Error saving token: {e}")
    
    def generate_session(self, request_token):
        """Generate session with request token"""
        try:
            data = self.kite.generate_session(request_token, api_secret=API_SECRET)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            self.save_access_token(self.access_token)
            return True
        except Exception as e:
            print(f"Error generating session: {e}")
            return False
    
    def authenticate(self):
        """Main authentication flow"""
        # Try loading existing token
        self.access_token = self.load_access_token()
        
        if self.access_token:
            print("✓ Using saved access token for today")
            self.kite.set_access_token(self.access_token)
            
            # Verify token is valid
            try:
                profile = self.kite.profile()
                print(f"✓ Logged in as: {profile['user_name']} ({profile['email']})")
                return self.kite
            except Exception as e:
                print(f"✗ Saved token is invalid: {e}")
                self.access_token = None
        
        # Need new token
        print("\n" + "="*60)
        print("ZERODHA KITE LOGIN REQUIRED")
        print("="*60)
        login_url = self.kite.login_url()
        print(f"\n1. Visit this URL:\n   {login_url}")
        print("\n2. Login with your Zerodha credentials")
        print("\n3. After redirect, copy the 'request_token' from URL")
        print("="*60 + "\n")
        
        request_token = input("Enter request token: ").strip()
        
        if self.generate_session(request_token):
            profile = self.kite.profile()
            print(f"\n✓ Successfully logged in as: {profile['user_name']}")
            return self.kite
        else:
            print("\n✗ Authentication failed!")
            return None

def get_kite_instance():
    """Helper function to get authenticated Kite instance"""
    auth = KiteAuth()
    return auth.authenticate()