"""Pydantic v2 request body validation for Flask routes.

Usage:
    from services.validation import validate_request, SimulatorExecuteBody

    @app.route("/api/simulator/execute", methods=["POST"])
    @validate_request(SimulatorExecuteBody)
    def my_view(body: SimulatorExecuteBody):
        # body is a validated Pydantic model instance
        ...

Error format on validation failure:
    {"success": false, "error": "<first error message>", "code": "VALIDATION_ERROR"}
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Optional, Type

from flask import request, jsonify
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def validate_request(schema: Type[BaseModel]):
    """Decorator that validates the JSON request body against a Pydantic model.

    The validated model instance is passed as the first positional argument
    after `self` (or as the only extra argument for function-based views).
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            body = request.get_json(silent=True) or {}
            try:
                parsed = schema.model_validate(body)
            except Exception as exc:
                # Pydantic v2 ValidationError → extract first human-readable message
                first_msg = str(exc)
                try:
                    errors = exc.errors()  # type: ignore[attr-defined]
                    if errors:
                        loc = " → ".join(str(l) for l in errors[0].get("loc", []))
                        msg = errors[0].get("msg", str(exc))
                        first_msg = f"{loc}: {msg}" if loc else msg
                except Exception:
                    pass
                return jsonify({
                    "success": False,
                    "error": first_msg,
                    "code": "VALIDATION_ERROR",
                }), 400
            return fn(*args, body=parsed, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Request body schemas
# ---------------------------------------------------------------------------

class RegisterBody(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v

    @field_validator("name")
    @classmethod
    def name_clean(cls, v: str) -> str:
        return v.strip()


class LoginBody(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.strip().lower()


class RefreshBody(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class BrokerLinkBody(BaseModel):
    request_token: str = Field(..., min_length=5, max_length=200)


class SimulatorExecuteBody(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)
    quantity: int = Field(..., ge=1)
    atr: float = Field(..., gt=0)
    trail_multiplier: float = Field(default=1.5, ge=0.5, le=5.0)
    instrument_token: Optional[int] = None
    ltp: Optional[float] = Field(default=None, gt=0)

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.strip().upper()


class SimulatorCloseBody(BaseModel):
    trade_id: str = Field(..., min_length=1)


class SimulatorResetBody(BaseModel):
    initial_capital: float = Field(default=1_000_000, ge=10_000, le=100_000_000)


class AnalyzeStockBody(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)
    instrument_token: Optional[int] = None
    llm_provider: Optional[str] = Field(default=None)

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("llm_provider")
    @classmethod
    def provider_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = {"claude", "openai"}
        if v not in allowed:
            raise ValueError(f"llm_provider must be one of {allowed}")
        return v


class ChatSendBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None


class CalculateExitsBody(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)
    ltp: float = Field(..., gt=0)
    atr: float = Field(..., gt=0)
    trail_multiplier: Optional[float] = Field(default=None, ge=0.5, le=5.0)

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.strip().upper()


class ChangePasswordBody(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class ForgotPasswordBody(BaseModel):
    email: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str) -> str:
        return v.strip().lower()


class ResetPasswordBody(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)


class LLMKeyBody(BaseModel):
    provider: str = Field(...)
    api_key: str = Field(..., min_length=10, max_length=500)

    @field_validator("provider")
    @classmethod
    def provider_valid(cls, v: str) -> str:
        allowed = {"anthropic", "openai"}
        if v not in allowed:
            raise ValueError(f"provider must be one of {allowed}")
        return v
