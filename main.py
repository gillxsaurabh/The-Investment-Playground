from kite_auth import get_kite_instance

def main():
    # Authenticate and get Kite instance
    kite = get_kite_instance()
    
    if not kite:
        print("Failed to authenticate. Exiting...")
        return
    
    print("\n" + "="*60)
    print("COGNICAP - READY")
    print("="*60)
    
    # Your trading logic here
    # Example: Get holdings
    try:
        holdings = kite.holdings()
        print(f"\nYou have {len(holdings)} holdings")
        
        # Get positions
        positions = kite.positions()
        print(f"Net positions: {len(positions['net'])}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()