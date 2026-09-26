"""
Evaluation: Statistical Significance & Hypothesis Testing
==========================================================
Conducts parametric and non-parametric hypothesis tests to evaluate whether
strategy excess returns over the benchmark (Buy & Hold) are statistically significant.
"""
from typing import Dict, Any, List
import numpy as np
from scipy import stats


class SignificanceTester:
    @staticmethod
    def test_excess_returns(
        strategy_returns: List[float],
        benchmark_returns: List[float]
    ) -> Dict[str, Any]:
        """Runs Paired t-test and Wilcoxon signed-rank test against benchmark."""
        s = np.array(strategy_returns)
        b = np.array(benchmark_returns)

        min_len = min(len(s), len(b))
        if min_len < 10:
            return {"error": "Insufficient observations for statistical significance testing (minimum 10 required)"}

        s_slice = s[:min_len]
        b_slice = b[:min_len]
        diff = s_slice - b_slice

        # Paired t-test
        t_stat, p_val_t = stats.ttest_1samp(diff, 0.0)

        # Wilcoxon signed-rank test (non-parametric)
        try:
            w_stat, p_val_w = stats.wilcoxon(diff)
        except Exception:
            w_stat, p_val_w = np.nan, np.nan

        is_significant_95 = bool(p_val_t < 0.05 and np.mean(diff) > 0)

        return {
            "mean_excess_return": round(float(np.mean(diff)), 6),
            "paired_t_statistic": round(float(t_stat), 4),
            "t_test_p_value": round(float(p_val_t), 4),
            "wilcoxon_statistic": round(float(w_stat), 4) if not np.isnan(w_stat) else None,
            "wilcoxon_p_value": round(float(p_val_w), 4) if not np.isnan(p_val_w) else None,
            "statistically_significant_at_95": is_significant_95
        }
