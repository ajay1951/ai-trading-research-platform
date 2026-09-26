"""
Evaluation: Monte Carlo Equity Path & Risk Distribution Engine
=============================================================
Runs randomized path simulations and trade return shuffling to compute
tail risk distributions: VaR (95%), CVaR (95%), and Maximum Drawdown distributions.
"""
from typing import Dict, Any, List
import numpy as np


class MonteCarloSimulator:
    def __init__(self, n_simulations: int = 1000, initial_capital: float = 1000.0, seed: int = 42):
        self.n_simulations = n_simulations
        self.initial_capital = initial_capital
        self.seed = seed

    def simulate(self, trade_returns: List[float]) -> Dict[str, Any]:
        """Runs Monte Carlo permutation resampling across historical trade returns."""
        if len(trade_returns) < 5:
            return {"error": "Insufficient trade count for simulation"}

        arr = np.array(trade_returns)
        n_trades = len(arr)
        np.random.seed(self.seed)

        max_drawdowns = []
        final_returns = []

        for _ in range(self.n_simulations):
            sampled = np.random.choice(arr, size=n_trades, replace=True)
            equity_curve = self.initial_capital * np.cumprod(1.0 + sampled)

            peak = np.maximum.accumulate(equity_curve)
            dd = (equity_curve - peak) / peak
            max_dd = abs(np.min(dd)) * 100.0

            max_drawdowns.append(max_dd)
            ret_pct = ((equity_curve[-1] - self.initial_capital) / self.initial_capital) * 100.0
            final_returns.append(ret_pct)

        max_drawdowns = np.array(max_drawdowns)
        final_returns = np.array(final_returns)

        var_95 = float(np.percentile(max_drawdowns, 95))
        cvar_95 = float(np.mean(max_drawdowns[max_drawdowns >= var_95]))
        prob_profit = float(np.mean(final_returns > 0.0) * 100.0)

        return {
            "iterations": self.n_simulations,
            "median_max_drawdown_pct": round(float(np.median(max_drawdowns)), 2),
            "var_95_max_dd_pct": round(var_95, 2),
            "cvar_95_max_dd_pct": round(cvar_95, 2),
            "worst_case_max_dd_pct": round(float(np.max(max_drawdowns)), 2),
            "probability_of_profit_pct": round(prob_profit, 2),
            "median_final_return_pct": round(float(np.median(final_returns)), 2)
        }
