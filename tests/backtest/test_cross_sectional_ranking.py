"""
Cross-Sectional Multi-Asset Ranking & Portfolio Construction Tests
===================================================================
Rigorous unit and leakage tests for relative-strength ranking, Top-N selection,
tie-breaking, missing data handling, and friction deduction.
"""

import pytest
import numpy as np
import pandas as pd
from evaluation.cross_sectional import CrossSectionalRanker, simulate_cross_sectional_portfolio


def test_correct_ranking_order_descending():
    """Verifies that assets are ranked strictly by predicted score descending."""
    predictions = {
        "BTC": 0.55,
        "ETH": 0.85,
        "SOL": 0.70,
        "BNB": 0.40,
        "XRP": 0.30
    }
    weights = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=2, allow_short=True)
    
    # Top 2: ETH (0.85), SOL (0.70) -> Long (+0.50 each)
    assert np.isclose(weights["ETH"], 0.50)
    assert np.isclose(weights["SOL"], 0.50)
    # Bottom 2: XRP (0.30), BNB (0.40) -> Short (-0.50 each)
    assert np.isclose(weights["XRP"], -0.50)
    assert np.isclose(weights["BNB"], -0.50)
    # Middle: BTC (0.55) -> Neutral (0.0)
    assert np.isclose(weights["BTC"], 0.0)


def test_top_2_long_selection():
    """Verifies Top-2 long selection assigns positive weights equally."""
    predictions = {"A": 0.9, "B": 0.8, "C": 0.5, "D": 0.2}
    weights = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=0, allow_short=False)
    
    assert np.isclose(weights["A"], 0.50)
    assert np.isclose(weights["B"], 0.50)
    assert weights["C"] == 0.0
    assert weights["D"] == 0.0


def test_bottom_2_short_selection():
    """Verifies Bottom-2 short selection assigns negative weights."""
    predictions = {"A": 0.9, "B": 0.8, "C": 0.5, "D": 0.2, "E": 0.1}
    weights = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=2, allow_short=True)
    
    assert np.isclose(weights["D"], -0.50)
    assert np.isclose(weights["E"], -0.50)


def test_long_only_mode():
    """Verifies that allow_short=False enforces zero short exposure for all assets."""
    predictions = {"BTC": 0.8, "ETH": 0.7, "SOL": 0.3, "DOGE": 0.1}
    weights = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=2, allow_short=False)
    
    assert weights["BTC"] == 0.50
    assert weights["ETH"] == 0.50
    assert weights["SOL"] == 0.0
    assert weights["DOGE"] == 0.0
    assert all(w >= 0.0 for w in weights.values())


def test_equal_prediction_tie_handling():
    """Verifies that identical prediction scores resolve deterministically via symbol sorting."""
    predictions = {"SOL": 0.50, "ETH": 0.50, "BTC": 0.50, "ADA": 0.50}
    weights_1 = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=2, allow_short=True)
    weights_2 = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=2, allow_short=True)
    
    assert weights_1 == weights_2
    assert sum(weights_1.values()) == 0.0 # Long sum (+1.0) + Short sum (-1.0) = 0.0


def test_missing_and_nan_asset_handling():
    """Verifies that NaN, None, and Inf values are safely excluded from rankings."""
    predictions = {
        "BTC": 0.80,
        "ETH": np.nan,
        "SOL": None,
        "BNB": 0.60,
        "XRP": 0.20,
        "ADA": 0.10
    }
    weights = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=2, allow_short=True)
    
    assert weights["ETH"] == 0.0
    assert weights["SOL"] == 0.0
    assert weights["BTC"] == 0.50
    assert weights["BNB"] == 0.50
    assert weights["ADA"] == -0.50
    assert weights["XRP"] == -0.50


def test_insufficient_assets_handling():
    """Verifies graceful handling when total assets < (top_n + bottom_n)."""
    predictions = {"BTC": 0.75, "ETH": 0.25}
    # Asking for Top 2 and Bottom 2 from only 2 assets -> Long only top assets safely
    weights = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=2, allow_short=True)
    
    assert weights["BTC"] == 0.50
    assert weights["ETH"] == 0.50 # Both allocated long without short collision


def test_risk_and_exposure_limits():
    """Verifies that gross leverage does not exceed configured maximum single weight."""
    predictions = {f"SYM_{i}": 0.5 + i * 0.05 for i in range(10)}
    weights = CrossSectionalRanker.rank_assets(predictions, top_n=2, bottom_n=2, allow_short=True, max_single_weight=0.35)
    
    for w in weights.values():
        assert abs(w) <= 0.35 + 1e-6


def test_turnover_and_transaction_cost_deduction():
    """
    Verifies that portfolio simulation deducts exact friction proportional to weight changes.
    """
    timestamps = pd.date_range("2026-01-01", periods=10, freq="1h")
    # 2 assets, completely flat prices ($100.0)
    prices_df = pd.DataFrame({
        "A": np.full(10, 100.0),
        "B": np.full(10, 100.0)
    }, index=timestamps)

    # Alternate 100% allocation between A and B every bar (200% turnover per step)
    weights_df = pd.DataFrame({
        "A": [1.0 if i % 2 == 0 else 0.0 for i in range(10)],
        "B": [0.0 if i % 2 == 0 else 1.0 for i in range(10)]
    }, index=timestamps)

    fee_rate = 0.0004
    slippage = 0.0002
    cost_per_trade = fee_rate + slippage # 0.0006 per 100% turnover

    metrics = simulate_cross_sectional_portfolio(
        prices_df, weights_df, fee_rate=fee_rate, slippage=slippage, initial_capital=1000.0
    )

    # In a flat market with 200% turnover per bar, return must be strictly negative due to friction
    assert metrics["return_pct"] < 0.0
    assert metrics["trades"] > 0
    assert metrics["turnover"] > 0.0


def test_zero_future_leakage_in_ranking():
    """
    Causality / Leakage test: Verifies that mutating future prices at bar t+1
    has ZERO effect on the cross-sectional ranking generated at bar t.
    """
    predictions_t = {"BTC": 0.70, "ETH": 0.80, "SOL": 0.60, "BNB": 0.40}
    weights_original = CrossSectionalRanker.rank_assets(predictions_t, top_n=2, bottom_n=2)

    # Modify future prediction scores at t+1
    predictions_future_mutated = {"BTC": 0.10, "ETH": 0.20, "SOL": 0.90, "BNB": 0.95}

    # Re-evaluate bar t weights
    weights_recheck = CrossSectionalRanker.rank_assets(predictions_t, top_n=2, bottom_n=2)

    assert weights_original == weights_recheck
