"""Generic circuit breaker for external service calls.

States:
    CLOSED    — normal operation; calls pass through
    OPEN      — too many failures; calls rejected immediately
    HALF_OPEN — recovery probe; one call allowed through to test the service

Usage:
    _cb = CircuitBreaker("screener.in", failure_threshold=3, recovery_timeout=300)

    if _cb.is_call_permitted():
        try:
            result = call_external_service()
            _cb.record_success()
        except Exception:
            _cb.record_failure()
            return fallback()
    else:
        return fallback()
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

_CLOSED    = "CLOSED"
_OPEN      = "OPEN"
_HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Thread-safe circuit breaker."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 300.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = _CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_call_permitted(self) -> bool:
        """Return True if a call should be attempted."""
        with self._lock:
            if self._state == _CLOSED:
                return True
            if self._state == _OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._state = _HALF_OPEN
                    logger.info("[CircuitBreaker][%s] Transitioning OPEN→HALF_OPEN", self.name)
                    return True
                return False
            # HALF_OPEN — allow one probe call
            return True

    def record_success(self) -> None:
        """Call this when an external call succeeds."""
        with self._lock:
            if self._state != _CLOSED:
                logger.info(
                    "[CircuitBreaker][%s] Success — transitioning %s→CLOSED",
                    self.name, self._state,
                )
            self._state = _CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        """Call this when an external call fails."""
        with self._lock:
            self._failure_count += 1
            if self._state == _HALF_OPEN or self._failure_count >= self.failure_threshold:
                self._state = _OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "[CircuitBreaker][%s] Opened after %d failure(s). "
                    "Will retry in %.0fs.",
                    self.name, self._failure_count, self.recovery_timeout,
                )

    @property
    def state(self) -> str:
        with self._lock:
            return self._state
