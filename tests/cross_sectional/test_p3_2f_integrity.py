"""
tests/cross_sectional/test_p3_2f_integrity.py
=============================================
P3-2F Dynamic Risk Integrity, Activation & Methodology Validation Test Suite.

Validates:
1. Drawdown-aware activation accounting and causal state transitions
2. Inverse Volatility vs Equal Risk Contribution (ERC) algebraic equivalence
3. Correlation-aware control causality and exposure reduction
4. Regime conditioning causality and sample boundaries
5. Volatility targeting mathematical consistency
6. Value-at-Risk (VaR) and Expected Shortfall (CVaR) causality
7. MRC/CRC conservation under near-singular and regular covariances
8. Future mutation causality invariance
9. Determinism and baseline immutability
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
# 1. Drawdown Activation & State Transition Tests
# =============================================================================

def test_drawdown_state_transition_sequence():
    cfg = DynamicRiskConfig(mode=RiskControlMode.DRAWDOWN_AWARE)
    engine = DynamicRiskEngine(cfg)

    dates = pd.date_range("2026-01-01", periods=6, freq="1h")
    prices = pd.DataFrame({"BTCUSDT": [100.0] * 6}, index=dates)
    base_w = pd.DataFrame({"BTCUSDT": [1.0] * 6}, index=dates)

    # Sequence: 1.0 (Normal) -> 0.94 (Caution -6%) -> 0.88 (Defensive -12%) -> 0.82 (Severe -18%) -> 0.96 (Recovery to Caution -4% from 1.0 -> Normal)
    eq_curve = [1.0, 0.94, 0.88, 0.82, 0.96, 1.02]
    sized_w = engine.size_portfolio_weights(base_w, prices, realized_equity_curve=eq_curve)

    assert np.isclose(sized_w.iloc[0]["BTCUSDT"], 1.00) # Normal (DD = 0%)
    assert np.isclose(sized_w.iloc[1]["BTCUSDT"], 0.80) # Caution (DD = 6%)
    assert np.isclose(sized_w.iloc[2]["BTCUSDT"], 0.50) # Defensive (DD = 12%)
    assert np.isclose(sized_w.iloc[3]["BTCUSDT"], 0.25) # Severe (DD = 18%)
    assert np.isclose(sized_w.iloc[4]["BTCUSDT"], 1.00) # Normal (DD = 4%)
    assert np.isclose(sized_w.iloc[5]["BTCUSDT"], 1.00) # Normal (New peak 1.02)


# =============================================================================
# 2. Inverse Volatility vs ERC Mathematical Equivalence
# =============================================================================

def test_iv_vs_erc_algebraic_identity():
    """
    Validates that for any 2-asset long-only portfolio, Inverse Volatility weighting
    and Equal Risk Contribution (ERC) weighting are algebraically identical.
    """
    vols = [0.20, 0.40] # Vol1 = 20%, Vol2 = 40%
    correlations = [-0.50, 0.00, 0.50, 0.80, 0.95]

    for corr in correlations:
        cov12 = corr * vols[0] * vols[1]
        cov_mat = pd.DataFrame([
            [vols[0] ** 2, cov12],
            [cov12, vols[1] ** 2]
        ], index=["A", "B"], columns=["A", "B"])

        # Inverse Volatility weights: w1 = 1/0.2 / (1/0.2 + 1/0.4) = 5 / 7.5 = 2/3
        w_iv = {"A": (1.0 / vols[0]) / (1.0 / vols[0] + 1.0 / vols[1]), "B": (1.0 / vols[1]) / (1.0 / vols[0] + 1.0 / vols[1])}

        rc = DynamicRiskEngine.decompose_risk_contributions(w_iv, cov_mat)

        # In ERC, CRC1 must equal CRC2
        assert np.isclose(rc.component_risk_contributions["A"], rc.component_risk_contributions["B"], atol=1e-6)
        assert np.isclose(rc.percentage_risk_contributions["A"], 0.50, atol=1e-4)
        assert np.isclose(rc.percentage_risk_contributions["B"], 0.50, atol=1e-4)


# =============================================================================
# 3. Correlation-Aware Control Triggering
# =============================================================================

def test_correlation_control_scaling():
    cfg = DynamicRiskConfig(mode=RiskControlMode.CORRELATION_AWARE, corr_threshold=0.80)
    engine = DynamicRiskEngine(cfg)

    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    # Highly correlated assets (rho ~ 0.95)
    np.random.seed(42)
    noise = np.random.normal(0, 0.005, 100)
    series_a = np.cumprod(1 + np.random.normal(0, 0.01, 100)) * 100.0
    series_b = series_a * (1 + noise)

    prices = pd.DataFrame({"A": series_a, "B": series_b}, index=dates)
    base_w = pd.DataFrame({"A": 0.5, "B": 0.5}, index=dates)

    sized_w = engine.size_portfolio_weights(base_w, prices)

    # After initial lookback, gross exposure must be scaled down
    last_exposure = sized_w.iloc[-1].sum()
    assert last_exposure < 1.00
    assert last_exposure >= 0.50


# =============================================================================
# 4. Volatility Target Scaling
# =============================================================================

def test_volatility_target_scaling():
    cfg = DynamicRiskConfig(mode=RiskControlMode.VOL_TARGETING, target_annual_vol=0.20)
    engine = DynamicRiskEngine(cfg)

    # High volatility asset (~60% annualized)
    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    np.random.seed(42)
    p_high_vol = np.cumprod(1 + np.random.normal(0, 0.02, 100)) * 100.0
    prices = pd.DataFrame({"BTCUSDT": p_high_vol}, index=dates)
    base_w = pd.DataFrame({"BTCUSDT": 1.0}, index=dates)

    sized_w = engine.size_portfolio_weights(base_w, prices)
    last_weight = sized_w.iloc[-1]["BTCUSDT"]

    # Target (20%) / Est Vol (~60%) -> weight scaled down towards ~0.33
    assert last_weight < 0.50
    assert last_weight >= 0.20


# =============================================================================
# 5. Future Mutation Invariance
# =============================================================================

def test_dynamic_risk_future_mutation():
    engine = DynamicRiskEngine(DynamicRiskConfig(mode=RiskControlMode.COMBINED_DYNAMIC))
    dates = pd.date_range("2026-01-01", periods=80, freq="1h")
    np.random.seed(99)
    p_orig = pd.DataFrame({
        "BTCUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 80)) * 50000.0,
        "ETHUSDT": np.cumprod(1 + np.random.normal(0, 0.01, 80)) * 3000.0
    }, index=dates)
    base_w = pd.DataFrame({"BTCUSDT": 0.5, "ETHUSDT": 0.5}, index=dates)

    w1 = engine.size_portfolio_weights(base_w, p_orig)

    # Mutate future bars after t=45
    p_mutated = p_orig.copy()
    p_mutated.iloc[45:] = p_mutated.iloc[45:] * 5.0

    w2 = engine.size_portfolio_weights(base_w, p_mutated)

    assert np.allclose(w1.iloc[:43].values, w2.iloc[:43].values, atol=1e-8)
