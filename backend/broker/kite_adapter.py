"""Kite Connect broker adapter.

Thin wrapper around the KiteConnect SDK that implements the BrokerAdapter interface.
If Kite changes their API or you switch to another broker, only this file needs updating.
"""

from typing import Any, Dict, List

from kiteconnect import KiteConnect

from broker.base import BrokerAdapter
from config import KITE_API_KEY, KITE_API_SECRET


class KiteBrokerAdapter(BrokerAdapter):
    """KiteConnect implementation of BrokerAdapter."""

    def __init__(self, access_token: str = ""):
        self._kite = KiteConnect(api_key=KITE_API_KEY)
        if access_token:
            self._kite.set_access_token(access_token)

    @property
    def raw_kite(self) -> KiteConnect:
        """Access the underlying KiteConnect instance (for edge cases)."""
        return self._kite

    def get_holdings(self) -> List[Dict[str, Any]]:
        return self._kite.holdings()

    def get_positions(self) -> Dict[str, Any]:
        return self._kite.positions()

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

    def get_margins(self, segment: str) -> Dict[str, Any]:
        return self._kite.margins(segment)

    def profile(self) -> Dict[str, Any]:
        return self._kite.profile()

    def login_url(self) -> str:
        return self._kite.login_url()

    def generate_session(self, request_token: str) -> Dict[str, Any]:
        return self._kite.generate_session(request_token, api_secret=KITE_API_SECRET)

    def set_access_token(self, access_token: str) -> None:
        self._kite.set_access_token(access_token)
