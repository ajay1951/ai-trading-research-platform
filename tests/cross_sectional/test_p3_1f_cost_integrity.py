"""
tests/cross_sectional/test_p3_1f_cost_integrity.py
==================================================
P3-1F Transaction Cost Integrity Audit & Regression Test Suite.

Validates:
1. Signal-to-fill accounting & double-counting elimination
2. Synthetic BUY/SELL favorable and unfavorable delay dynamics
3. Critical regression test ensuring delay is NOT charged twice
4. Corwin-Schultz spread numerical stability across edge cases
5. Total cost conservation (Total = Fee + HalfSpread + Slippage + Impact)
6. Future mutation and causality invariance
7. Determinism across successive runs
"""

import pytest
import numpy as np
import pandas as pd
from evaluation.transaction_costs import (
    TransactionCostEngine,
    CostModelConfig,
    CostModelProfile,
    TradeCostBreakdown,
    SpreadModel,
    FeeModel,
    SlippageModel,
    MarketImpactModel,
    SCENARIO_CONFIGS
)


# =============================================================================
# 1. Synthetic Accounting & Delay Double-Counting Regression Tests
# =============================================================================

def test_delay_double_counting_eliminated_in_p3_1f():
    """
    Critical Regression Test:
    In a backtest where an order is placed at bar t and fills at bar t+1 open,
    the gross return is measured from P_fill(t+1) to P_exit(t+2).
    The price movement (P_fill - P_signal) is ALREADY reflected by the fact
    that the investor did NOT earn returns between t and t+1.
    Therefore, the transaction cost engine MUST NOT deduct (P_fill - P_signal) AGAIN.
    """
    cfg_p3_1f = CostModelConfig(profile=CostModelProfile.P3_1F_BASE) # include_delay_cost = False
    engine_p3_1f = TransactionCostEngine(cfg_p3_1f)

    # Synthetic Trade: Signal at 100.0, Fill at 105.0 (5% price jump)
    ctx = {
        "high": 105.0, "low": 100.0, "high_prev": 101.0, "low_prev": 99.0,
        "realized_vol_24h": 0.015, "rolling_24h_quote_volume": 50_000_000.0,
        "fill_price": 105.0
    }

    tb = engine_p3_1f.estimate_trade_cost(
        symbol="BTCUSDT",
        timestamp="2026-01-01 00:00:00",
        side="BUY",
        quantity=1.0,
        reference_price=100.0,
        market_context=ctx
    )

    # In P3-1F, delay_bps must be 0.0 to prevent double subtraction
    assert tb.delay_bps == 0.0
    assert tb.delay_dollars == 0.0
    # Total friction must strictly consist of Fee + Spread + Slippage + Impact
    expected_total = tb.fee_dollars + tb.spread_dollars + tb.slippage_dollars + tb.impact_dollars
    assert np.isclose(tb.total_cost_dollars, expected_total)


def test_synthetic_buy_price_increase_vs_decrease():
    """
    Tests economic behavior under favorable vs unfavorable execution drift.
    """
    engine_p3_1f = TransactionCostEngine(CostModelConfig(profile=CostModelProfile.P3_1F_BASE))

    # Buy with price increase (100 -> 105)
    ctx_up = {"high": 105.0, "low": 100.0, "fill_price": 105.0, "realized_vol_24h": 0.015, "rolling_24h_quote_volume": 50_000_000.0}
    tb_up = engine_p3_1f.estimate_trade_cost("BTCUSDT", "2026-01-01", "BUY", 1.0, 100.0, ctx_up)

    # Buy with price decrease (100 -> 95)
    ctx_down = {"high": 100.0, "low": 95.0, "fill_price": 95.0, "realized_vol_24h": 0.015, "rolling_24h_quote_volume": 50_000_000.0}
    tb_down = engine_p3_1f.estimate_trade_cost("BTCUSDT", "2026-01-01", "BUY", 1.0, 100.0, ctx_down)

    # Both must have valid non-negative fees, spread, slippage, and zero double-counted delay
    assert tb_up.delay_bps == 0.0
    assert tb_down.delay_bps == 0.0
    assert tb_up.total_cost_dollars > 0.0
    assert tb_down.total_cost_dollars > 0.0


def test_synthetic_sell_price_increase_vs_decrease():
    """
    Tests SELL execution accounting.
    """
    engine_p3_1f = TransactionCostEngine(CostModelConfig(profile=CostModelProfile.P3_1F_BASE))

    ctx = {"high": 102.0, "low": 98.0, "fill_price": 99.0, "realized_vol_24h": 0.015, "rolling_24h_quote_volume": 50_000_000.0}
    tb_sell = engine_p3_1f.estimate_trade_cost("BTCUSDT", "2026-01-01", "SELL", 2.0, 100.0, ctx)

    assert tb_sell.side == "SELL"
    assert tb_sell.notional == 200.0
    assert tb_sell.delay_bps == 0.0
    assert tb_sell.fee_dollars > 0.0


# =============================================================================
# 2. Corwin-Schultz Numerical Stability & Edge Cases
# =============================================================================

def test_corwin_schultz_extreme_edge_cases():
    cfg = CostModelConfig(profile=CostModelProfile.P3_1F_BASE, min_spread_bps=1.0, max_spread_bps=50.0)
    spread_model = SpreadModel(cfg)

    # Case A: Identical high and low (zero range)
    sp_zero_range = spread_model.estimate_spread_bps(100.0, 100.0, 100.0, 100.0, 0.0, 10_000_000.0)
    assert 1.0 <= sp_zero_range <= 50.0
    assert not np.isnan(sp_zero_range)

    # Case B: Extreme high volatility / flash crash (50% range)
    sp_extreme = spread_model.estimate_spread_bps(150.0, 50.0, 140.0, 60.0, 0.10, 5_000_000.0)
    assert sp_extreme <= 50.0 # Capped by max_spread_bps
    assert sp_extreme >= 1.0

    # Case C: Missing previous bar (None)
    sp_first_bar = spread_model.estimate_spread_bps(101.0, 99.0, None, None, 0.015, 50_000_000.0)
    assert 1.0 <= sp_first_bar <= 50.0
    assert not np.isnan(sp_first_bar)


# =============================================================================
# 3. Cost Accounting Conservation
# =============================================================================

def test_cost_accounting_conservation():
    cfg = CostModelConfig(profile=CostModelProfile.P3_1F_BASE)
    engine = TransactionCostEngine(cfg)

    ctx = {
        "high": 101.0, "low": 99.0, "high_prev": 100.5, "low_prev": 99.5,
        "realized_vol_24h": 0.02, "rolling_24h_quote_volume": 20_000_000.0,
        "fill_price": 100.2
    }

    tb = engine.estimate_trade_cost("ETHUSDT", "2026-01-01", "BUY", 10.0, 100.0, ctx)

    # Conservation: sum of parts MUST strictly equal total
    assert np.isclose(tb.total_cost_bps, tb.fee_bps + tb.spread_bps + tb.slippage_bps + tb.impact_bps)
    assert np.isclose(tb.total_cost_dollars, tb.fee_dollars + tb.spread_dollars + tb.slippage_dollars + tb.impact_dollars)


# =============================================================================
# 4. Causal Future Mutation Test
# =============================================================================

def test_p3_1f_future_mutation_invariance():
    engine = TransactionCostEngine(CostModelConfig(profile=CostModelProfile.P3_1F_BASE))

    dates = pd.date_range("2026-01-01", periods=80, freq="1h")
    np.random.seed(123)
    p_orig = pd.DataFrame({
        "BTCUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 80)) * 50000.0,
        "ETHUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 80)) * 3000.0
    }, index=dates)
    w_orig = pd.DataFrame({
        "BTCUSDT": [0.5 if i % 2 == 0 else 0.0 for i in range(80)],
        "ETHUSDT": [0.5 if i % 2 == 1 else 0.0 for i in range(80)]
    }, index=dates)

    costs_orig, _ = engine.compute_portfolio_rebalance_costs(p_orig, w_orig)

    # Mutate future bars (from index 50 onward)
    p_mutated = p_orig.copy()
    p_mutated.iloc[50:] = p_mutated.iloc[50:] * 10.0

    costs_mutated, _ = engine.compute_portfolio_rebalance_costs(p_mutated, w_orig)

    assert np.allclose(costs_orig[:48], costs_mutated[:48], atol=1e-8)


# =============================================================================
# 5. Determinism
# =============================================================================

def test_p3_1f_determinism():
    cfg = CostModelConfig(profile=CostModelProfile.P3_1F_BASE)
    e1 = TransactionCostEngine(cfg)
    e2 = TransactionCostEngine(cfg)

    dates = pd.date_range("2026-01-01", periods=30, freq="1h")
    p = pd.DataFrame({"BTCUSDT": np.linspace(50000, 52000, 30)}, index=dates)
    w = pd.DataFrame({"BTCUSDT": [1.0 if i % 2 == 0 else 0.0 for i in range(30)]}, index=dates)

    c1, logs1 = e1.compute_portfolio_rebalance_costs(p, w)
    c2, logs2 = e2.compute_portfolio_rebalance_costs(p, w)

    assert np.array_equal(c1, c2)
    assert [l.to_dict() for l in logs1] == [l.to_dict() for l in logs2]
