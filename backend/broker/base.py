"""Abstract broker interface.

Decouples business logic from broker-specific API details.
Any broker (Kite, Upstox, mock) can be used by implementing this interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BrokerAdapter(ABC):
    """Abstract base class for broker adapters."""

    # --- Portfolio ---

    @abstractmethod
    def get_holdings(self) -> List[Dict[str, Any]]:
        """Get user holdings."""
        ...

    @abstractmethod
    def get_positions(self) -> Dict[str, Any]:
        """Get user positions (net and day)."""
        ...

    # --- Market data ---

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

    # --- Account ---

    @abstractmethod
    def get_margins(self, segment: str) -> Dict[str, Any]:
        """Get account margins/funds for a segment (e.g. 'equity')."""
        ...

    @abstractmethod
    def profile(self) -> Dict[str, Any]:
        """Get user profile."""
        ...

    # --- Auth ---

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

    # --- Order management ---

    @abstractmethod
    def place_order(
        self,
        variety: str,
        exchange: str,
        tradingsymbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        product: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        tag: Optional[str] = None,
    ) -> str:
        """Place an order. Returns order_id."""
        ...

    @abstractmethod
    def modify_order(
        self,
        variety: str,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
    ) -> str:
        """Modify an existing order. Returns order_id."""
        ...

    @abstractmethod
    def cancel_order(self, variety: str, order_id: str) -> str:
        """Cancel an order. Returns order_id."""
        ...

    @abstractmethod
    def get_orders(self) -> List[Dict[str, Any]]:
        """Get list of all orders for the day."""
        ...

    @abstractmethod
    def get_order_history(self, order_id: str) -> List[Dict[str, Any]]:
        """Get status history for a specific order."""
        ...

    @abstractmethod
    def get_order_trades(self, order_id: str) -> List[Dict[str, Any]]:
        """Get trade fills for a specific order."""
        ...
