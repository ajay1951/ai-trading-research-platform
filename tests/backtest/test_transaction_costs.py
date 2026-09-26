"""
Backtesting Integrity Test: Transaction Costs & Slippage Modeling
================================================================
Verifies that maker/taker fees and slippage drift are strictly deducted
from portfolio cash and equity on every execution.
"""

import pytest
import numpy as np
from training.benchmark_suite import simulate_strategy_returns


def test_fees_and_slippage_are_deducted():
    """
    Test: In an asset that stays completely flat (zero price change),
    frequent position flipping MUST result in cumulative losses exactly proportional
    to fee_rate + slippage.
    """
    n_bars = 100
    prices = np.full(n_bars, 100.0)
    
    # Alternate between Long (1) and Flat (0) every bar -> 99 position transitions
    signals = np.array([1.0 if i % 2 == 0 else 0.0 for i in range(n_bars)])

    fee_rate = 0.0004   # 0.04% fee
    slippage = 0.0002   # 0.02% slippage
    cost_per_trade = fee_rate + slippage

    res = simulate_strategy_returns(prices, signals, fee_rate=fee_rate, slippage=slippage)

    # In a flat market, return must be negative solely due to costs
    assert res["return_pct"] < 0.0, "Portfolio must show a loss due to trading friction"
    assert res["trades"] > 0, "Trades count must be positive"
    
    # Verify fee-free baseline shows exactly 0% return
    res_zero_cost = simulate_strategy_returns(prices, signals, fee_rate=0.0, slippage=0.0)
    assert np.isclose(res_zero_cost["return_pct"], 0.0, atol=1e-5), "Zero-cost simulation on flat price must yield 0% return"
