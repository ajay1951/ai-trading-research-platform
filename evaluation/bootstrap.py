"""
Evaluation: Bootstrap Confidence Intervals
===========================================
Computes stationary and percentile bootstrap confidence intervals for Sharpe Ratio
and Strategy Returns without assuming normality.
"""
from typing import Dict, Any, List, Tuple
import numpy as np
import pandas as pd


class BootstrapEvaluator:
    def __init__(self, n_iterations: int = 1000, confidence_level: float = 0.95, seed: int = 42):
        self.n_iterations = n_iterations
        self.confidence_level = confidence_level
        self.seed = seed

    def compute_sharpe_ci(
        self,
        returns: List[float],
        risk_free_rate: float = 0.0,
        annualization_factor: float = np.sqrt(365 * 24)
    ) -> Dict[str, Any]:
        """Calculates bootstrap confidence intervals for the annualized Sharpe Ratio."""
        if len(returns) < 5:
            return {"error": "Insufficient data points for bootstrap"}

        arr = np.array(returns)
        np.random.seed(self.seed)
        n = len(arr)

        boot_sharpes = []
        for _ in range(self.n_iterations):
            sample = np.random.choice(arr, size=n, replace=True)
            std = np.std(sample)
            if std > 1e-9:
                s = (np.mean(sample) - risk_free_rate) / std * annualization_factor
                boot_sharpes.append(s)

        boot_sharpes = np.array(boot_sharpes)
        alpha = 1.0 - self.confidence_level
        ci_lower = float(np.percentile(boot_sharpes, (alpha / 2.0) * 100.0))
        ci_upper = float(np.percentile(boot_sharpes, (1.0 - alpha / 2.0) * 100.0))
        median_sharpe = float(np.median(boot_sharpes))

        return {
            "metric": "Sharpe Ratio",
            "confidence_level": self.confidence_level,
            "ci_lower": round(ci_lower, 3),
            "ci_upper": round(ci_upper, 3),
            "median": round(median_sharpe, 3),
            "iterations": self.n_iterations
        }
