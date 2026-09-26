"""
Risk Management: Emergency Circuit Breaker
==========================================
Halts trading during extreme market dislocations, runaway slippage, or API connection errors.
"""

import time
import logging

logger = logging.getLogger("CircuitBreaker")


class CircuitBreaker:
    def __init__(self, max_consecutive_errors: int = 5, max_slippage_deviation: float = 0.015):
        self.max_errors = max_consecutive_errors
        self.max_slippage = max_slippage_deviation
        self.consecutive_errors: int = 0
        self.is_tripped: bool = False
        self.trip_reason: str = ""
        self.trip_timestamp: float = 0.0

    def record_success(self):
        """Resets error counter upon successful execution."""
        self.consecutive_errors = 0

    def record_error(self, error_msg: str) -> bool:
        """Records an execution error. Trips circuit breaker if threshold exceeded."""
        self.consecutive_errors += 1
        logger.warning(f"Execution error ({self.consecutive_errors}/{self.max_errors}): {error_msg}")
        if self.consecutive_errors >= self.max_errors:
            self.trip(f"Exceeded {self.max_errors} consecutive errors: {error_msg}")
            return True
        return False

    def check_slippage(self, arrival_price: float, fill_price: float, is_short: bool = False) -> bool:
        """Checks if realized execution slippage exceeded safety tolerance."""
        if arrival_price <= 0 or fill_price <= 0:
            return False
        deviation = (fill_price - arrival_price) / arrival_price if not is_short else (arrival_price - fill_price) / arrival_price
        if abs(deviation) > self.max_slippage:
            self.trip(f"Runaway slippage detected: {deviation * 100:.2f}% (Limit: {self.max_slippage * 100:.2f}%)")
            return False
        return True

    def trip(self, reason: str):
        self.is_tripped = True
        self.trip_reason = reason
        self.trip_timestamp = time.time()
        logger.critical(f"EMERGENCY CIRCUIT BREAKER TRIPPED! Reason: {reason}")

    def reset(self):
        self.is_tripped = False
        self.trip_reason = ""
        self.consecutive_errors = 0
        logger.info("Circuit breaker manually reset.")
