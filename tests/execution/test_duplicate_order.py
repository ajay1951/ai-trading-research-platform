"""
Reliability Test: Duplicate Order Prevention & Idempotency
==========================================================
Verifies that network retries or duplicate signals cannot trigger duplicate fills.
"""

import pytest
from typing import Set


class OrderIdempotencyTracker:
    def __init__(self):
        self.seen_order_ids: Set[str] = set()

    def process_order(self, client_order_id: str) -> bool:
        """Returns True if order is new and accepted, False if duplicate."""
        if client_order_id in self.seen_order_ids:
            return False
        self.seen_order_ids.add(client_order_id)
        return True


def test_first_order_accepted():
    tracker = OrderIdempotencyTracker()
    assert tracker.process_order("ORDER-2026-BTC-001") is True


def test_duplicate_order_rejected():
    tracker = OrderIdempotencyTracker()
    assert tracker.process_order("ORDER-2026-BTC-001") is True
    # Duplicate retry with same idempotency key must be blocked
    assert tracker.process_order("ORDER-2026-BTC-001") is False


def test_distinct_orders_accepted():
    tracker = OrderIdempotencyTracker()
    assert tracker.process_order("ORDER-2026-BTC-001") is True
    assert tracker.process_order("ORDER-2026-BTC-002") is True
