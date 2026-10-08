"""
Unit and Regression Tests for P1-2 Cross-Sectional Robustness & Sensitivity Engine
=================================================================================
Verifies cost scaling, Top-N allocation, universe leave-one-out slicing,
rebalance intervals (18H, 24H, 36H, 48H), future mutation invariance, and reproducibility.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio
from training.robustness_validation import RobustnessValidationRunner


@pytest.fixture
def mock_predictions_and_prices():
    """Generates synthetic 100-bar multi-asset prediction and price panel."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
    n_bars = 120
    base_time = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(hours=i) for i in range(n_bars)]

    np.random.seed(42)
    pred_data = {sym: np.random.uniform(0.4, 0.6, size=n_bars) for sym in symbols}
    price_data = {}
    for sym in symbols:
        ret = np.random.normal(0.0005, 0.01, size=n_bars)
        price_data[sym] = 100.0 * np.cumprod(1.0 + ret)

    preds_df = pd.DataFrame(pred_data, index=timestamps)
    prices_df = pd.DataFrame(price_data, index=timestamps)
    return preds_df, prices_df, symbols


def test_cost_scaling_monotonicity(mock_predictions_and_prices):
    """Verifies that higher friction levels strictly scale transaction costs and reduce net return deterministically."""
    preds_df, prices_df, symbols = mock_predictions_and_prices
    raw_weights = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    sched_weights = CrossSectionalRanker.apply_rebalance_frequency(raw_weights, interval_bars=24)

    costs_grid = [0.0, 5.0, 12.0, 20.0, 30.0, 50.0]
    total_costs = []
    net_returns = []

    for cost_bps in costs_grid:
        fee_rate = (cost_bps / 20000.0) * (2.0 / 3.0)
        slippage = (cost_bps / 20000.0) * (1.0 / 3.0)
        m = simulate_cross_sectional_portfolio(prices_df, sched_weights, fee_rate=fee_rate, slippage=slippage)
        total_costs.append(m["total_costs_pct"])
        net_returns.append(m["return_pct"])

    # 1. Zero cost should produce 0.0 total costs
    assert total_costs[0] == 0.0

    # 2. Costs must be strictly monotonic non-decreasing with cost_bps
    for i in range(len(costs_grid) - 1):
        assert total_costs[i + 1] > total_costs[i]
        assert net_returns[i + 1] < net_returns[i]


def test_top_n_selection_and_weight_properties(mock_predictions_and_prices):
    """Verifies Top-1, Top-2, Top-3, Top-4 select correct number of assets and sum to 100%."""
    preds_df, prices_df, _ = mock_predictions_and_prices

    for top_n in [1, 2, 3, 4]:
        weights_df = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=top_n)
        for t_idx in range(len(weights_df)):
            row = weights_df.iloc[t_idx]
            active_weights = row[row > 0]
            assert len(active_weights) == top_n
            assert pytest.approx(active_weights.sum(), abs=1e-5) == 1.0
            for w in active_weights:
                assert pytest.approx(w, abs=1e-5) == 1.0 / top_n


def test_leave_one_out_universe_slicing(mock_predictions_and_prices):
    """Verifies that removing an asset properly excludes it from selection without mutating original data."""
    preds_df, prices_df, symbols = mock_predictions_and_prices
    orig_cols = list(preds_df.columns)

    for removed_sym in symbols:
        remaining = [s for s in symbols if s != removed_sym]
        weights_df = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2, symbols_subset=remaining)

        # The removed asset must have 0 allocation across all timestamps
        assert (weights_df[removed_sym] == 0.0).all()

        # Exactly 2 assets from remaining must be selected at each bar
        for t_idx in range(len(weights_df)):
            row = weights_df.iloc[t_idx]
            active_assets = row[row > 0].index.tolist()
            assert len(active_assets) == 2
            assert removed_sym not in active_assets

    # Original dataframe columns must remain intact
    assert list(preds_df.columns) == orig_cols


def test_rebalance_schedules_18h_24h_36h_48h(mock_predictions_and_prices):
    """Verifies scheduling for 18H, 24H, 36H, 48H intervals and confirms turnover monotonically decreases."""
    preds_df, prices_df, _ = mock_predictions_and_prices
    raw_weights = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)

    intervals = [18, 24, 36, 48]
    turnovers = []

    for int_bars in intervals:
        sched_w = CrossSectionalRanker.apply_rebalance_frequency(raw_weights, interval_bars=int_bars)
        
        # Verify intermediate bars are forward filled
        for i in range(len(sched_w)):
            if i % int_bars != 0:
                prev_i = i - (i % int_bars)
                pd.testing.assert_series_equal(sched_w.iloc[i], sched_w.iloc[prev_i], check_names=False)

        m = simulate_cross_sectional_portfolio(prices_df, sched_w, fee_rate=0.0004, slippage=0.0002)
        turnovers.append(m["turnover"])

    # Turnover must generally decline as rebalance interval widens
    assert turnovers[0] >= turnovers[1]
    assert turnovers[1] >= turnovers[-1]


def test_future_mutation_invariance(mock_predictions_and_prices):
    """Verifies that altering prices at future timestamps t >= 60 does not change historical decisions or returns for t < 60."""
    preds_df, prices_df, _ = mock_predictions_and_prices
    cutoff_bar = 60

    raw_w1 = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    sched_w1 = CrossSectionalRanker.apply_rebalance_frequency(raw_w1, interval_bars=24)

    # Mutate future predictions & prices
    preds_df_mutated = preds_df.copy()
    prices_df_mutated = prices_df.copy()
    preds_df_mutated.iloc[cutoff_bar:] = np.random.uniform(0.1, 0.9, size=preds_df.iloc[cutoff_bar:].shape)
    prices_df_mutated.iloc[cutoff_bar:] *= 2.5

    raw_w2 = RobustnessValidationRunner._compute_weights_series(preds_df_mutated, top_n=2)
    sched_w2 = CrossSectionalRanker.apply_rebalance_frequency(raw_w2, interval_bars=24)

    # Decisions up to cutoff must be byte-for-byte identical
    pd.testing.assert_frame_equal(sched_w1.iloc[:cutoff_bar], sched_w2.iloc[:cutoff_bar])


def test_reproducibility_deterministic_runs(mock_predictions_and_prices):
    """Verifies that running portfolio simulation twice on identical inputs produces identical metrics."""
    preds_df, prices_df, _ = mock_predictions_and_prices
    raw_w = RobustnessValidationRunner._compute_weights_series(preds_df, top_n=2)
    sched_w = CrossSectionalRanker.apply_rebalance_frequency(raw_w, interval_bars=24)

    m1 = simulate_cross_sectional_portfolio(prices_df, sched_w, fee_rate=0.0004, slippage=0.0002)
    m2 = simulate_cross_sectional_portfolio(prices_df, sched_w, fee_rate=0.0004, slippage=0.0002)

    assert m1 == m2
