"""
Unit & Regression Tests: Cross-Sectional Rebalance Frequency, Turnover & Rank Persistence
========================================================================================
Validates scheduling intervals (1h, 4h, 12h, 24h), turnover accounting,
friction scaling, rank persistence metrics, and zero future lookahead.
"""

import pytest
import numpy as np
import pandas as pd
from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio


def test_rebalance_frequency_scheduling():
    """
    Verifies that apply_rebalance_frequency updates weights only on scheduled intervals
    and holds weights constant in intermediate bars.
    """
    timestamps = pd.date_range("2026-01-01", periods=12, freq="1h")
    # Alternating weights every hour: Bar 0 -> A=1, Bar 1 -> B=1, Bar 2 -> A=1, ...
    raw_weights = pd.DataFrame({
        "A": [1.0 if i % 2 == 0 else 0.0 for i in range(12)],
        "B": [0.0 if i % 2 == 0 else 1.0 for i in range(12)]
    }, index=timestamps)

    # 1. Interval = 4 hours: Should update only at index 0, 4, 8
    sched_4h = CrossSectionalRanker.apply_rebalance_frequency(raw_weights, interval_bars=4)
    # Bars 0, 1, 2, 3 should all match Bar 0 (A=1.0, B=0.0)
    for i in range(4):
        assert sched_4h.iloc[i]["A"] == 1.0
        assert sched_4h.iloc[i]["B"] == 0.0

    # Bars 4, 5, 6, 7 should all match Bar 4 (A=1.0, B=0.0)
    for i in range(4, 8):
        assert sched_4h.iloc[i]["A"] == 1.0

    # 2. Interval = 1 hour (Default): Should match raw weights identically
    sched_1h = CrossSectionalRanker.apply_rebalance_frequency(raw_weights, interval_bars=1)
    pd.testing.assert_frame_equal(sched_1h, raw_weights)


def test_turnover_reduction_under_slower_rebalancing():
    """
    Verifies that shifting from 1h rebalancing to 4h and 24h rebalancing strictly reduces turnover
    and total transaction costs in volatile ranking signals.
    """
    timestamps = pd.date_range("2026-01-01", periods=96, freq="1h")
    prices_df = pd.DataFrame({
        "A": np.full(96, 100.0),
        "B": np.full(96, 100.0)
    }, index=timestamps)

    # Shifting signal: Flips every 3 bars (not aligned with 4 or 24)
    raw_weights = pd.DataFrame({
        "A": [1.0 if (i // 3) % 2 == 0 else 0.0 for i in range(96)],
        "B": [0.0 if (i // 3) % 2 == 0 else 1.0 for i in range(96)]
    }, index=timestamps)

    # 1H Rebalance (samples every bar -> 32 position flips)
    w_1h = CrossSectionalRanker.apply_rebalance_frequency(raw_weights, interval_bars=1)
    res_1h = simulate_cross_sectional_portfolio(prices_df, w_1h)

    # 4H Rebalance (samples every 4 bars -> fewer flips)
    w_4h = CrossSectionalRanker.apply_rebalance_frequency(raw_weights, interval_bars=4)
    res_4h = simulate_cross_sectional_portfolio(prices_df, w_4h)

    # 24H Rebalance (samples every 24 bars -> 4 samples total)
    w_24h = CrossSectionalRanker.apply_rebalance_frequency(raw_weights, interval_bars=24)
    res_24h = simulate_cross_sectional_portfolio(prices_df, w_24h)

    assert res_1h["total_turnover"] > res_4h["total_turnover"]
    assert res_4h["total_turnover"] > res_24h["total_turnover"]
    assert res_1h["total_costs_pct"] > res_4h["total_costs_pct"]
    assert res_4h["total_costs_pct"] > res_24h["total_costs_pct"]


def test_holding_period_calculation_accuracy():
    """
    Verifies that average and max holding periods scale directly with rebalance interval.
    """
    timestamps = pd.date_range("2026-01-01", periods=25, freq="1h")
    prices_df = pd.DataFrame({
        "A": np.full(25, 100.0),
        "B": np.full(25, 100.0)
    }, index=timestamps)

    # Asset A held for first 12 step bars, Asset B held for next 12 step bars
    weights = pd.DataFrame({
        "A": [1.0 if i < 12 else 0.0 for i in range(25)],
        "B": [0.0 if i >= 12 else 0.0 for i in range(25)]
    }, index=timestamps)
    weights["B"] = [1.0 if (12 <= i < 24) else 0.0 for i in range(25)]

    res = simulate_cross_sectional_portfolio(prices_df, weights)
    assert res["max_holding_period_hours"] == 12
    assert np.isclose(res["avg_holding_period_hours"], 12.0, atol=0.5)


def test_rank_persistence_metrics():
    """
    Verifies that compute_rank_persistence calculates lag correlations and Jaccard overlaps correctly.
    """
    timestamps = pd.date_range("2026-01-01", periods=50, freq="1h")
    
    # 1. Perfectly static predictions across time -> Autocorrelation = 1.0, Overlap = 1.0
    static_preds = pd.DataFrame({
        "A": np.full(50, 0.9),
        "B": np.full(50, 0.8),
        "C": np.full(50, 0.5),
        "D": np.full(50, 0.2),
        "E": np.full(50, 0.1)
    }, index=timestamps)

    res_static = CrossSectionalRanker.compute_rank_persistence(static_preds, top_n=2, bottom_n=2)
    assert np.isclose(res_static["rank_corr_1h"], 1.0)
    assert np.isclose(res_static["rank_corr_24h"], 1.0)
    assert np.isclose(res_static["top_n_persistence_1h"], 1.0)
    assert res_static["top_n_transitions_count"] == 0

    # 2. Random noisy predictions -> Jaccard overlap should be significantly lower
    np.random.seed(42)
    random_preds = pd.DataFrame(np.random.randn(50, 5), index=timestamps, columns=["A", "B", "C", "D", "E"])
    res_rand = CrossSectionalRanker.compute_rank_persistence(random_preds, top_n=2, bottom_n=2)
    assert res_rand["top_n_persistence_24h"] < 0.80
    assert res_rand["top_n_transitions_count"] > 0


def test_future_price_mutation_invariance_in_rebalance():
    """
    Future Mutation / Causality test:
    Asserts that mutating future prices at bar t > 10 has ZERO impact on
    weights or portfolio allocation decisions at bars t <= 10.
    """
    timestamps = pd.date_range("2026-01-01", periods=20, freq="1h")
    preds = pd.DataFrame({
        "A": np.linspace(0.8, 0.4, 20),
        "B": np.linspace(0.2, 0.9, 20),
        "C": np.full(20, 0.5),
        "D": np.full(20, 0.3)
    }, index=timestamps)

    raw_w = pd.DataFrame([
        CrossSectionalRanker.rank_assets(preds.iloc[i].to_dict(), top_n=2, bottom_n=2)
        for i in range(len(preds))
    ], index=timestamps)

    w_4h_original = CrossSectionalRanker.apply_rebalance_frequency(raw_w, interval_bars=4)

    # Mutate future predictions after bar 10
    preds_mutated = preds.copy()
    preds_mutated.iloc[11:, :] = np.random.randn(9, 4)

    raw_w_mutated = pd.DataFrame([
        CrossSectionalRanker.rank_assets(preds_mutated.iloc[i].to_dict(), top_n=2, bottom_n=2)
        for i in range(len(preds_mutated))
    ], index=timestamps)

    w_4h_mutated = CrossSectionalRanker.apply_rebalance_frequency(raw_w_mutated, interval_bars=4)

    # Historical decisions at bars 0..10 MUST be bitwise identical
    pd.testing.assert_frame_equal(w_4h_original.iloc[:11], w_4h_mutated.iloc[:11])
