"""
tests/cross_sectional/test_p4_1_isolation.py
============================================
P4-1 Shadow Non-Interference & Isolation Validation Test Suite.

Validates:
1. Shadow isolation: Running Challenger alongside Champion does NOT alter Champion predictions or outputs.
2. Bitwise equivalence of Champion standalone vs Champion in shadow mode.
"""

import pytest
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from evaluation.extended_shadow import ExtendedShadowEngine


def test_shadow_non_interference_bitwise():
    # Create deterministic dataset
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    symbols = ["BTCUSDT", "ETHUSDT"]

    prices_df = pd.DataFrame({
        "BTCUSDT": 50000.0 + np.cumsum(np.random.normal(0, 100, 100)),
        "ETHUSDT": 3000.0 + np.cumsum(np.random.normal(0, 20, 100))
    }, index=dates)

    asset_dfs = {}
    for s in symbols:
        asset_dfs[s] = pd.DataFrame({
            "feat1": np.random.normal(0, 1, 100),
            "feat2": np.random.normal(0, 1, 100),
            "target": np.random.binomial(1, 0.5, 100)
        }, index=dates)

    X_train = np.random.normal(0, 1, (200, 2))
    y_train = np.random.binomial(1, 0.5, 200)

    champ_model = LGBMClassifier(n_estimators=10, max_depth=3, random_state=42, verbose=-1)
    champ_model.fit(X_train, y_train)

    chall_model = LGBMClassifier(n_estimators=15, max_depth=4, random_state=99, verbose=-1)
    chall_model.fit(X_train, y_train)

    # 1. Run Champion with Challenger in Shadow
    res_shadow = ExtendedShadowEngine.run_longitudinal_study(
        champion_model=champ_model,
        challenger_model=chall_model,
        champion_model_id="CHAMP",
        challenger_model_id="CHALL",
        prices_df=prices_df,
        asset_dfs=asset_dfs,
        eval_timestamps=list(dates),
        rebalance_interval_bars=48,
        cost_bps_one_way=21.38
    )

    # 2. Run Champion with identical Challenger (self-shadow)
    res_standalone = ExtendedShadowEngine.run_longitudinal_study(
        champion_model=champ_model,
        challenger_model=champ_model,
        champion_model_id="CHAMP",
        challenger_model_id="CHAMP",
        prices_df=prices_df,
        asset_dfs=asset_dfs,
        eval_timestamps=list(dates),
        rebalance_interval_bars=48,
        cost_bps_one_way=21.38
    )

    # Champion results must be bitwise identical regardless of what Challenger was running
    assert res_shadow.champion_net_return_pct == res_standalone.champion_net_return_pct
    assert res_shadow.champion_net_sharpe == res_standalone.champion_net_sharpe
    assert res_shadow.champion_max_drawdown_pct == res_standalone.champion_max_drawdown_pct
    assert res_shadow.is_shadow_isolated
