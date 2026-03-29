"""TradingEngine factory — returns the correct engine based on trading mode.

Maintains singletons so the same engine instance is shared across routes,
automation, and the position monitor.
"""

import logging
import threading
from typing import Optional

from services.file_lock import locked_json_read, atomic_json_write
from services.trading_engine import TradingEngine

logger = logging.getLogger(__name__)

_engines: dict = {}
_engines_lock = threading.Lock()


def get_trading_engine(access_token: str, mode: Optional[str] = None) -> TradingEngine:
    """Return the appropriate TradingEngine for the given mode.

    Args:
        access_token: Kite access token for the current session.
        mode: 'simulator' or 'live'. If None, reads from automation_state.json.

    Returns:
        Singleton TradingEngine (PaperTradingSimulator or LiveTradingEngine).
    """
    if mode is None:
        mode = _read_mode_from_state()

    key = mode  # one singleton per mode (not per token)

    with _engines_lock:
        if key == "live":
            engine = _engines.get("live")
            if engine is None:
                from broker import get_broker
                from services.live_engine import LiveTradingEngine
                broker = get_broker(access_token)
                engine = LiveTradingEngine(broker)
                _engines["live"] = engine
                logger.info("[EngineFactory] Created LiveTradingEngine singleton")
            else:
                # Update broker token if it changed (new login)
                try:
                    engine.broker.set_access_token(access_token)
                except Exception:
                    pass
            return engine

        else:  # simulator (default)
            engine = _engines.get("simulator")
            if engine is None:
                from broker import get_broker
                from services.simulator_engine import PaperTradingSimulator, start_position_monitor
                broker = get_broker(access_token)
                engine = PaperTradingSimulator(broker.raw_kite)
                _engines["simulator"] = engine
                start_position_monitor(engine)
                logger.info("[EngineFactory] Created PaperTradingSimulator singleton")
            else:
                # Update token if needed
                try:
                    engine.kite.set_access_token(access_token)
                except Exception:
                    pass
            return engine


def get_current_mode() -> str:
    """Return the current trading mode from automation state."""
    return _read_mode_from_state()


def set_trading_mode(mode: str) -> None:
    """Persist the trading mode to automation_state.json."""
    if mode not in ("simulator", "live"):
        raise ValueError(f"Invalid mode: {mode}")
    from config import AUTOMATION_STATE_FILE
    state = locked_json_read(AUTOMATION_STATE_FILE, default={})
    state["mode"] = mode
    atomic_json_write(AUTOMATION_STATE_FILE, state, indent=2)
    logger.info("[EngineFactory] Trading mode set to '%s'", mode)


def _read_mode_from_state() -> str:
    """Read mode from automation_state.json. Defaults to 'simulator'."""
    from config import AUTOMATION_STATE_FILE
    data = locked_json_read(AUTOMATION_STATE_FILE, default={})
    return data.get("mode", "simulator")
