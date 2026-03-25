"""Kite Connect broker adapter.

Thin wrapper around the KiteConnect SDK that implements the BrokerAdapter interface.
If Kite changes their API or you switch to another broker, only this file needs updating.
"""

from typing import Any, Dict, List, Optional

from kiteconnect import KiteConnect

from broker.base import BrokerAdapter
from config import KITE_API_KEY, KITE_API_SECRET


class KiteBrokerAdapter(BrokerAdapter):
    """KiteConnect implementation of BrokerAdapter."""

    # --- Kite constants (expose for consumers without raw_kite access) ---
    VARIETY_REGULAR = "regular"
    VARIETY_AMO = "amo"
    EXCHANGE_NSE = "NSE"
    EXCHANGE_BSE = "BSE"
    TRANSACTION_TYPE_BUY = "BUY"
    TRANSACTION_TYPE_SELL = "SELL"
    ORDER_TYPE_MARKET = "MARKET"
    ORDER_TYPE_LIMIT = "LIMIT"
    ORDER_TYPE_SL = "SL"
    ORDER_TYPE_SLM = "SL-M"
    PRODUCT_CNC = "CNC"
    PRODUCT_MIS = "MIS"
    VALIDITY_DAY = "DAY"

    def __init__(self, access_token: str = ""):
        self._kite = KiteConnect(api_key=KITE_API_KEY)
        if access_token:
            self._kite.set_access_token(access_token)

    @property
    def raw_kite(self) -> KiteConnect:
        """Access the underlying KiteConnect instance (for edge cases)."""
        return self._kite

    # --- Portfolio ---

    def get_holdings(self) -> List[Dict[str, Any]]:
        return self._kite.holdings()

    def get_positions(self) -> Dict[str, Any]:
        return self._kite.positions()

    # --- Market data ---

    def get_quote(self, symbols: List[str]) -> Dict[str, Any]:
        return self._kite.quote(symbols)

    def get_ltp(self, symbols: List[str]) -> Dict[str, Any]:
        return self._kite.ltp(symbols)

    def get_historical_data(
        self,
        instrument_token: int,
        from_date: str,
        to_date: str,
        interval: str,
    ) -> List[Dict[str, Any]]:
        return self._kite.historical_data(
            instrument_token, from_date, to_date, interval
        )

    def get_instruments(self, exchange: str) -> List[Dict[str, Any]]:
        return self._kite.instruments(exchange)

    # --- Account ---

    def get_margins(self, segment: str) -> Dict[str, Any]:
        return self._kite.margins(segment)

    def profile(self) -> Dict[str, Any]:
        return self._kite.profile()

    # --- Auth ---

    def login_url(self) -> str:
        return self._kite.login_url()

    def generate_session(self, request_token: str) -> Dict[str, Any]:
        return self._kite.generate_session(request_token, api_secret=KITE_API_SECRET)

    def set_access_token(self, access_token: str) -> None:
        self._kite.set_access_token(access_token)

    # --- Order management ---

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
        kwargs = dict(
            variety=variety,
            exchange=exchange,
            tradingsymbol=tradingsymbol,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=order_type,
            product=product,
        )
        if price is not None:
            kwargs["price"] = price
        if trigger_price is not None:
            kwargs["trigger_price"] = trigger_price
        if tag is not None:
            kwargs["tag"] = tag[:20]  # Kite tag max 20 chars
        return self._kite.place_order(**kwargs)

    def modify_order(
        self,
        variety: str,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[str] = None,
    ) -> str:
        kwargs: Dict[str, Any] = dict(variety=variety, order_id=order_id)
        if quantity is not None:
            kwargs["quantity"] = quantity
        if price is not None:
            kwargs["price"] = price
        if trigger_price is not None:
            kwargs["trigger_price"] = trigger_price
        if order_type is not None:
            kwargs["order_type"] = order_type
        return self._kite.modify_order(**kwargs)

    def cancel_order(self, variety: str, order_id: str) -> str:
        return self._kite.cancel_order(variety=variety, order_id=order_id)

    def get_orders(self) -> List[Dict[str, Any]]:
        return self._kite.orders()

    def get_order_history(self, order_id: str) -> List[Dict[str, Any]]:
        return self._kite.order_history(order_id)

    def get_order_trades(self, order_id: str) -> List[Dict[str, Any]]:
        return self._kite.order_trades(order_id)
