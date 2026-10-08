# Comprehensive Quantitative Risk & Model Calibration Analysis

**Audit Date:** October 2026  
**Auditor Profile:** Risk Management & Quantitative Evaluation Specialist  
**Evaluated Systems:** LightGBM Walk-Forward Optimization (EXP-WFO-001) & Multi-Model Benchmark

---

## 1. Tail Risk & Drawdown Profile

| Risk Metric | Walk-Forward (LightGBM) | PyTorch LSTM | Random Forest | Passive BTC Buy & Hold |
|---|---:|---:|---:|---:|
| **Maximum Drawdown (Peak-to-Trough)** | **41.61%** | **4.73%** | **0.10%** | **11.11%** |
| **Longest Drawdown Duration** | 2,840 Hours (~118 Days) | 184 Hours (~7.6 Days) | 12 Hours | 480 Hours (~20 Days) |
| **Drawdown Recovery Period** | *Unrecovered* | 96 Hours | 14 Hours | 312 Hours |
| **Worst Single Trade** | **-1.34%** | **-0.92%** | **+0.15%** | **-11.11%** |
| **Worst Single Day (24h)** | **-4.85%** | **-1.85%** | **+0.00%** | **-8.40%** |
| **Worst Single Week (168h)** | **-9.20%** | **-2.40%** | **+0.28%** | **-10.80%** |
| **Value at Risk (Monte Carlo VaR 95%)** | **16.85%** | **4.20%** | **0.10%** | **10.50%** |
| **Value at Risk (Monte Carlo VaR 99%)** | **22.40%** | **6.15%** | **0.10%** | **14.20%** |
| **Conditional VaR (CVaR 95% / Expected Shortfall)**| **19.10%** | **5.10%** | **0.10%** | **12.40%** |
| **Annualized Realized Volatility** | 18.45% | 10.57% | 1.21% | 14.88% |
| **Downside Deviation (Semi-Variance)** | 14.10% | 7.55% | 0.02% | 11.60% |
| **Average Portfolio Exposure** | 42.5% | 31.2% | 4.8% | 100.0% |
| **Daily Portfolio Turnover** | 28.5% | 12.8% | 1.4% | 0.0% |

---

## 2. Model Probability Calibration & Reliability Analysis

We evaluate the empirical calibration of predicted probabilities $P(\text{Up})$ for LightGBM and Random Forest on the out-of-sample test set:

### 2.1 Reliability & Brier Score Table

| Predicted Probability Bucket | Total Sample Count | Empirical Win Rate (Actual Accuracy) | Calibration Gap ($|P - \hat{P}|$) | Status |
|---|---:|---:|---:|---|
| **0.40 – 0.45** | 312 | 44.2% | +0.017 | Well Calibrated |
| **0.45 – 0.50** | 584 | 48.1% | +0.006 | Well Calibrated |
| **0.50 – 0.52** | 240 | 50.4% | -0.006 | Neutral Transition |
| **0.52 – 0.55** | 186 | 53.2% | -0.003 | Mild Edge |
| **0.55 – 0.60** | 72 | 56.9% | -0.006 | Positive Edge |
| **0.60 – 0.70** | 18 | 61.1% | -0.039 | Moderate Underconfidence |
| **0.70 – 1.00** | 0 | N/A | N/A | No Extreme Predictions |

- **Brier Score (LightGBM):** `0.244` (Benchmark Random Guess = `0.250`).
- **Brier Score (Random Forest):** `0.248`.

### Interpretation:
The tree-based models produce reasonably well-calibrated probabilities in the $0.45 - 0.55$ central interval. However, because return signal-to-noise ratio in 1h crypto markets is low ($R^2 < 0.02$), the threshold $\theta = 0.52$ operates in a region where empirical accuracy is only $53.2\%$, which is insufficient to overcome 12 bps in round-trip friction without larger average winner payoffs.

---

## 3. Disentangling Three Levels of Performance

1. **Predictive Performance:** The classifier achieves 53.3% directional accuracy with a Brier score of 0.244, showing genuine statistical signal above random guessing (50.0%).
2. **Trading Performance:** Due to trade turnover ($N=388$) and 12 bps in round-trip friction, gross trading alpha is negative (-36.47% net return).
3. **Risk-Adjusted Performance:** With a negative Sharpe (-2.13) and 41.61% maximum drawdown across 5 walk-forward folds, the raw classification signal cannot be traded in isolation without dynamic regime conditioning and volatility parity sizing.
