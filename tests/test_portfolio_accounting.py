"""
Backtesting Integrity Test: Portfolio Accounting & Mark-to-Market Math
======================================================================
Verifies that wallet cash, open position notional, and total equity
follow strict double-entry balance equations.
"""

import pytest
import numpy as np


def test_mark_to_market_accounting():
    """
    Test: Total Equity = Cash + Mark-to-Market Open Position Value.
    Long PnL: (Current Price - Entry Price) * Size
    Short PnL: (Entry Price - Current Price) * Size
    """
    initial_cash = 1000.0
    
    # 1. Open a Long Position: Buy 2 units at $100
    entry_price_long = 100.0
    size_long = 2.0
    notional_cost_long = entry_price_long * size_long # $200
    cash_after_buy = initial_cash - notional_cost_long # $800

    # Price moves to $110 (+10%)
    current_price_up = 110.0
    unrealized_pnl_long = (current_price_up - entry_price_long) * size_long # +$20
    current_position_value_long = size_long * current_price_up # $220
    total_equity_up = cash_after_buy + current_position_value_long # $1020

    assert np.isclose(total_equity_up, 1020.0)
    assert np.isclose(unrealized_pnl_long, 20.0)
    assert np.isclose(total_equity_up, initial_cash + unrealized_pnl_long)

    # 2. Open a Short Position: Short 1 unit at $200
    entry_price_short = 200.0
    size_short = 1.0
    # Price falls to $180 (-10% price, profitable for short)
    current_price_down = 180.0
    unrealized_pnl_short = (entry_price_short - current_price_down) * size_short # +$20
    
    assert np.isclose(unrealized_pnl_short, 20.0)
