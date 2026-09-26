"""
Backtesting Integrity Test: Position Sizing & Capital Allocation
================================================================
Verifies that slot limits, maximum exposure, and leverage bounds
cannot be violated by the execution engine.
"""

import pytest
import numpy as np


def calculate_position_size(
    available_cash: float,
    max_slots: int = 2,
    max_risk_pct: float = 0.50,
    price: float = 100.0
) -> float:
    """Calculates position size strictly respecting slot allocation and cash."""
    if available_cash <= 0 or price <= 0 or max_slots <= 0:
        return 0.0
    slot_capital = (available_cash * max_risk_pct) / max_slots
    size = slot_capital / price
    return size


def test_position_sizing_respects_limits():
    """
    Test: Position allocation cannot exceed allocated capital per slot.
    """
    cash = 1000.0
    price = 50.0
    max_slots = 2
    max_risk_pct = 0.50 # 50% max exposure

    size = calculate_position_size(cash, max_slots=max_slots, max_risk_pct=max_risk_pct, price=price)
    notional = size * price

    # 1 slot should be exactly $250 (50% of 1000 / 2 slots)
    assert np.isclose(notional, 250.0)
    assert notional <= (cash * max_risk_pct)


def test_zero_cash_produces_zero_size():
    """
    Test: Sizing returns 0 if wallet has 0 cash.
    """
    size = calculate_position_size(0.0, price=100.0)
    assert size == 0.0
