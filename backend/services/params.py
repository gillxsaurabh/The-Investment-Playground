"""YAML-backed configuration loader for analysis parameters and LLM prompts.

Loads once at import time. To apply changes: edit the YAML files and restart
the backend (or send SIGHUP to gunicorn).

Public API:
    from services.params import params, prompts

    params.get("RSI_PERIOD")          # → 14
    params.gear(3)                     # → dict for gear 3 profile
    params.sell_urgency_points()       # → flat dict of all urgency point values

    prompts.get("ai_conviction_engine")            # → raw template str
    prompts.render("ai_conviction_engine", vix=..) # → interpolated str
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_PARAMS_FILE = _CONFIG_DIR / "analysis_params.yaml"
_PROMPTS_FILE = _CONFIG_DIR / "prompts.yaml"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError(
            "pyyaml is required but not installed. Run: pip install pyyaml>=6.0"
        ) from e
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def _flatten(d: dict, prefix: str = "", sep: str = ".") -> dict:
    """Recursively flatten a nested dict into dotted keys."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key, sep))
        else:
            out[key] = v
    return out


_MISSING = object()


class _Params:
    """Accessor for analysis_params.yaml."""

    def __init__(self, data: dict) -> None:
        self._data = data
        # Build a flat lookup of every leaf value keyed by its CONSTANT_NAME (uppercase last segment)
        self._flat: dict[str, Any] = {}
        for section_data in data.values():
            if isinstance(section_data, dict):
                for k, v in section_data.items():
                    if not isinstance(v, dict):
                        self._flat[k] = v

        # Also flatten nested sell_urgency_points into SELL_URGENCY_POINTS_* style keys
        urgency_data = data.get("sell_urgency_points", {})
        for section, signals in urgency_data.items():
            if isinstance(signals, dict):
                for signal_name, pts in signals.items():
                    key = f"SELL_URGENCY_{section.upper()}_{signal_name.upper()}"
                    self._flat[key] = pts

    def get(self, key: str, default: Any = _MISSING) -> Any:
        """Return value by constant name (e.g. 'RSI_PERIOD').

        Raises KeyError if key is absent and no default given — catches typos early.
        """
        if key in self._flat:
            return self._flat[key]
        if default is not _MISSING:
            return default
        raise KeyError(
            f"Parameter '{key}' not found in {_PARAMS_FILE}. "
            "Check spelling or add it to the YAML."
        )

    def gear(self, gear_number: int) -> dict:
        """Return the full profile dict for a strategy gear (1–5)."""
        gears = self._data.get("strategy_gears", {}).get("gears", {})
        if gear_number not in gears:
            raise KeyError(f"Gear {gear_number} not defined in strategy_gears.gears")
        return dict(gears[gear_number])

    def all_gears(self) -> dict:
        """Return the full strategy_gears dict (including default_gear)."""
        return dict(self._data.get("strategy_gears", {}))

    def sell_urgency_points(self) -> dict[str, int]:
        """Return flat dict of all urgency point values keyed by descriptive name."""
        out = {}
        for section, signals in self._data.get("sell_urgency_points", {}).items():
            if isinstance(signals, dict):
                for signal_name, pts in signals.items():
                    out[f"{section}.{signal_name}"] = pts
        return out

    def section(self, name: str) -> dict:
        """Return a top-level YAML section by name."""
        if name not in self._data:
            raise KeyError(f"Section '{name}' not found in {_PARAMS_FILE}")
        return dict(self._data[name])


class _PromptRenderError(Exception):
    """Raised when a required template variable is missing."""


class _StrictFormatDict(dict):
    """A dict that raises on missing keys during str.format_map."""
    def __missing__(self, key):
        raise _PromptRenderError(
            f"Prompt template requires variable '{{{key}}}' but it was not supplied. "
            "Either add it to the render() call or fix the template in prompts.yaml."
        )


class _Prompts:
    """Accessor for prompts.yaml."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def get(self, name: str) -> str:
        """Return the raw template string (with {var} placeholders unreplaced)."""
        if name not in self._data:
            raise KeyError(
                f"Prompt '{name}' not found in {_PROMPTS_FILE}. "
                "Check spelling or add it to prompts.yaml."
            )
        entry = self._data[name]
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict):
            template = entry.get("template")
            if template is None:
                raise KeyError(f"Prompt '{name}' has no 'template' key in prompts.yaml.")
            return template
        raise TypeError(f"Unexpected type for prompt '{name}': {type(entry)}")

    def render(self, name: str, **kwargs: Any) -> str:
        """Render a prompt template, substituting {var} placeholders.

        Raises _PromptRenderError if a required variable is missing (fails loudly
        rather than silently leaving unreplaced placeholders).
        """
        template = self.get(name)
        try:
            return template.format_map(_StrictFormatDict(kwargs))
        except _PromptRenderError:
            raise
        except KeyError as e:
            raise _PromptRenderError(
                f"Prompt '{name}' template uses variable {e} which was not supplied."
            ) from e

    def meta(self, name: str) -> dict:
        """Return full prompt entry dict (includes provider, extended_thinking, etc.)."""
        if name not in self._data:
            raise KeyError(f"Prompt '{name}' not found in {_PROMPTS_FILE}.")
        entry = self._data[name]
        return dict(entry) if isinstance(entry, dict) else {"template": entry}


# ---------------------------------------------------------------------------
# Singletons — loaded once at import time
# ---------------------------------------------------------------------------

try:
    _params_data = _load_yaml(_PARAMS_FILE)
    params = _Params(_params_data)
    logger.debug("[Params] Loaded %s", _PARAMS_FILE)
except Exception as _e:
    logger.error("[Params] Failed to load %s: %s", _PARAMS_FILE, _e)
    raise

try:
    _prompts_data = _load_yaml(_PROMPTS_FILE)
    prompts = _Prompts(_prompts_data)
    logger.debug("[Prompts] Loaded %s", _PROMPTS_FILE)
except Exception as _e:
    logger.error("[Prompts] Failed to load %s: %s", _PROMPTS_FILE, _e)
    raise
