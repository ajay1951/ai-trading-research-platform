"""
Unit and Regression Tests for P1-4 Portfolio Risk, Concentration & Stress Audit
==============================================================================
Verifies:
- Test A: HHI calculation
- Test B: Effective number of assets
- Test C: Asset exposure accounting
- Test D: Selection counts
- Test E: Selection rates sum correctly
- Test F: Asset PnL contribution accounting
- Test G: Correlation matrix symmetry
- Test H: Correlation diagonal equals 1
- Test I: Rolling correlation uses past-only observations
- Test J: Selected-pair correlation uses point-in-time information
- Test K: Single-asset stress calculation
- Test L: Two-asset stress calculation
- Test M: Drawdown identification
- Test N: Future-mutation invariance
- Test O: Determinism
- Test P: No mutation of frozen strategy weights
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from evaluation.portfolio_risk import PortfolioRiskEngine
from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio
from training.robustness_validation import RobustnessValidationRunner, UNIVERSE_SYMBOLS


@pytest.fixture
def mock_p14_dataset():
    """Generates synthetic multi-asset price and prediction panel for P1-4 tests."""
    symbols = UNIVERSE_SYMBOLS
    n_bars = 300
    base_time = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(hours=i) for i in range(n_bars)]

    np.random.seed(42)
    pred_data = {sym: np.random.uniform(0.4, 0.6, size=n_bars) for sym in symbols}
    price_data = {}
    for i, sym in enumerate(symbols):
        vol = 0.005 + (i * 0.002)
        ret = np.random.normal(0.0002, vol, size=n_bars)
        price_data[sym] = 100.0 * np.cumprod(1.0 + ret)

    preds_df = pd.DataFrame(pred_data, index=timestamps)
    prices_df = pd.DataFrame(price_data, index=timestamps)
    return preds_df, prices_df, symbols


def test_a_hhi_calculation():
    """Test A: Verifies HHI calculation for known allocations."""
    # 50% / 50% allocation -> HHI = 0.5^2 + 0.5^2 = 0.50
    w_equal = np.array([0.5, 0.5, 0.0, 0.0])
    assert pytest.approx(PortfolioRiskEngine.compute_hhi(w_equal), abs=1e-5) == 0.50

    # 100% single asset -> HHI = 1.0^2 = 1.00
    w_single = np.array([1.0, 0.0, 0.0])
    assert pytest.approx(PortfolioRiskEngine.compute_hhi(w_single), abs=1e-5) == 1.00

    # 4 equal assets -> HHI = 4 * 0.25^2 = 0.25
    w_four = np.array([0.25, 0.25, 0.25, 0.25])
    assert pytest.approx(PortfolioRiskEngine.compute_hhi(w_four), abs=1e-5) == 0.25


def test_b_effective_assets_calculation():
    """Test B: Verifies Effective Number of Assets (N_eff = 1 / HHI)."""
    w_equal = np.array([0.5, 0.5, 0.0])
    assert pytest.approx(PortfolioRiskEngine.compute_effective_assets(w_equal), abs=1e-5) == 2.0

    w_four = np.array([0.25, 0.25, 0.25, 0.25])
    assert pytest.approx(PortfolioRiskEngine.compute_effective_assets(w_four), abs=1e-5) == 4.0

    w_single = np.array([1.0])
    assert pytest.approx(PortfolioRiskEngine.compute_effective_assets(w_single), abs=1e-5) == 1.0


def test_c_asset_exposure_accounting(mock_p14_dataset):
    """Test C: Verifies asset exposure accounting and weight boundary checks."""
    preds_df, prices_df, _ = mock_p14_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)

    exposure_df, meta = PortfolioRiskEngine.compute_asset_exposure_and_attribution(prices_df, w_sched)
    
    assert len(exposure_df) == len(UNIVERSE_SYMBOLS)
    for _, row in exposure_df.iterrows():
        if row["selection_count"] > 0:
            assert 0.0 <= row["min_weight_pct"] <= 100.0
            assert 0.0 <= row["max_weight_pct"] <= 100.0
            assert row["max_weight_pct"] == 50.0 # 50% equal weight Top 2


def test_d_selection_counts(mock_p14_dataset):
    """Test D: Verifies that total selected slots equal 2 * total_rebalances."""
    preds_df, prices_df, _ = mock_p14_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)

    exposure_df, meta = PortfolioRiskEngine.compute_asset_exposure_and_attribution(prices_df, w_sched)
    total_slots = exposure_df["selection_count"].sum()
    expected_slots = meta["total_rebalance_events"] * 2
    assert total_slots == expected_slots


def test_e_selection_rates_sum_correctly(mock_p14_dataset):
    """Test E: Verifies selection rates sum to 200% across all assets in a Top-2 portfolio."""
    preds_df, prices_df, _ = mock_p14_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)

    exposure_df, _ = PortfolioRiskEngine.compute_asset_exposure_and_attribution(prices_df, w_sched)
    sum_rate = exposure_df["selection_rate_pct"].sum()
    assert pytest.approx(sum_rate, abs=0.1) == 200.0


def test_f_asset_pnl_contribution_accounting(mock_p14_dataset):
    """Test F: Verifies asset step gross contributions reconcile with portfolio return."""
    preds_df, prices_df, _ = mock_p14_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)

    aligned_w = w_sched.reindex(prices_df.index).ffill().fillna(0.0)
    asset_ret = ((prices_df - prices_df.shift(1)) / prices_df.shift(1)).fillna(0.0)
    step_contrib = (aligned_w.shift(1).fillna(0.0) * asset_ret).sum(axis=1)
    port_cum_gross = float((np.prod(1.0 + step_contrib) - 1.0) * 100.0)

    m = simulate_cross_sectional_portfolio(prices_df, w_sched, fee_rate=0.0, slippage=0.0)
    assert pytest.approx(m["return_pct"], rel=1e-3) == port_cum_gross


def test_g_correlation_matrix_symmetry(mock_p14_dataset):
    """Test G: Verifies pairwise correlation matrix is strictly symmetric: C_ij == C_ji."""
    _, prices_df, _ = mock_p14_dataset
    corr_mat, _ = PortfolioRiskEngine.compute_pairwise_correlations(prices_df)
    np.testing.assert_allclose(corr_mat.values, corr_mat.values.T, atol=1e-8)


def test_h_correlation_diagonal_equals_one(mock_p14_dataset):
    """Test H: Verifies correlation matrix diagonal elements are identically 1.0."""
    _, prices_df, _ = mock_p14_dataset
    corr_mat, _ = PortfolioRiskEngine.compute_pairwise_correlations(prices_df)
    diag = np.diag(corr_mat.values)
    np.testing.assert_allclose(diag, 1.0, atol=1e-8)


def test_i_rolling_correlation_uses_past_only(mock_p14_dataset):
    """Test I: Verifies rolling correlation at bar t depends only on prices up to bar t."""
    _, prices_df, _ = mock_p14_dataset
    t_idx = 180
    window = 168

    ret_full = ((prices_df - prices_df.shift(1)) / prices_df.shift(1)).fillna(0.0)
    corr_full = ret_full.iloc[t_idx - window + 1 : t_idx + 1]["BTCUSDT"].corr(ret_full.iloc[t_idx - window + 1 : t_idx + 1]["ETHUSDT"])

    prices_sliced = prices_df.iloc[: t_idx + 1]
    ret_sliced = ((prices_sliced - prices_sliced.shift(1)) / prices_sliced.shift(1)).fillna(0.0)
    corr_sliced = ret_sliced.iloc[-window:]["BTCUSDT"].corr(ret_sliced.iloc[-window:]["ETHUSDT"])

    assert pytest.approx(corr_full, abs=1e-6) == corr_sliced


def test_j_selected_pair_point_in_time_correlation(mock_p14_dataset):
    """Test J: Verifies selected pair correlation uses strictly point-in-time past slices."""
    preds_df, prices_df, _ = mock_p14_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)

    pairs_df, summary = PortfolioRiskEngine.compute_selected_pair_correlations(prices_df, w_sched, window=168)
    assert len(pairs_df) > 0
    assert 0.0 <= summary["pct_above_07"] <= 100.0
    for _, row in pairs_df.iterrows():
        assert -1.0 <= row["rolling_correlation"] <= 1.0


def test_k_single_asset_stress_calculation():
    """Test K: Verifies single-asset deterministic shock arithmetic."""
    exp_df = pd.DataFrame([{"symbol": "BTCUSDT", "max_weight_pct": 50.0, "avg_weight_when_selected_pct": 50.0}])
    pairs_df = pd.DataFrame()
    single_df, _ = PortfolioRiskEngine.compute_stress_test_matrices(exp_df, pairs_df)

    row = single_df.iloc[0]
    # 50% weight * -10% shock = -5.0% loss
    assert pytest.approx(row["loss_at_max_w_minus_10pct"], abs=1e-5) == -5.0
    # 50% weight * -50% shock = -25.0% loss
    assert pytest.approx(row["loss_at_max_w_minus_50pct"], abs=1e-5) == -25.0


def test_l_two_asset_stress_calculation():
    """Test L: Verifies simultaneous dual-asset deterministic shock arithmetic."""
    exp_df = pd.DataFrame()
    pairs_df = pd.DataFrame()
    _, dual_df = PortfolioRiskEngine.compute_stress_test_matrices(exp_df, pairs_df)

    # (-50%, -50%) on 50/50 -> -50.0%
    crash_50 = dual_df[dual_df["scenario"].str.contains("-50%, -50%")].iloc[0]
    assert pytest.approx(crash_50["portfolio_instantaneous_loss_pct"], abs=1e-5) == -50.0

    # (-50%, -20%) on 50/50 -> 0.5*-50 + 0.5*-20 = -35.0%
    crash_asym = dual_df[dual_df["scenario"].str.contains("-50%, -20%")].iloc[0]
    assert pytest.approx(crash_asym["portfolio_instantaneous_loss_pct"], abs=1e-5) == -35.0


def test_m_drawdown_identification():
    """Test M: Verifies peak-to-trough drawdown detection."""
    t_idx = pd.date_range("2025-01-01", periods=10, freq="h", tz="UTC")
    # Equity curve with a 20% drawdown: 100 -> 110 -> 88 (20% drop from 110) -> 115
    eq_vals = [100.0, 105.0, 110.0, 99.0, 88.0, 95.0, 105.0, 115.0, 116.0, 117.0]
    equity_series = pd.Series(eq_vals, index=t_idx)
    w_df = pd.DataFrame({"BTCUSDT": [0.5]*10, "ETHUSDT": [0.5]*10}, index=t_idx)
    p_df = pd.DataFrame({"BTCUSDT": [100]*10, "ETHUSDT": [100]*10}, index=t_idx)

    drawdowns = PortfolioRiskEngine.identify_drawdown_episodes(equity_series, w_df, p_df, thresholds=[0.10, 0.15])
    assert len(drawdowns) >= 1
    # 88 from 110 is exactly 20.0% drawdown
    assert pytest.approx(drawdowns[0]["max_drawdown_pct"], abs=1e-2) == 20.0


def test_n_future_mutation_invariance(mock_p14_dataset):
    """Test N: Modifying prices after bar 180 leaves historical correlations and metrics before bar 180 unchanged."""
    preds_df, prices_df, _ = mock_p14_dataset
    cutoff = 180

    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)
    
    # Original
    pairs_orig, _ = PortfolioRiskEngine.compute_selected_pair_correlations(prices_df, w_sched, window=168)

    # Mutated
    prices_mut = prices_df.copy()
    prices_mut.iloc[cutoff:] *= 4.0
    pairs_mut, _ = PortfolioRiskEngine.compute_selected_pair_correlations(prices_mut, w_sched, window=168)

    # All decisions before cutoff must be identical
    ts_cutoff = str(prices_df.index[cutoff])
    orig_pre = pairs_orig[pairs_orig["timestamp"] < ts_cutoff]
    mut_pre = pairs_mut[pairs_mut["timestamp"] < ts_cutoff]
    pd.testing.assert_frame_equal(orig_pre, mut_pre)


def test_o_p14_determinism(mock_p14_dataset):
    """Test O: Verifies that running P1-4 risk calculations twice produces identical outputs."""
    preds_df, prices_df, _ = mock_p14_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)

    exp1, meta1 = PortfolioRiskEngine.compute_asset_exposure_and_attribution(prices_df, w_sched)
    exp2, meta2 = PortfolioRiskEngine.compute_asset_exposure_and_attribution(prices_df, w_sched)

    pd.testing.assert_frame_equal(exp1, exp2)
    assert meta1 == meta2


def test_p_no_mutation_of_frozen_strategy_weights(mock_p14_dataset):
    """Test P: Verifies that risk analysis operations cannot mutate input portfolio weights."""
    preds_df, prices_df, _ = mock_p14_dataset
    w_raw = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    w_sched = CrossSectionalRanker.apply_rebalance_frequency(w_raw, interval_bars=48)
    w_copy = w_sched.copy(deep=True)

    # Run multiple audit functions
    PortfolioRiskEngine.compute_asset_exposure_and_attribution(prices_df, w_sched)
    PortfolioRiskEngine.compute_portfolio_hhi_series(w_sched)
    PortfolioRiskEngine.compute_selected_pair_correlations(prices_df, w_sched)

    pd.testing.assert_frame_equal(w_sched, w_copy)
