"""Broker abstraction layer.

Provides a factory function to get a broker adapter based on configuration.
Currently only supports Kite Connect; future adapters (Upstox, etc.) can be
plugged in by implementing the BrokerAdapter interface.
"""

from broker.kite_adapter import KiteBrokerAdapter
from broker.base import BrokerAdapter


def get_broker(access_token: str) -> BrokerAdapter:
    """Factory — returns a broker adapter instance for the given access token."""
    return KiteBrokerAdapter(access_token)
