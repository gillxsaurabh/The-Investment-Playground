"""Centralized configuration for the CogniCap backend.

All environment variables, file paths, and Flask settings are managed here.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env files: backend/.env first (has Kite credentials with correct API
# subscription), then project root .env for any additional keys (e.g. OPENAI_API_KEY).
# First file loaded with override=True wins for shared keys.
_BACKEND_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_ROOT.parent

# Load root .env first (no override) — sets any keys not yet in env
_root_env = _PROJECT_ROOT / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)

# Load backend/.env second with override — its Kite keys take priority
_backend_env = _BACKEND_ROOT / ".env"
if _backend_env.exists():
    load_dotenv(_backend_env, override=True)

# --- Broker credentials ---
KITE_API_KEY = os.getenv("KITE_API_KEY", "")
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "")

# --- AI API keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# --- File paths ---
_BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = _BACKEND_DIR / "data"
STATE_DIR = DATA_DIR / "state"

TOKEN_FILE = STATE_DIR / "access_token.json"
ANALYSIS_STORAGE_FILE = STATE_DIR / "analysis_storage.json"
SIMULATOR_DATA_FILE = STATE_DIR / "simulator_data.json"
SIMULATOR_PRICE_HISTORY_FILE = STATE_DIR / "simulator_price_history.json"
AUTOMATION_STATE_FILE = STATE_DIR / "automation_state.json"
DB_PATH = STATE_DIR / "cognicap.db"

# --- Well-known instrument tokens ---
NIFTY_50_TOKEN = 256265
SENSEX_TOKEN = 265

# --- Flask ---
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"


def validate_config():
    """Validate that required environment variables are set. Call at startup."""
    missing = []
    if not KITE_API_KEY:
        missing.append("KITE_API_KEY")
    if not KITE_API_SECRET:
        missing.append("KITE_API_SECRET")
    if missing:
        print(f"[Config] WARNING: Missing environment variables: {', '.join(missing)}")
        print("[Config] Some features will be unavailable. Set them in .env at project root.")
