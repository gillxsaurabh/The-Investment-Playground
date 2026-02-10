from kiteconnect import KiteConnect

# Initialize KiteConnect
api_key = "bi56trp8ev6rdy9d"
api_secret = "zxulw382p4qm0k3yzcmwkec1su5fprrs"

kite = KiteConnect(api_key=api_key)

# Step 1: Generate login URL
login_url = kite.login_url()
print("Please visit this URL to login:")
print(login_url)

# Step 2: After login, enter the request token from redirect URL
request_token = input("\nEnter request token: ")

# Step 3: Generate session
try:
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]
    kite.set_access_token(access_token)
    
    # Test connection
    profile = kite.profile()
    print("\nConnection successful!")
    print(f"User: {profile['user_name']}")
    print(f"Email: {profile['email']}")
except Exception as e:
    print(f"Error: {e}")