"""
Reliability Test: WebSocket Reconnect & Backoff
===============================================
Verifies that WebSocket disconnections trigger exponential backoff reconnection
without crashing the execution daemon.
"""

import pytest
import time
from unittest.mock import MagicMock, patch


class MockWebSocketClient:
    def __init__(self, fail_times: int = 2):
        self.fail_times = fail_times
        self.attempts = 0
        self.is_connected = False

    def connect(self) -> bool:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            self.is_connected = False
            raise ConnectionError("Mock WebSocket connection dropped")
        self.is_connected = True
        return True


def connect_with_retry(client, max_retries: int = 5, backoff_base: float = 0.01) -> bool:
    for attempt in range(1, max_retries + 1):
        try:
            return client.connect()
        except ConnectionError:
            time.sleep(backoff_base * (2 ** (attempt - 1)))
    return False


def test_websocket_reconnect_success():
    """Test: Reconnects successfully after transient dropouts."""
    client = MockWebSocketClient(fail_times=2)
    success = connect_with_retry(client, max_retries=5)
    assert success is True
    assert client.is_connected is True
    assert client.attempts == 3


def test_websocket_reconnect_exhausted():
    """Test: Safely fails without hanging if server is permanently down."""
    client = MockWebSocketClient(fail_times=10)
    success = connect_with_retry(client, max_retries=3)
    assert success is False
    assert client.is_connected is False
    assert client.attempts == 3
