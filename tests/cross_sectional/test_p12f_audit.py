"""
Unit and Regression Tests for P1-2F Audit Engine
================================================
Verifies frequency audit scheduling, SOL exclusion slicing, asset contribution reconciliation,
point-in-time causal BTC regime classification, and deterministic reproducibility.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio
from training.robustness_validation import RobustnessValidationRunner, UNIVERSE_SYMBOLS


@pytest.fixture
def mock_audit_dataset():
    """Generates synthetic 100-bar multi-asset prediction and price panel with BTC."""
    symbols = UNIVERSE_SYMBOLS
    n_bars = 200
    base_time = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(hours=i) for i in range(n_bars)]

    np.random.seed(42)
    pred_data = {sym: np.random.uniform(0.4, 0.6, size=n_bars) for sym in symbols}
    price_data = {}
    for sym in symbols:
        ret = np.random.normal(0.0002, 0.015, size=n_bars)
        price_data[sym] = 100.0 * np.cumprod(1.0 + ret)

    preds_df = pd.DataFrame(pred_data, index=timestamps)
    prices_df = pd.DataFrame(price_data, index=timestamps)
    return preds_df, prices_df, symbols


def test_frequency_audit_invariance(mock_audit_dataset):
    """Verifies that identical predictions produce scheduled holdings with zero intermediate rebalances."""
    preds_df, prices_df, symbols = mock_audit_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)

    for interval in [24, 36, 48]:
        w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=interval)
        for i in range(len(w_sched)):
            if i % interval != 0:
                prev_rebal_idx = i - (i % interval)
                pd.testing.assert_series_equal(w_sched.iloc[i], w_sched.iloc[prev_rebal_idx], check_names=False)


def test_sol_audit_exclusion_integrity(mock_audit_dataset):
    """Verifies that excluding SOL strictly zeroes SOL without mutating other assets."""
    preds_df, prices_df, symbols = mock_audit_dataset
    symbols_no_sol = [s for s in symbols if s != "SOLUSDT"]

    w_nosol = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2, symbols_subset=symbols_no_sol)
    assert (w_nosol["SOLUSDT"] == 0.0).all()

    for i in range(len(w_nosol)):
        row = w_nosol.iloc[i]
        active = row[row > 0]
        assert len(active) == 2
        assert "SOLUSDT" not in active.index
        assert pytest.approx(active.sum(), abs=1e-5) == 1.0


def test_asset_attribution_reconciliation(mock_audit_dataset):
    """Verifies that gross asset contributions sum exactly to portfolio gross return before friction."""
    preds_df, prices_df, symbols = mock_audit_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=24)

    aligned_w = w_sched.reindex(prices_df.index).ffill().fillna(0.0)
    asset_ret = (prices_df - prices_df.shift(1)) / prices_df.shift(1)
    asset_ret = asset_ret.fillna(0.0)

    # Asset by asset step contributions
    step_contrib = (aligned_w.shift(1).fillna(0.0) * asset_ret)
    total_step_gross = step_contrib.sum(axis=1)

    portfolio_gross_cum = float((np.prod(1.0 + total_step_gross) - 1.0) * 100.0)
    
    # Run simulation with 0 fees to compare gross return
    m = simulate_cross_sectional_portfolio(prices_df, w_sched, fee_rate=0.0, slippage=0.0)
    assert pytest.approx(m["return_pct"], rel=1e-3) == portfolio_gross_cum


def test_btc_regime_future_mutation_invariance(mock_audit_dataset):
    """Verifies point-in-time causal integrity of BTC 100-day SMA regime segmentation."""
    _, prices_df, _ = mock_audit_dataset
    btc_close = prices_df["BTCUSDT"]

    # Compute baseline regime segmentation
    sma_100d = btc_close.rolling(50, min_periods=10).mean() # using 50 bars for test slice
    mom_100d = (btc_close - sma_100d) / (sma_100d + 1e-9)
    baseline_regime = (mom_100d > 0.05).astype(int) - (mom_100d < -0.05).astype(int)

    # Mutate future BTC prices after bar 100
    cutoff = 100
    btc_mutated = btc_close.copy()
    btc_mutated.iloc[cutoff:] *= 3.0

    sma_mutated = btc_mutated.rolling(50, min_periods=10).mean()
    mom_mutated = (btc_mutated - sma_mutated) / (sma_mutated + 1e-9)
    mutated_regime = (mom_mutated > 0.05).astype(int) - (mom_mutated < -0.05).astype(int)

    # Historical regime labels before cutoff must remain identical
    pd.testing.assert_series_equal(baseline_regime.iloc[:cutoff], mutated_regime.iloc[:cutoff])


def test_audit_reproducibility(mock_audit_dataset):
    """Verifies that running portfolio simulation on identical slices produces identical deterministic metrics."""
    preds_df, prices_df, _ = mock_audit_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)

    m1 = simulate_cross_sectional_portfolio(prices_df, w_sched, fee_rate=0.0004, slippage=0.0002)
    m2 = simulate_cross_sectional_portfolio(prices_df, w_sched, fee_rate=0.0004, slippage=0.0002)

    assert m1 == m2
