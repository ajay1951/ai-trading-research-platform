"""
Reliability Test: Stale Price Rejection
=======================================
Verifies that orders are rejected when incoming market quotes are stale
(older than maximum allowable age threshold).
"""

import pytest
import time


def is_price_fresh(quote_timestamp_ms: float, current_time_ms: float, max_latency_ms: float = 3000.0) -> bool:
    """Returns True only if quote is within max_latency_ms."""
    if quote_timestamp_ms <= 0 or current_time_ms <= 0:
        return False
    age = current_time_ms - quote_timestamp_ms
    return 0 <= age <= max_latency_ms


def test_fresh_price_accepted():
    """Test: Quote aged 200ms is accepted."""
    now_ms = time.time() * 1000.0
    quote_ms = now_ms - 200.0
    assert is_price_fresh(quote_ms, now_ms, max_latency_ms=1000.0) is True


def test_stale_price_rejected():
    """Test: Quote aged 5000ms is strictly rejected."""
    now_ms = time.time() * 1000.0
    quote_ms = now_ms - 5000.0
    assert is_price_fresh(quote_ms, now_ms, max_latency_ms=1000.0) is False


def test_future_timestamp_rejected():
    """Test: Quote with clock drift from future is rejected."""
    now_ms = time.time() * 1000.0
    quote_ms = now_ms + 2000.0 # 2s into future
    assert is_price_fresh(quote_ms, now_ms, max_latency_ms=1000.0) is False
