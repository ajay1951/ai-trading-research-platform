"""
tests/cross_sectional/test_p3_1_transaction_costs.py
====================================================
P3-1 Validation Test Suite: Advanced Transaction Cost Intelligence Layer.

Validates:
1. Fee calculations & Maker/Taker distinction
2. Spread model & Corwin-Schultz high-low estimation
3. Volatility- and liquidity-adjusted dynamic slippage
4. Square-root market impact monotonicity with trade size
5. Point-in-time liquidity scoring & discrete classification
6. Adverse delay cost calculation
7. Zero double-counting of execution friction components
8. Non-positive order/price rejection
9. Future data mutation & strict zero-lookahead invariance
10. Deterministic bit-for-bit repeatability across executions
"""

import pytest
import numpy as np
import pandas as pd
from evaluation.transaction_costs import (
    TransactionCostEngine,
    CostModelConfig,
    CostModelProfile,
    TradeCostBreakdown,
    LiquidityTier,
    OrderExecutionType,
    FeeModel,
    SpreadModel,
    SlippageModel,
    MarketImpactModel,
    LiquidityModel,
    DelayCostModel,
    SCENARIO_CONFIGS
)


@pytest.fixture
def base_engine():
    cfg = CostModelConfig(profile=CostModelProfile.ADVANCED_BASE)
    return TransactionCostEngine(cfg)


# =============================================================================
# 1. Fee Model Tests
# =============================================================================

def test_fee_model_maker_vs_taker():
    cfg = CostModelConfig(maker_fee_bps=4.0, taker_fee_bps=6.0)
    fee_model = FeeModel(cfg)

    # 10,000 USD notional
    fee_maker_bps, fee_maker_dollars = fee_model.calculate_fee(10_000.0, OrderExecutionType.MAKER)
    fee_taker_bps, fee_taker_dollars = fee_model.calculate_fee(10_000.0, OrderExecutionType.TAKER)

    assert fee_maker_bps == 4.0
    assert fee_maker_dollars == 4.0 # $10,000 * 0.0004 = $4.00
    assert fee_taker_bps == 6.0
    assert fee_taker_dollars == 6.0 # $10,000 * 0.0006 = $6.00


def test_fee_model_zero_notional():
    fee_model = FeeModel(CostModelConfig())
    bps, dollars = fee_model.calculate_fee(0.0)
    assert bps == 0.0
    assert dollars == 0.0


# =============================================================================
# 2. Spread Model Tests & Corwin-Schultz
# =============================================================================

def test_corwin_schultz_spread_estimation():
    cfg = CostModelConfig(profile=CostModelProfile.ADVANCED_BASE, min_spread_bps=1.0, max_spread_bps=50.0)
    spread_model = SpreadModel(cfg)

    # Simulate 2 consecutive bars
    high_prev, low_prev = 101.0, 99.0
    high_now, low_now = 102.0, 100.0

    spread_bps = spread_model.estimate_spread_bps(
        high_now=high_now,
        low_now=low_now,
        high_prev=high_prev,
        low_prev=low_prev,
        realized_vol_24h=0.015,
        rolling_24h_quote_volume=50_000_000.0
    )

    assert 1.0 <= spread_bps <= 50.0

    # Half-spread crossing cost
    half_bps, half_dollars = spread_model.calculate_spread_cost(10_000.0, spread_bps)
    assert np.isclose(half_bps, 0.5 * spread_bps)
    assert np.isclose(half_dollars, 10_000.0 * (half_bps / 10000.0))


def test_spread_model_fixed_profile():
    cfg = CostModelConfig(profile=CostModelProfile.FIXED_12BPS)
    spread_model = SpreadModel(cfg)
    spread_bps = spread_model.estimate_spread_bps(105.0, 95.0, 104.0, 96.0, 0.02, 10_000_000.0)
    assert spread_bps == 0.0


# =============================================================================
# 3. Dynamic Slippage & Volatility Scaling
# =============================================================================

def test_slippage_model_volatility_and_liquidity_scaling():
    cfg = CostModelConfig(base_slippage_bps=2.0, slippage_vol_beta=0.5, slippage_liq_beta=0.5)
    slip_model = SlippageModel(cfg)

    # Normal conditions
    bps_norm, dol_norm = slip_model.calculate_slippage(
        notional=10_000.0, realized_vol_24h=0.015, rolling_24h_quote_volume=50_000_000.0,
        benchmark_vol=0.015, benchmark_volume=50_000_000.0
    )

    # High volatility condition (3.0% vol = 2x normal)
    bps_high_vol, dol_high_vol = slip_model.calculate_slippage(
        notional=10_000.0, realized_vol_24h=0.030, rolling_24h_quote_volume=50_000_000.0,
        benchmark_vol=0.015, benchmark_volume=50_000_000.0
    )

    # Low liquidity condition ($10M = 0.2x normal)
    bps_low_liq, dol_low_liq = slip_model.calculate_slippage(
        notional=10_000.0, realized_vol_24h=0.015, rolling_24h_quote_volume=10_000_000.0,
        benchmark_vol=0.015, benchmark_volume=50_000_000.0
    )

    assert bps_norm == 2.0
    assert bps_high_vol > bps_norm
    assert bps_low_liq > bps_norm
    assert dol_high_vol > dol_norm


# =============================================================================
# 4. Market Impact & Monotonicity
# =============================================================================

def test_market_impact_monotonicity():
    cfg = CostModelConfig(impact_gamma=0.10)
    impact_model = MarketImpactModel(cfg)

    notional_small = 1_000.0
    notional_med = 50_000.0
    notional_large = 500_000.0

    vol = 0.02
    quote_vol = 10_000_000.0

    bps_s, dol_s, p_s = impact_model.calculate_market_impact(notional_small, vol, quote_vol)
    bps_m, dol_m, p_m = impact_model.calculate_market_impact(notional_med, vol, quote_vol)
    bps_l, dol_l, p_l = impact_model.calculate_market_impact(notional_large, vol, quote_vol)

    # Monotonicity: larger trades must incur non-decreasing impact in bps and total dollars
    assert bps_s < bps_m < bps_l
    assert dol_s < dol_m < dol_l
    assert p_s < p_m < p_l


# =============================================================================
# 5. Liquidity Classification
# =============================================================================

def test_liquidity_classification():
    score_btc, tier_btc = LiquidityModel.evaluate_liquidity(500_000_000.0, 0.01)
    score_sol, tier_sol = LiquidityModel.evaluate_liquidity(60_000_000.0, 0.015)
    score_near, tier_near = LiquidityModel.evaluate_liquidity(12_000_000.0, 0.02)
    score_illiquid, tier_illiquid = LiquidityModel.evaluate_liquidity(2_000_000.0, 0.04)

    assert tier_btc == LiquidityTier.HIGH
    assert tier_sol == LiquidityTier.MEDIUM
    assert tier_near == LiquidityTier.LOW
    assert tier_illiquid == LiquidityTier.EXTREME
    assert score_btc > score_sol > score_near > score_illiquid


# =============================================================================
# 6. Delay Cost Model
# =============================================================================

def test_delay_cost_calculation():
    cfg = CostModelConfig(include_delay_cost=True)
    delay_model = DelayCostModel(cfg)

    # Adverse Buy: Price rises from 100 to 100.50 (50 bps)
    bps_buy, dol_buy = delay_model.calculate_delay_cost(10_000.0, decision_price=100.0, fill_price=100.50, side="BUY")
    assert np.isclose(bps_buy, 50.0)
    assert np.isclose(dol_buy, 50.0)

    # Favorable Buy: Price drops from 100 to 99.50 -> 0 adverse delay cost
    bps_fav, dol_fav = delay_model.calculate_delay_cost(10_000.0, decision_price=100.0, fill_price=99.50, side="BUY")
    assert bps_fav == 0.0
    assert dol_fav == 0.0


# =============================================================================
# 7. Unified Engine & No Double-Counting
# =============================================================================

def test_engine_cost_decomposition_and_no_double_counting(base_engine):
    ctx = {
        "high": 50100.0,
        "low": 49900.0,
        "high_prev": 50050.0,
        "low_prev": 49850.0,
        "realized_vol_24h": 0.015,
        "rolling_24h_quote_volume": 100_000_000.0,
        "fill_price": 50010.0
    }

    tb = base_engine.estimate_trade_cost(
        symbol="BTCUSDT",
        timestamp="2026-01-01 00:00:00",
        side="BUY",
        quantity=0.2,
        reference_price=50000.0,
        market_context=ctx
    )

    # Verify no double counting: Total = Fee + Spread + Slippage + Impact + Delay
    assert np.isclose(tb.total_cost_bps, tb.fee_bps + tb.spread_bps + tb.slippage_bps + tb.impact_bps + tb.delay_bps)
    assert np.isclose(tb.total_cost_dollars, tb.fee_dollars + tb.spread_dollars + tb.slippage_dollars + tb.impact_dollars + tb.delay_dollars)
    assert tb.notional == 10_000.0
    assert tb.total_cost_dollars > 0.0


def test_invalid_parameters_rejection(base_engine):
    with pytest.raises(ValueError):
        base_engine.estimate_trade_cost("BTCUSDT", "2026-01-01", "BUY", quantity=0.0, reference_price=50000.0, market_context={})

    with pytest.raises(ValueError):
        base_engine.estimate_trade_cost("BTCUSDT", "2026-01-01", "BUY", quantity=1.0, reference_price=-100.0, market_context={})


# =============================================================================
# 8. Future Data Mutation & Zero-Lookahead Invariant
# =============================================================================

def test_future_data_mutation_invariance():
    """
    Causality Integrity Test:
    Mutating future prices or volume AFTER bar t MUST NOT alter the cost computed at bar t.
    """
    engine = TransactionCostEngine(CostModelConfig(profile=CostModelProfile.ADVANCED_BASE))

    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    np.random.seed(42)
    p_orig = pd.DataFrame({
        "BTCUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 100)) * 50000.0,
        "ETHUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 100)) * 3000.0
    }, index=dates)

    w_orig = pd.DataFrame({
        "BTCUSDT": [0.5 if i % 2 == 0 else 0.0 for i in range(100)],
        "ETHUSDT": [0.5 if i % 2 == 1 else 0.0 for i in range(100)]
    }, index=dates)

    costs_orig, _ = engine.compute_portfolio_rebalance_costs(p_orig, w_orig)

    # Mutate future bars (from index 60 onward)
    p_mutated = p_orig.copy()
    p_mutated.iloc[60:] = p_mutated.iloc[60:] * 5.0 # 500% future price spike

    costs_mutated, _ = engine.compute_portfolio_rebalance_costs(p_mutated, w_orig)

    # Historical costs for bars 0..58 must remain strictly identical
    assert np.allclose(costs_orig[:58], costs_mutated[:58], atol=1e-8)


# =============================================================================
# 9. Determinism Across Successive Executions
# =============================================================================

def test_cost_engine_determinism():
    cfg = CostModelConfig(profile=CostModelProfile.ADVANCED_BASE)
    engine1 = TransactionCostEngine(cfg)
    engine2 = TransactionCostEngine(cfg)

    dates = pd.date_range("2026-01-01", periods=50, freq="1h")
    prices = pd.DataFrame({"BTCUSDT": np.linspace(50000, 55000, 50)}, index=dates)
    weights = pd.DataFrame({"BTCUSDT": [1.0 if i % 4 == 0 else 0.0 for i in range(50)]}, index=dates)

    c1, logs1 = engine1.compute_portfolio_rebalance_costs(prices, weights)
    c2, logs2 = engine2.compute_portfolio_rebalance_costs(prices, weights)

    assert np.array_equal(c1, c2)
    assert len(logs1) == len(logs2)
    assert [l.to_dict() for l in logs1] == [l.to_dict() for l in logs2]


# =============================================================================
# 10. Scenario Config Hierarchy & Monotonicity
# =============================================================================

def test_scenario_configs_hierarchy():
    opt = SCENARIO_CONFIGS[CostModelProfile.ADVANCED_OPTIMISTIC]
    base = SCENARIO_CONFIGS[CostModelProfile.ADVANCED_BASE]
    con = SCENARIO_CONFIGS[CostModelProfile.ADVANCED_CONSERVATIVE]
    str_cfg = SCENARIO_CONFIGS[CostModelProfile.ADVANCED_STRESSED]

    # Monotonic progression in assumptions
    assert opt.maker_fee_bps < base.maker_fee_bps < con.maker_fee_bps < str_cfg.maker_fee_bps
    assert opt.taker_fee_bps < base.taker_fee_bps < con.taker_fee_bps < str_cfg.taker_fee_bps
    assert opt.base_slippage_bps < base.base_slippage_bps < con.base_slippage_bps < str_cfg.base_slippage_bps
    assert opt.impact_gamma < base.impact_gamma < con.impact_gamma < str_cfg.impact_gamma


# =============================================================================
# 11. Partial Rebalance Turnover Cost
# =============================================================================

def test_partial_rebalance_turnover_proportionality():
    engine = TransactionCostEngine(CostModelConfig(profile=CostModelProfile.FIXED_12BPS))
    dates = pd.date_range("2026-01-01", periods=3, freq="1h")
    prices = pd.DataFrame({"BTCUSDT": [100.0, 100.0, 100.0]}, index=dates)
    
    # Weight changes from 0.0 -> 0.5 (dw = 0.5) vs 0.0 -> 1.0 (dw = 1.0)
    w_half = pd.DataFrame({"BTCUSDT": [0.5, 0.5, 0.5]}, index=dates)
    w_full = pd.DataFrame({"BTCUSDT": [1.0, 1.0, 1.0]}, index=dates)

    costs_half, _ = engine.compute_portfolio_rebalance_costs(prices, w_half, portfolio_capital=10_000.0)
    costs_full, _ = engine.compute_portfolio_rebalance_costs(prices, w_full, portfolio_capital=10_000.0)

    # Cost of 50% rebalance must be exactly half of 100% rebalance
    assert np.isclose(costs_half[0] * 2.0, costs_full[0])

