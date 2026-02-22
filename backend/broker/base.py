"""Abstract broker interface.

Decouples business logic from broker-specific API details.
Any broker (Kite, Upstox, mock) can be used by implementing this interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BrokerAdapter(ABC):
    """Abstract base class for broker adapters."""

    @abstractmethod
    def get_holdings(self) -> List[Dict[str, Any]]:
        """Get user holdings."""
        ...

    @abstractmethod
    def get_positions(self) -> Dict[str, Any]:
        """Get user positions (net and day)."""
        ...

    @abstractmethod
    def get_quote(self, symbols: List[str]) -> Dict[str, Any]:
        """Get full quote for symbols (e.g. ['NSE:RELIANCE', 'BSE:SENSEX'])."""
        ...

    @abstractmethod
    def get_ltp(self, symbols: List[str]) -> Dict[str, Any]:
        """Get last traded price for symbols."""
        ...

    @abstractmethod
    def get_historical_data(
        self,
        instrument_token: int,
        from_date: str,
        to_date: str,
        interval: str,
    ) -> List[Dict[str, Any]]:
        """Get historical OHLCV candle data."""
        ...

    @abstractmethod
    def get_instruments(self, exchange: str) -> List[Dict[str, Any]]:
        """Get list of tradable instruments for an exchange."""
        ...

    @abstractmethod
    def get_margins(self, segment: str) -> Dict[str, Any]:
        """Get account margins/funds for a segment (e.g. 'equity')."""
        ...

    @abstractmethod
    def profile(self) -> Dict[str, Any]:
        """Get user profile."""
        ...

    @abstractmethod
    def login_url(self) -> str:
        """Get the OAuth login URL."""
        ...

    @abstractmethod
    def generate_session(self, request_token: str) -> Dict[str, Any]:
        """Exchange request token for access token."""
        ...

    @abstractmethod
    def set_access_token(self, access_token: str) -> None:
        """Set the access token for authenticated API calls."""
        ...
