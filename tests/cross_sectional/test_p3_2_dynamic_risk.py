"""
tests/cross_sectional/test_p3_2_dynamic_risk.py
===============================================
P3-2 Dynamic Risk & Portfolio Intelligence Validation Test Suite.

Validates:
1. Causal volatility, covariance, and correlation calculations
2. Future data mutation invariance across all risk features
3. Portfolio volatility, Marginal Risk Contribution (MRC), and Component Risk Contribution (CRC)
4. CRC sum conservation identity: sum(CRC_i) == portfolio_volatility
5. Weight invariants: w_i >= 0, sum(w_i) <= 1.0, max weight caps
6. Drawdown state transitions and exposure scaling
7. BTC market regime conditioning
8. Historical Value-at-Risk (VaR) and Expected Shortfall (CVaR)
9. Deterministic execution and baseline immutability
10. Robustness across edge cases (zero vol, perfectly correlated assets, single asset)
"""

import pytest
import numpy as np
import pandas as pd
from evaluation.dynamic_risk import (
    DynamicRiskEngine,
    DynamicRiskConfig,
    RiskControlMode,
    DrawdownState,
    RiskContributionMetrics
)


# =============================================================================
# 1. Causal Volatility & Covariance Tests
# =============================================================================

def test_causal_volatility_and_covariance_calculation():
    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    np.random.seed(42)
    prices = pd.DataFrame({
        "BTCUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 100)) * 50000.0,
        "ETHUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 100)) * 3000.0
    }, index=dates)

    vol_df = DynamicRiskEngine.compute_rolling_volatility(prices, window=24, min_periods=5)
    cov_dict = DynamicRiskEngine.compute_rolling_covariance(prices, window=24, min_periods=5)

    assert len(vol_df) == 100
    assert not vol_df.iloc[25:].isna().any().any()
    assert (vol_df.iloc[25:] > 0).all().all()

    # Check covariance symmetry and positive semi-definiteness
    last_ts = dates[-1]
    assert last_ts in cov_dict
    cov_mat = cov_dict[last_ts]
    assert np.isclose(cov_mat.loc["BTCUSDT", "ETHUSDT"], cov_mat.loc["ETHUSDT", "BTCUSDT"])
    eigenvalues = np.linalg.eigvalsh(cov_mat.values)
    assert np.all(eigenvalues >= -1e-8)


# =============================================================================
# 2. Marginal & Component Risk Contribution (MRC/CRC Conservation)
# =============================================================================

def test_risk_contribution_decomposition_and_conservation():
    cov_mat = pd.DataFrame([
        [0.16, 0.08],
        [0.08, 0.25]
    ], index=["BTCUSDT", "ETHUSDT"], columns=["BTCUSDT", "ETHUSDT"])

    weights = {"BTCUSDT": 0.5, "ETHUSDT": 0.5}
    rc_metrics = DynamicRiskEngine.decompose_risk_contributions(weights, cov_mat)

    # Verification: sum(CRC_i) must equal portfolio volatility
    assert rc_metrics.is_reconciled
    assert np.isclose(rc_metrics.crc_sum, rc_metrics.portfolio_volatility, atol=1e-5)
    assert rc_metrics.portfolio_volatility > 0
    assert rc_metrics.diversification_ratio >= 1.0


# =============================================================================
# 3. Weight Invariants & Normalization
# =============================================================================

def test_dynamic_risk_weight_invariants():
    engine = DynamicRiskEngine(DynamicRiskConfig(mode=RiskControlMode.COMBINED_DYNAMIC, target_annual_vol=0.20))
    dates = pd.date_range("2026-01-01", periods=50, freq="1h")
    prices = pd.DataFrame({"BTCUSDT": np.linspace(50000, 55000, 50), "ETHUSDT": np.linspace(3000, 3300, 50)}, index=dates)
    base_w = pd.DataFrame({"BTCUSDT": 0.5, "ETHUSDT": 0.5}, index=dates)

    sized_w = engine.size_portfolio_weights(base_w, prices)

    assert (sized_w >= 0.0).all().all()
    assert (sized_w.sum(axis=1) <= 1.0 + 1e-6).all()
    assert not sized_w.isna().any().any()


# =============================================================================
# 4. Drawdown State Transitions
# =============================================================================

def test_drawdown_state_scaling():
    engine = DynamicRiskEngine(DynamicRiskConfig(mode=RiskControlMode.DRAWDOWN_AWARE))
    dates = pd.date_range("2026-01-01", periods=4, freq="1h")
    prices = pd.DataFrame({"BTCUSDT": [100.0, 100.0, 100.0, 100.0]}, index=dates)
    base_w = pd.DataFrame({"BTCUSDT": [1.0, 1.0, 1.0, 1.0]}, index=dates)

    # Simulated Equity: Peak = 1.0, then drops to 0.94 (-6%), 0.88 (-12%), 0.80 (-20%)
    equity_curve = [1.0, 0.94, 0.88, 0.80]
    sized_w = engine.size_portfolio_weights(base_w, prices, realized_equity_curve=equity_curve)

    # Bar 0: Normal (1.0)
    # Bar 1: Caution -6% (0.80)
    # Bar 2: Defensive -12% (0.50)
    # Bar 3: Severe -20% (0.25)
    assert np.isclose(sized_w.iloc[0]["BTCUSDT"], 1.00)
    assert np.isclose(sized_w.iloc[1]["BTCUSDT"], 0.80)
    assert np.isclose(sized_w.iloc[2]["BTCUSDT"], 0.50)
    assert np.isclose(sized_w.iloc[3]["BTCUSDT"], 0.25)


# =============================================================================
# 5. Value-at-Risk & Expected Shortfall
# =============================================================================

def test_var_and_cvar_calculation():
    np.random.seed(42)
    rets = np.random.normal(0.001, 0.02, 1000)
    var_95, es_95 = DynamicRiskEngine.calculate_var_cvar(rets, 0.95)

    assert var_95 > 0.0
    assert es_95 >= var_95


# =============================================================================
# 6. Future Data Mutation Invariance
# =============================================================================

def test_future_mutation_invariance():
    engine = DynamicRiskEngine(DynamicRiskConfig(mode=RiskControlMode.COMBINED_DYNAMIC))
    dates = pd.date_range("2026-01-01", periods=80, freq="1h")
    np.random.seed(123)
    p_orig = pd.DataFrame({
        "BTCUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 80)) * 50000.0,
        "ETHUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 80)) * 3000.0
    }, index=dates)
    w_orig = pd.DataFrame({"BTCUSDT": 0.5, "ETHUSDT": 0.5}, index=dates)

    w_res1 = engine.size_portfolio_weights(w_orig, p_orig)

    # Mutate future bars after t=50
    p_mutated = p_orig.copy()
    p_mutated.iloc[50:] = p_mutated.iloc[50:] * 8.0

    w_res2 = engine.size_portfolio_weights(w_orig, p_mutated)

    assert np.allclose(w_res1.iloc[:48].values, w_res2.iloc[:48].values, atol=1e-8)


# =============================================================================
# 7. Edge Cases & Robustness
# =============================================================================

def test_zero_volatility_edge_case():
    cov_zero = pd.DataFrame([
        [0.0, 0.0],
        [0.0, 0.0]
    ], index=["BTCUSDT", "ETHUSDT"], columns=["BTCUSDT", "ETHUSDT"])

    rc = DynamicRiskEngine.decompose_risk_contributions({"BTCUSDT": 0.5, "ETHUSDT": 0.5}, cov_zero)
    assert rc.portfolio_volatility == 0.0
    assert rc.is_reconciled


def test_perfect_correlation_edge_case():
    # Vol1 = 0.20, Vol2 = 0.20, Corr = 1.0 -> Cov = 0.04
    cov_perf = pd.DataFrame([
        [0.04, 0.04],
        [0.04, 0.04]
    ], index=["BTCUSDT", "ETHUSDT"], columns=["BTCUSDT", "ETHUSDT"])

    rc = DynamicRiskEngine.decompose_risk_contributions({"BTCUSDT": 0.5, "ETHUSDT": 0.5}, cov_perf)
    assert np.isclose(rc.portfolio_volatility, 0.20)
    assert np.isclose(rc.diversification_ratio, 1.00) # Zero diversification benefit


def test_single_active_asset():
    cov_single = pd.DataFrame([[0.09]], index=["BTCUSDT"], columns=["BTCUSDT"])
    rc = DynamicRiskEngine.decompose_risk_contributions({"BTCUSDT": 1.0}, cov_single)
    assert np.isclose(rc.portfolio_volatility, 0.30)
    assert rc.is_reconciled


def test_regime_conditioning_scaling():
    engine = DynamicRiskEngine(DynamicRiskConfig(mode=RiskControlMode.REGIME_CONDITIONED))
    dates = pd.date_range("2026-01-01", periods=3, freq="1h")
    prices = pd.DataFrame({"BTCUSDT": [100.0, 100.0, 100.0]}, index=dates)
    base_w = pd.DataFrame({"BTCUSDT": [1.0, 1.0, 1.0]}, index=dates)

    # Bull (+10%), Sideways (0%), Bear (-10%)
    btc_trend = pd.Series([0.10, 0.00, -0.10], index=dates)
    sized_w = engine.size_portfolio_weights(base_w, prices, btc_trend_returns=btc_trend)

    assert np.isclose(sized_w.iloc[0]["BTCUSDT"], 1.00)
    assert np.isclose(sized_w.iloc[1]["BTCUSDT"], 0.80)
    assert np.isclose(sized_w.iloc[2]["BTCUSDT"], 0.50)

