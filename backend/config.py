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

# In production (Railway/Docker), env vars are injected by the platform.
# Only load .env files in development (when they exist outside Docker).
_root_env = _PROJECT_ROOT / ".env"
_backend_env = _BACKEND_ROOT / ".env"

if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
    # Running on Railway — trust platform-injected env vars, skip .env files
    print("[Config] Railway detected — using platform environment variables")
else:
    # Local development — load .env files
    if _root_env.exists():
        load_dotenv(_root_env, override=False)
    if _backend_env.exists():
        load_dotenv(_backend_env, override=True)

# --- Environment ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development | staging | production

# --- App Security ---
JWT_SECRET = os.getenv("JWT_SECRET", "").strip().strip('"\'')  # strip Railway-added quotes
JWT_ACCESS_EXPIRY_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRY_MINUTES", "15"))
JWT_REFRESH_EXPIRY_DAYS = int(os.getenv("JWT_REFRESH_EXPIRY_DAYS", "7"))

# --- Encryption secrets (separate from JWT_SECRET) ---
# In production these MUST be set independently.
# In development they fall back to JWT_SECRET with a warning.
LLM_KEY_ENCRYPTION_SECRET = os.getenv("LLM_KEY_ENCRYPTION_SECRET", "").strip().strip('"\'')
BROKER_TOKEN_ENCRYPTION_SECRET = os.getenv("BROKER_TOKEN_ENCRYPTION_SECRET", "").strip().strip('"\'')

# --- CORS ---
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:4200").split(",")
    if o.strip()
]

# --- Broker credentials ---
# Strip surrounding quotes — Railway sometimes stores values with quotes if entered in .env format
KITE_API_KEY = os.getenv("KITE_API_KEY", "").strip().strip('"\'')
KITE_API_SECRET = os.getenv("KITE_API_SECRET", "").strip().strip('"\'')

# --- AI API keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# --- Observability ---
SENTRY_DSN = os.getenv("SENTRY_DSN", "")

# --- Redis ---
REDIS_URL = os.getenv("REDIS_URL", "").strip()

# --- File paths ---
_BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = _BACKEND_DIR / "data"

# DATA_MOUNT_PATH overrides the state directory — set to the Railway volume mount
# (e.g. DATA_MOUNT_PATH=/data) so DB and JSON state survive container restarts.
_DATA_MOUNT = os.getenv("DATA_MOUNT_PATH", "").strip()
STATE_DIR = Path(_DATA_MOUNT) if _DATA_MOUNT else DATA_DIR / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)  # ensure dir exists on fresh deploys

TOKEN_FILE = STATE_DIR / "access_token.json"
# analysis_storage.json is deprecated — analysis cache lives in user_analysis_cache table
SIMULATOR_DATA_FILE = STATE_DIR / "simulator_data.json"
SIMULATOR_PRICE_HISTORY_FILE = STATE_DIR / "simulator_price_history.json"
AUTOMATION_STATE_FILE = STATE_DIR / "automation_state.json"
DB_PATH = STATE_DIR / "cognicap.db"
BACKUP_DIR = STATE_DIR / "backups"

# --- S3 off-site backups (optional) ---
S3_BACKUP_BUCKET = os.getenv("S3_BACKUP_BUCKET", "").strip()
S3_BACKUP_PREFIX = os.getenv("S3_BACKUP_PREFIX", "cognicap/backups").strip()
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1").strip()

# --- Well-known instrument tokens ---
NIFTY_50_TOKEN = 256265
SENSEX_TOKEN = 265

# --- Flask ---
FLASK_PORT = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5000")))  # PORT is injected by Railway/Render
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"


def validate_config():
    """Validate that required environment variables are set. Call at startup."""
    # --- Debug: check env var presence (temporary) ---
    _jwt_raw = os.getenv("JWT_SECRET")
    print(f"[Config] DEBUG: JWT_SECRET from os.getenv = {'<set, len=' + str(len(_jwt_raw)) + '>' if _jwt_raw else '<NOT SET>'}")
    print(f"[Config] DEBUG: JWT_SECRET module var = {'<set, len=' + str(len(JWT_SECRET)) + '>' if JWT_SECRET else '<EMPTY>'}")
    _env_keys = sorted([k for k in os.environ if 'JWT' in k or 'SECRET' in k or 'RAILWAY' in k])
    print(f"[Config] DEBUG: Related env keys: {_env_keys}")

    # --- JWT_SECRET is mandatory — refuse to start without it ---
    if not JWT_SECRET:
        print("[Config] FATAL: JWT_SECRET is not set. The application cannot start.")
        print("[Config] Generate one: python -c \"import secrets; print(secrets.token_hex(32))\"")
        sys.exit(1)
    if len(JWT_SECRET) < 32:
        print("[Config] FATAL: JWT_SECRET must be at least 32 characters for security.")
        print(f"[Config] Current length: {len(JWT_SECRET)}. Generate a longer one.")
        sys.exit(1)

    # --- Production-specific checks ---
    if ENVIRONMENT == "production":
        if FLASK_DEBUG:
            print("[Config] WARNING: FLASK_DEBUG is enabled in production. This is not recommended.")
        if not SENTRY_DSN:
            print("[Config] WARNING: SENTRY_DSN is not set in production. Error monitoring is disabled.")
        if not LLM_KEY_ENCRYPTION_SECRET:
            print("[Config] FATAL: LLM_KEY_ENCRYPTION_SECRET must be set in production (cannot fall back to JWT_SECRET).")
            sys.exit(1)
        if not BROKER_TOKEN_ENCRYPTION_SECRET:
            print("[Config] FATAL: BROKER_TOKEN_ENCRYPTION_SECRET must be set in production.")
            sys.exit(1)
    else:
        # Development warnings
        if not LLM_KEY_ENCRYPTION_SECRET:
            print("[Config] WARNING: LLM_KEY_ENCRYPTION_SECRET not set — falling back to JWT_SECRET for LLM key encryption (not safe for production).")
        if not BROKER_TOKEN_ENCRYPTION_SECRET:
            print("[Config] WARNING: BROKER_TOKEN_ENCRYPTION_SECRET not set — broker token encryption disabled until set.")

    # --- Optional broker credentials (only needed for Kite features) ---
    optional_missing = []
    if not KITE_API_KEY:
        optional_missing.append("KITE_API_KEY")
    if not KITE_API_SECRET:
        optional_missing.append("KITE_API_SECRET")
    if optional_missing:
        print(f"[Config] WARNING: Missing optional variables: {', '.join(optional_missing)}")
        print("[Config] Broker features will be unavailable. Set them in .env at project root.")

    print(f"[Config] Environment: {ENVIRONMENT}")
