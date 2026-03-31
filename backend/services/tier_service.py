"""User tier derivation + plan management service.

Tiers are computed at runtime from the user's API configurations — never stored.
Plans are explicitly selected by the user and stored in the users table.

Plan              Tier  LLM source        Kite required
---------------------------------------------------------
general (Stock Explorer)  1  platform (shared) no
ideal   (The Executer)    2  platform (shared) yes
rockstar (Lone Wolf)      3  user's own keys   yes

Enforcement:
  - Lone Wolf plan users must supply their own LLM keys.
    The platform LLM fallback is disabled for them.
  - The Executer/Lone Wolf plan users must have Kite linked for portfolio features.
"""

from typing import Optional

TIER_GENERAL = 1
TIER_IDEAL = 2
TIER_ROCKSTAR = 3

TIER_NAMES = {
    TIER_GENERAL: "Stock Explorer",
    TIER_IDEAL: "The Executer",
    TIER_ROCKSTAR: "Lone Wolf",
}

VALID_PLANS = {"general", "ideal", "rockstar"}


# ── Plan CRUD ──────────────────────────────────────────────────────────────────

def get_user_plan(user_id: int) -> str:
    """Return the user's explicitly selected plan ('general'/'ideal'/'rockstar')."""
    from services.db import get_conn
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT plan FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row["plan"] if row else "general"
    finally:
        conn.close()


def set_user_plan(user_id: int, plan: str) -> None:
    """Persist the user's selected plan."""
    if plan not in VALID_PLANS:
        raise ValueError(f"Invalid plan '{plan}'. Must be one of: {VALID_PLANS}")
    from services.db import get_conn
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET plan = ?, updated_at = datetime('now') WHERE id = ?",
            (plan, user_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── Tier derivation ────────────────────────────────────────────────────────────

def get_user_tier(user_id: int) -> int:
    """Derive the user's tier from their API configurations."""
    from services.auth_service import get_broker_token
    from services.llm_key_service import get_user_llm_providers

    has_broker = get_broker_token(user_id) is not None
    has_llm = len(get_user_llm_providers(user_id)) > 0

    if has_broker and has_llm:
        return TIER_ROCKSTAR
    elif has_broker:
        return TIER_IDEAL
    else:
        return TIER_GENERAL


def get_user_tier_info(user_id: int) -> dict:
    """Return tier + plan + full breakdown of what's configured."""
    from services.auth_service import get_broker_token
    from services.llm_key_service import get_user_llm_providers

    has_broker = get_broker_token(user_id) is not None
    llm_providers = get_user_llm_providers(user_id)
    has_llm = len(llm_providers) > 0
    plan = get_user_plan(user_id)

    if has_broker and has_llm:
        tier = TIER_ROCKSTAR
    elif has_broker:
        tier = TIER_IDEAL
    else:
        tier = TIER_GENERAL

    return {
        "tier": tier,
        "tier_name": TIER_NAMES[tier],
        "plan": plan,
        "has_broker": has_broker,
        "has_llm_keys": has_llm,
        "llm_providers": llm_providers,
        "needs_payment": plan in ("general", "ideal"),
    }
