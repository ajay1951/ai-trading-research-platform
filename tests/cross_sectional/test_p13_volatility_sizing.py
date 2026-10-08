"""
Unit and Regression Tests for P1-3 Volatility-Aware Position Sizing Engine
=========================================================================
Verifies:
1. test_inverse_vol_weights_sum_to_one
2. test_inverse_vol_weights_are_deterministic
3. test_volatility_uses_only_past_data
4. test_volatility_future_mutation_invariance
5. test_no_intermediate_rebalances
6. test_ranking_is_unchanged_by_volatility_sizing
7. test_iv_cap_respects_25_75_bounds
8. test_weight_allocation_preserves_full_exposure
9. test_asset_attribution_reconciliation
10. test_sol_exclusion_integrity
11. test_p13_reproducibility
12. Edge case handling (zero volatility, NaN/missing data, identical volatilities).
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio
from evaluation.volatility_sizing import VolatilitySizingEngine
from training.robustness_validation import RobustnessValidationRunner, UNIVERSE_SYMBOLS


@pytest.fixture
def mock_p13_dataset():
    """Generates synthetic multi-asset price and prediction panel."""
    symbols = UNIVERSE_SYMBOLS
    n_bars = 250
    base_time = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(hours=i) for i in range(n_bars)]

    np.random.seed(42)
    pred_data = {sym: np.random.uniform(0.4, 0.6, size=n_bars) for sym in symbols}
    price_data = {}
    for i, sym in enumerate(symbols):
        # assign different baseline volatilities
        vol = 0.005 + (i * 0.002)
        ret = np.random.normal(0.0002, vol, size=n_bars)
        price_data[sym] = 100.0 * np.cumprod(1.0 + ret)

    preds_df = pd.DataFrame(pred_data, index=timestamps)
    prices_df = pd.DataFrame(price_data, index=timestamps)
    return preds_df, prices_df, symbols


def test_inverse_vol_weights_sum_to_one(mock_p13_dataset):
    """Verifies that normalized inverse volatility weights sum to 100% across active assets."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_iv = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="inverse_vol")

    for i in range(len(w_iv)):
        row = w_iv.iloc[i]
        active = row[row > 0]
        if len(active) > 0:
            assert pytest.approx(active.sum(), abs=1e-5) == 1.0


def test_inverse_vol_weights_are_deterministic(mock_p13_dataset):
    """Verifies that identical price and prediction inputs produce deterministic weights."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol1 = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    vol2 = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)

    w1 = VolatilitySizingEngine.size_portfolio(w_raw, vol1, mode="inverse_vol")
    w2 = VolatilitySizingEngine.size_portfolio(w_raw, vol2, mode="inverse_vol")
    pd.testing.assert_frame_equal(w1, w2)


def test_volatility_uses_only_past_data(mock_p13_dataset):
    """Verifies that volatility at bar t depends only on prices up to bar t."""
    _, prices_df, _ = mock_p13_dataset
    t_idx = 180
    vol_full = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    
    prices_sliced = prices_df.iloc[: t_idx + 1]
    vol_sliced = VolatilitySizingEngine.compute_historical_volatility(prices_sliced, window=168)

    pd.testing.assert_series_equal(vol_full.iloc[t_idx], vol_sliced.iloc[t_idx])


def test_volatility_future_mutation_invariance(mock_p13_dataset):
    """Verifies that mutating prices after bar 180 leaves volatility and sized weights before bar 180 unchanged."""
    preds_df, prices_df, _ = mock_p13_dataset
    cutoff = 180
    
    vol_orig = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_orig = VolatilitySizingEngine.size_portfolio(w_raw, vol_orig, mode="inverse_vol")

    # Mutate future prices
    prices_mut = prices_df.copy()
    prices_mut.iloc[cutoff:] *= 3.5
    vol_mut = VolatilitySizingEngine.compute_historical_volatility(prices_mut, window=168)
    w_mut = VolatilitySizingEngine.size_portfolio(w_raw, vol_mut, mode="inverse_vol")

    # All weights and volatilities prior to cutoff must be byte-for-byte identical
    pd.testing.assert_frame_equal(vol_orig.iloc[:cutoff], vol_mut.iloc[:cutoff])
    pd.testing.assert_frame_equal(w_orig.iloc[:cutoff], w_mut.iloc[:cutoff])


def test_no_intermediate_rebalances(mock_p13_dataset):
    """Verifies that applying 48H frequency scheduling preserves constant weights during intermediate bars."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_iv = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="inverse_vol")
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_iv, interval_bars=48)

    for i in range(len(w_sched)):
        if i % 48 != 0:
            prev_rebal_idx = i - (i % 48)
            pd.testing.assert_series_equal(w_sched.iloc[i], w_sched.iloc[prev_rebal_idx], check_names=False)


def test_ranking_is_unchanged_by_volatility_sizing(mock_p13_dataset):
    """Verifies that active selected assets in Top 2 are strictly identical between Equal Weight and Inverse Volatility."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_iv = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="inverse_vol")

    for i in range(len(w_raw)):
        active_raw = set(w_raw.iloc[i][w_raw.iloc[i] > 0].index)
        active_iv = set(w_iv.iloc[i][w_iv.iloc[i] > 0].index)
        assert active_raw == active_iv


def test_iv_cap_respects_25_75_bounds(mock_p13_dataset):
    """Verifies that Volatility-Capped sizing enforces [0.25, 0.75] weight bounds on all active assets."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_cap = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="iv_capped", min_weight_cap=0.25, max_weight_cap=0.75)

    for i in range(len(w_cap)):
        active = w_cap.iloc[i][w_cap.iloc[i] > 0]
        if len(active) == 2:
            for w in active:
                assert 0.2499 <= w <= 0.7501
            assert pytest.approx(active.sum(), abs=1e-5) == 1.0


def test_weight_allocation_preserves_full_exposure(mock_p13_dataset):
    """Verifies that portfolio always maintains 100% total invested capital exposure across all modes."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)

    for mode in ["equal", "inverse_vol", "iv_capped"]:
        w_sized = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode=mode)
        total_exp = w_sized.sum(axis=1)
        assert np.allclose(total_exp.values, 1.0, atol=1e-5)


def test_asset_attribution_reconciliation(mock_p13_dataset):
    """Verifies that individual asset gross step contributions sum exactly to portfolio gross return."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_iv = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="inverse_vol")
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_iv, interval_bars=48)

    aligned_w = w_sched.reindex(prices_df.index).ffill().fillna(0.0)
    asset_ret = ((prices_df - prices_df.shift(1)) / prices_df.shift(1)).fillna(0.0)

    step_contrib = (aligned_w.shift(1).fillna(0.0) * asset_ret).sum(axis=1)
    port_cum_gross = float((np.prod(1.0 + step_contrib) - 1.0) * 100.0)

    m = simulate_cross_sectional_portfolio(prices_df, w_sched, fee_rate=0.0, slippage=0.0)
    assert pytest.approx(m["return_pct"], rel=1e-3) == port_cum_gross


def test_sol_exclusion_integrity(mock_p13_dataset):
    """Verifies that excluding SOL strictly allocates 0.0 to SOL without affecting sizing normalization."""
    preds_df, prices_df, symbols = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    symbols_no_sol = [s for s in symbols if s != "SOLUSDT"]

    w_nosol_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2, symbols_subset=symbols_no_sol)
    w_nosol_iv = VolatilitySizingEngine.size_portfolio(w_nosol_raw, vol_panel, mode="inverse_vol")

    assert (w_nosol_iv["SOLUSDT"] == 0.0).all()
    for i in range(len(w_nosol_iv)):
        active = w_nosol_iv.iloc[i][w_nosol_iv.iloc[i] > 0]
        assert len(active) == 2
        assert "SOLUSDT" not in active.index
        assert pytest.approx(active.sum(), abs=1e-5) == 1.0


def test_edge_cases_volatility_handling(mock_p13_dataset):
    """Verifies fallback to equal weights on zero, NaN, missing, or identical volatilities."""
    preds_df, prices_df, _ = mock_p13_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    
    # 1. Identical volatilities -> 50% / 50%
    vol_identical = pd.DataFrame(0.50, index=prices_df.index, columns=prices_df.columns)
    w_ident = VolatilitySizingEngine.size_portfolio(w_raw, vol_identical, mode="inverse_vol")
    for i in range(len(w_ident)):
        active = w_ident.iloc[i][w_ident.iloc[i] > 0]
        if len(active) == 2:
            assert pytest.approx(active.iloc[0], abs=1e-5) == 0.50
            assert pytest.approx(active.iloc[1], abs=1e-5) == 0.50

    # 2. NaN volatility -> fallback to 50% / 50%
    vol_nan = pd.DataFrame(np.nan, index=prices_df.index, columns=prices_df.columns)
    w_nan = VolatilitySizingEngine.size_portfolio(w_raw, vol_nan, mode="inverse_vol")
    for i in range(len(w_nan)):
        active = w_nan.iloc[i][w_nan.iloc[i] > 0]
        if len(active) == 2:
            assert pytest.approx(active.iloc[0], abs=1e-5) == 0.50
            assert pytest.approx(active.iloc[1], abs=1e-5) == 0.50

    # 3. Zero volatility -> fallback to 50% / 50%
    vol_zero = pd.DataFrame(0.0, index=prices_df.index, columns=prices_df.columns)
    w_zero = VolatilitySizingEngine.size_portfolio(w_raw, vol_zero, mode="inverse_vol")
    for i in range(len(w_zero)):
        active = w_zero.iloc[i][w_zero.iloc[i] > 0]
        if len(active) == 2:
            assert pytest.approx(active.iloc[0], abs=1e-5) == 0.50
            assert pytest.approx(active.iloc[1], abs=1e-5) == 0.50


def test_p13_reproducibility(mock_p13_dataset):
    """Verifies that running portfolio simulation on identical data produces identical deterministic metrics."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_iv = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="inverse_vol")
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_iv, interval_bars=48)

    m1 = simulate_cross_sectional_portfolio(prices_df, w_sched, fee_rate=0.0004, slippage=0.0002)
    m2 = simulate_cross_sectional_portfolio(prices_df, w_sched, fee_rate=0.0004, slippage=0.0002)
    assert m1 == m2


# =========================================================================
# TASK 4: Explicit Cap Regression Tests (Tests A - G)
# =========================================================================

def test_iv_cap_test_a_upper_bound_enforcement():
    """Test A: Construct extreme volatility skew (vol_A = 0.10, vol_B = 0.90 -> raw_A = 90%), verify final_weight <= 0.75."""
    t_idx = pd.date_range("2025-01-01", periods=5, freq="h", tz="UTC")
    symbols = ["ASSET_LOW_VOL", "ASSET_HIGH_VOL"]
    preds_df = pd.DataFrame({"ASSET_LOW_VOL": [0.9, 0.9, 0.9, 0.9, 0.9], "ASSET_HIGH_VOL": [0.8, 0.8, 0.8, 0.8, 0.8]}, index=t_idx)
    # Asset A has vol=0.10, Asset B has vol=0.90. Raw IV weights: A=90%, B=10%
    vol_df = pd.DataFrame({"ASSET_LOW_VOL": [0.10]*5, "ASSET_HIGH_VOL": [0.90]*5}, index=t_idx)
    
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_cap = VolatilitySizingEngine.size_portfolio(w_raw, vol_df, mode="iv_capped", min_weight_cap=0.25, max_weight_cap=0.75)
    
    for i in range(len(w_cap)):
        assert w_cap.iloc[i]["ASSET_LOW_VOL"] <= 0.75 + 1e-6
        assert pytest.approx(w_cap.iloc[i]["ASSET_LOW_VOL"], abs=1e-5) == 0.75


def test_iv_cap_test_b_lower_bound_enforcement():
    """Test B: Construct extreme volatility skew, verify final_weight >= 0.25 for high vol asset."""
    t_idx = pd.date_range("2025-01-01", periods=5, freq="h", tz="UTC")
    symbols = ["ASSET_LOW_VOL", "ASSET_HIGH_VOL"]
    preds_df = pd.DataFrame({"ASSET_LOW_VOL": [0.9, 0.9, 0.9, 0.9, 0.9], "ASSET_HIGH_VOL": [0.8, 0.8, 0.8, 0.8, 0.8]}, index=t_idx)
    vol_df = pd.DataFrame({"ASSET_LOW_VOL": [0.10]*5, "ASSET_HIGH_VOL": [0.90]*5}, index=t_idx)
    
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_cap = VolatilitySizingEngine.size_portfolio(w_raw, vol_df, mode="iv_capped", min_weight_cap=0.25, max_weight_cap=0.75)
    
    for i in range(len(w_cap)):
        assert w_cap.iloc[i]["ASSET_HIGH_VOL"] >= 0.25 - 1e-6
        assert pytest.approx(w_cap.iloc[i]["ASSET_HIGH_VOL"], abs=1e-5) == 0.25


def test_iv_cap_test_c_weight_sum_unity():
    """Test C: Construct arbitrary volatility pairings and verify sum(final_weights) == 1.0 within float tolerance."""
    t_idx = pd.date_range("2025-01-01", periods=10, freq="h", tz="UTC")
    preds_df = pd.DataFrame({"SYM1": [0.9]*10, "SYM2": [0.8]*10}, index=t_idx)
    np.random.seed(123)
    vol1 = np.random.uniform(0.01, 2.0, size=10)
    vol2 = np.random.uniform(0.01, 2.0, size=10)
    vol_df = pd.DataFrame({"SYM1": vol1, "SYM2": vol2}, index=t_idx)
    
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_cap = VolatilitySizingEngine.size_portfolio(w_raw, vol_df, mode="iv_capped", min_weight_cap=0.25, max_weight_cap=0.75)
    
    sums = w_cap.sum(axis=1)
    assert np.allclose(sums.values, 1.0, atol=1e-6)


def test_iv_cap_test_d_reporting_consistency(mock_p13_dataset):
    """Test D: Verify reported max/min final weights match the actual maximum/minimum weights in portfolio simulation."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_cap = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="iv_capped", min_weight_cap=0.25, max_weight_cap=0.75)
    
    diag = VolatilitySizingEngine.compute_cap_diagnostics(w_raw, vol_panel, min_weight_cap=0.25, max_weight_cap=0.75)
    
    # Calculate actual maximum and minimum active weights from w_cap
    active_weights = w_cap.values[w_cap.values > 0]
    actual_max_final_pct = round(float(np.max(active_weights) * 100.0), 2)
    actual_min_final_pct = round(float(np.min(active_weights) * 100.0), 2)
    
    assert diag["max_final_weight_pct"] == actual_max_final_pct
    assert diag["min_final_weight_pct"] == actual_min_final_pct
    assert diag["max_final_weight_pct"] <= 75.0 + 1e-4
    assert diag["min_final_weight_pct"] >= 25.0 - 1e-4


def test_iv_cap_test_e_raw_vs_final_weights_distinction():
    """Test E: Verify that raw IV weights can exceed 75% (e.g. 85%), while final IV-Cap weights strictly cannot."""
    t_idx = pd.date_range("2025-01-01", periods=2, freq="h", tz="UTC")
    preds_df = pd.DataFrame({"SYM_A": [0.9, 0.9], "SYM_B": [0.8, 0.8]}, index=t_idx)
    # Vol A = 0.15, Vol B = 0.85 -> Raw A = 85.0%, Raw B = 15.0%
    vol_df = pd.DataFrame({"SYM_A": [0.15, 0.15], "SYM_B": [0.85, 0.85]}, index=t_idx)
    
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_iv = VolatilitySizingEngine.size_portfolio(w_raw, vol_df, mode="inverse_vol")
    w_cap = VolatilitySizingEngine.size_portfolio(w_raw, vol_df, mode="iv_capped", min_weight_cap=0.25, max_weight_cap=0.75)
    
    assert w_iv.iloc[0]["SYM_A"] > 0.75 # Raw exceeds 75%
    assert w_iv.iloc[0]["SYM_B"] < 0.25 # Raw below 25%
    assert pytest.approx(w_cap.iloc[0]["SYM_A"], abs=1e-5) == 0.75 # Final is capped
    assert pytest.approx(w_cap.iloc[0]["SYM_B"], abs=1e-5) == 0.25 # Final is bounded


def test_iv_cap_test_f_determinism(mock_p13_dataset):
    """Test F: Run the sizing calculation twice on identical inputs and verify identical results."""
    preds_df, prices_df, _ = mock_p13_dataset
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    
    run1 = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="iv_capped")
    run2 = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="iv_capped")
    pd.testing.assert_frame_equal(run1, run2)


def test_iv_cap_test_g_future_mutation(mock_p13_dataset):
    """Test G: Modify future volatility inputs after bar 150 and verify historical IV-Cap weights prior to bar 150 are unchanged."""
    preds_df, prices_df, _ = mock_p13_dataset
    cutoff = 150
    vol_panel = VolatilitySizingEngine.compute_historical_volatility(prices_df, window=168)
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    
    w_cap_orig = VolatilitySizingEngine.size_portfolio(w_raw, vol_panel, mode="iv_capped")
    
    # Mutate future volatility panel
    vol_mut = vol_panel.copy()
    vol_mut.iloc[cutoff:] = vol_mut.iloc[cutoff:] * 5.0
    w_cap_mut = VolatilitySizingEngine.size_portfolio(w_raw, vol_mut, mode="iv_capped")
    
    pd.testing.assert_frame_equal(w_cap_orig.iloc[:cutoff], w_cap_mut.iloc[:cutoff])
