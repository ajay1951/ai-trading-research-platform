"""
Reliability Test: Risk Management Rules & Limits Enforcement
============================================================
Verifies that gross exposure caps, concentration limits, and circuit breakers
reliably intercept and reject non-compliant order requests.
"""

import pytest
from risk.exposure import ExposureManager
from risk.circuit_breaker import CircuitBreaker
from risk.drawdown import DrawdownMonitor


def test_exposure_limit_enforced():
    """Test: Reject order that exceeds 100% gross portfolio exposure."""
    mgr = ExposureManager(max_gross_exposure=1.0, max_single_asset_pct=0.35)
    equity = 1000.0

    current_positions = {
        "ETH/USDT": {"size": 2.0, "entry_price": 300.0} # $600 (60% exposure)
    }

    # Requesting additional $500 position -> Total $1100 (110% exposure) -> MUST BE REJECTED
    allowed = mgr.check_exposure(equity, current_positions, "SOL/USDT", new_notional=500.0)
    assert allowed is False

    # Requesting $300 position -> Total $900 (90% exposure) -> ALLOWED
    allowed_small = mgr.check_exposure(equity, current_positions, "SOL/USDT", new_notional=300.0)
    assert allowed_small is True


def test_single_asset_concentration_limit():
    """Test: Reject order that allocates >35% to a single asset."""
    mgr = ExposureManager(max_gross_exposure=1.0, max_single_asset_pct=0.35)
    equity = 1000.0
    current_positions = {}

    # Attempting to allocate $400 (40%) to BTC -> MUST BE REJECTED
    assert mgr.check_exposure(equity, current_positions, "BTC/USDT", new_notional=400.0) is False

    # Allocating $300 (30%) -> ALLOWED
    assert mgr.check_exposure(equity, current_positions, "BTC/USDT", new_notional=300.0) is True


def test_circuit_breaker_tripping():
    """Test: 5 consecutive errors trip the emergency circuit breaker."""
    cb = CircuitBreaker(max_consecutive_errors=3)
    assert cb.is_tripped is False

    cb.record_error("API Timeout 1")
    cb.record_error("API Timeout 2")
    assert cb.is_tripped is False

    cb.record_error("API Timeout 3")
    assert cb.is_tripped is True
    assert "Exceeded 3 consecutive errors" in cb.trip_reason
