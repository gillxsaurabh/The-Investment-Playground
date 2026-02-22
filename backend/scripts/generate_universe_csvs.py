#!/usr/bin/env python3
"""One-time script to generate universe CSV files (nifty100, midcap150, smallcap250).

Uses Kite Connect instruments API to get real instrument tokens and NSE index
constituent lists. Requires an active access_token.

Usage:
    cd backend
    ./venv/bin/python3 scripts/generate_universe_csvs.py

The script will read the access token from data/state/access_token.json.
"""

import csv
import json
import sys
from pathlib import Path

import requests
from kiteconnect import KiteConnect

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from config import KITE_API_KEY, TOKEN_FILE, DATA_DIR

# NSE index constituent URLs (public JSON endpoints)
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# Sector mapping based on existing nifty500.csv patterns
def _load_existing_sector_map() -> dict[str, dict]:
    """Load sector info from existing nifty500.csv."""
    csv_path = DATA_DIR / "nifty500.csv"
    sector_map = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            sector_map[row["symbol"]] = {
                "sector": row["sector"],
                "sector_index": row["sector_index"],
            }
    return sector_map


def _fetch_nse_index_constituents(index_name: str) -> list[str]:
    """Fetch constituent symbols from NSE India API."""
    url = f"https://www.nseindia.com/api/equity-stockIndices?index={index_name}"

    # NSE requires a session with cookies
    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    # First hit the main page to get cookies
    try:
        session.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass

    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        symbols = []
        for item in data.get("data", []):
            sym = item.get("symbol")
            if sym and sym != index_name:
                symbols.append(sym)
        return symbols
    except Exception as e:
        print(f"Failed to fetch {index_name} from NSE: {e}")
        return []


def _get_kite_instruments(access_token: str) -> dict[str, int]:
    """Get symbol → instrument_token map from Kite API."""
    kite = KiteConnect(api_key=KITE_API_KEY)
    kite.set_access_token(access_token)
    instruments = kite.instruments("NSE")
    token_map = {}
    for inst in instruments:
        sym = inst.get("tradingsymbol")
        token = inst.get("instrument_token")
        if sym and token:
            token_map[sym] = token
    return token_map


def _write_universe_csv(filename: str, symbols: list[str], token_map: dict[str, int], sector_map: dict):
    """Write a universe CSV file."""
    output_path = DATA_DIR / filename
    written = 0
    missing_tokens = []
    missing_sectors = []

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "instrument_token", "sector", "sector_index"])

        for symbol in sorted(symbols):
            token = token_map.get(symbol)
            if token is None:
                missing_tokens.append(symbol)
                continue

            sector_info = sector_map.get(symbol, {"sector": "Other", "sector_index": "NSE:NIFTY 50"})
            writer.writerow([
                symbol,
                token,
                sector_info["sector"],
                sector_info["sector_index"],
            ])
            written += 1

    print(f"  Wrote {written} stocks to {output_path}")
    if missing_tokens:
        print(f"  Skipped {len(missing_tokens)} (no instrument token): {missing_tokens[:5]}...")
    if missing_sectors:
        print(f"  {len(missing_sectors)} stocks defaulted to 'Other' sector")


def main():
    # Load access token
    try:
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)
        access_token = token_data.get("access_token")
        if not access_token:
            print("No access_token found in", TOKEN_FILE)
            sys.exit(1)
    except FileNotFoundError:
        print(f"Token file not found: {TOKEN_FILE}")
        print("Please authenticate with Kite first.")
        sys.exit(1)

    print("Fetching Kite instrument tokens...")
    token_map = _get_kite_instruments(access_token)
    print(f"  Loaded {len(token_map)} NSE instrument tokens")

    print("Loading sector mapping from nifty500.csv...")
    sector_map = _load_existing_sector_map()
    print(f"  Loaded sectors for {len(sector_map)} stocks")

    # Fetch index constituents from NSE
    indices = {
        "nifty100.csv": "NIFTY 100",
        "nifty_midcap150.csv": "NIFTY MIDCAP 150",
        "nifty_smallcap250.csv": "NIFTY SMALLCAP 250",
    }

    for filename, index_name in indices.items():
        print(f"\nFetching {index_name} constituents...")
        symbols = _fetch_nse_index_constituents(index_name)
        if not symbols:
            print(f"  WARNING: Could not fetch {index_name}. Try running during market hours.")
            print(f"  You can manually create {DATA_DIR / filename}")
            continue
        print(f"  Found {len(symbols)} constituents")
        _write_universe_csv(filename, symbols, token_map, sector_map)

    print("\nDone! Universe CSV files are in:", DATA_DIR)


if __name__ == "__main__":
    main()
