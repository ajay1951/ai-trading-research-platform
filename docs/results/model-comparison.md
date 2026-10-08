# Empirical Model Benchmark Comparison Report

**Audit Date:** October 2026  
**Evaluation Scope:** Out-Of-Sample (OOS) Test Fold (15% chronological split with 24-bar embargo buffer)  
**Execution Assumptions:** $t+1$ bar open execution, 0.04% maker fee (8 bps round-trip), 0.02% slippage (4 bps round-trip), Total Friction = 12 bps per turn.

---

## 1. Standardized Performance Benchmark Matrix

| Model | Return (%) | Ann. Return (%) | Volatility (%) | Sharpe Ratio | Sortino Ratio | Max DD (%) | Calmar | Win Rate (%) | Profit Factor | Trades | Turnover | Status / Assessment |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **Random Forest** | +1.12% | +4.58% | 1.21% | **3.77** | 559.97 | 0.10% | 10.76 | 100.0% | 99.00 | 4 | 0.18 | `UNSTABLE` (Sample size $N=4$ trades) |
| **PyTorch LSTM** | **+4.27%** | +17.65% | 10.57% | **1.67** | 1.40 | 4.73% | 0.90 | 66.7% | 2.55 | 30 | 1.33 | `VIABLE` ($N=30$, balanced risk) |
| **Buy & Hold** | +2.56% | +10.42% | 14.88% | **0.70** | 0.90 | 11.11% | 0.23 | 100.0% | 99.00 | 1 | 0.04 | `PASSIVE BENCHMARK` |
| **Transformer (Attention)** | -0.48% | -1.94% | 16.17% | **-0.12** | -0.09 | 3.89% | -0.12 | 46.0% | 1.77 | 50 | 2.22 | `UNDERPERFORMING` |
| **LightGBM** | -2.57% | -10.11% | 4.88% | **-2.07** | -0.91 | 5.10% | -0.50 | 53.3% | 1.18 | 30 | 1.33 | `NEGATIVE_EDGE` |
| **Logistic Regression** | -2.71% | -10.63% | 5.18% | **-2.05** | -0.64 | 4.19% | -0.65 | 50.0% | 0.90 | 18 | 0.80 | `LINEAR_UNDERFIT` |
| **Moving Average (20/50)** | -8.53% | -31.42% | 11.55% | **-2.72** | -2.83 | 12.55% | -0.68 | 38.5% | 0.56 | 13 | 0.58 | `CHOP_WHIPSAW` |
| **Random Baseline** | -31.01% | -81.25% | 6.93% | **-11.72** | -14.53 | 31.69% | -0.98 | 52.7% | 1.08 | 281 | 12.49 | `FRICTION_DESTROYED` |

---

## 2. Methodological Findings & Skeptical Analysis

1. **The Random Forest Anomaly (Sharpe 3.77):** Random Forest shows a Sharpe of 3.77, but this is generated from only **4 trades**. The evaluation engine's stability checks correctly flag this as statistically unstable ($N < 30$). The 100% win rate and 559.97 Sortino ratio are artifacts of sparse regime-specific filtering rather than sustainable statistical edge.
2. **PyTorch LSTM Viability:** LSTM produced +4.27% return with a Sharpe of 1.67 across 30 trades. Its sequential architecture successfully captured multi-bar momentum transitions better than memoryless tabular models.
3. **Friction Erosion on High Turnover:** The Random Baseline generated a 52.7% win rate and a gross profit factor of 1.08, but finished at **-31.01%** net return due to 281 trades compounding 12 bps in round-trip friction.
