# Cross-Sectional Turnover & Rebalance-Frequency Analysis

**Experiment ID:** `EXP-CS-RB-001`  
**Audit Date:** October 2026  
**Asset Universe:** 13 Top-Liquidity Crypto Assets (`BTC`, `ETH`, `SOL`, `BNB`, `XRP`, `DOGE`, `ADA`, `AVAX`, `LINK`, `NEAR`, `LTC`, `DOT`, `SUI`)  
**Methodology:** 5-Fold Walk-Forward Purged Cross-Validation with 24-Bar Embargo, $t+1$ Executions, Standardized 12 bps Round-Trip Frictions (4 bps Maker Fee + 2 bps Slippage per leg).  
**Baseline Reference:** `EXP-CS-001` (1-hour rebalance cross-sectional ranking).

---

## 1. Executive Summary

In baseline experiment `EXP-CS-001`, 1-hour cross-sectional ranking generated strong gross directional alpha (+9.88% Long-Only, +26.08% Long/Short) but suffered fatal friction decay (-27.27% net Long-Only, -48.69% net Long/Short) driven by excessive turnover (daily turnover of 21.5x and 43.2x respectively).

This experiment (`EXP-CS-RB-001`) isolates **rebalance frequency** ($1\text{h}, 4\text{h}, 12\text{h}, 24\text{h}$) as the primary independent variable.

### Key Finding:
**Decreasing rebalance frequency from 1-hour to 24-hours eliminates >91% of trading friction and yields consistently positive net performance across all 5 walk-forward folds for Long-Only Top 2 (+4.10% mean return, 5/5 profitable folds, Sharpe 1.16).**

---

## 2. Rebalance Frequency Comparison Matrix

| Strategy | Rebalance Freq | Interval (Bars) | Daily Turnover (x) | Avg Hold Period (h) | Gross Return (%) | Friction Drag (%) | Net Return (%) | Net Sharpe | Max DD (%) | Profitable Folds |
|---|---|---|---|---|---|---|---|---|---|---|
| **Long-Only (Top 2)** | **1H** | 1 | 21.48 | 2.24h | +9.88% | 37.15% | **-27.27%** | -5.61 | 33.92% | 0/5 |
| **Long-Only (Top 2)** | **4H** | 4 | 7.18 | 6.73h | +1.79% | 12.43% | **-10.64%** | -1.78 | 21.53% | 1/5 |
| **Long-Only (Top 2)** | **12H** | 12 | 3.12 | 15.74h | +7.89% | 5.40% | **+2.50%** | +0.85 | 16.50% | 3/5 |
| **Long-Only (Top 2)** | **24H** | 24 | 1.75 | 28.60h | +7.12% | 3.02% | **+4.10%** | **+1.16** | **15.95%** | **5/5** |
| **Long/Short (Top 2 / Bottom 2)** | **1H** | 1 | 43.22 | 2.31h | +26.08% | 74.78% | **-48.69%** | -12.27 | 51.38% | 0/5 |
| **Long/Short (Top 2 / Bottom 2)** | **4H** | 4 | 14.67 | 7.23h | +6.75% | 25.37% | **-18.62%** | -3.72 | 27.81% | 1/5 |
| **Long/Short (Top 2 / Bottom 2)** | **12H** | 12 | 6.31 | 18.86h | +8.23% | 10.91% | **-2.68%** | -0.75 | 19.68% | 2/5 |
| **Long/Short (Top 2 / Bottom 2)** | **24H** | 24 | 3.62 | 35.93h | +10.43% | 6.26% | **+4.18%** | **+0.78** | **15.90%** | **3/5** |

---

## 3. Rank Persistence & Autocorrelation

| Metric | 1-Hour Lag | 4-Hour Lag | 12-Hour Lag | 24-Hour Lag |
|---|---:|---:|---:|---:|
| **Spearman Rank Autocorrelation ($\rho$)** | 0.6672 | 0.4340 | 0.1833 | 0.0716 |
| **Top-2 Jaccard Overlap Fraction** | 45.68% | 30.90% | 17.96% | 12.84% |
| **Average Top-2 Stay Duration** | 2.24 hours | — | — | — |
| **Median Top-2 Stay Duration** | 1.00 hour | — | — | — |
| **Mean Rank Transitions / Fold** | 509 transitions | — | — | — |

### Key Insight on Rank Dynamics:
- The ML model's cross-sectional predictions exhibit moderate 1-hour autocorrelation ($\rho = 0.67$), but continuous hourly rebalancing caused rapid micro-swaps among close rankers (mean duration $\approx 2.24\text{h}$).
- Sampling target weights every 24 hours forces positions to be held for an average of 28.6 to 35.9 hours, capturing the underlying multi-day macro momentum while extinguishing 91.9% of redundant transaction friction.

---

## 4. Fold-by-Fold Performance (24-Hour Rebalance)

| Fold | Out-of-Sample Period | LO Net Return (%) | LO Gross Return (%) | LO Costs (%) | LO Sharpe | LO Max DD (%) | LS Net Return (%) | LS Sharpe |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **Fold 1** | 2025-06-08 → 2025-07-07 | +7.27% | +10.44% | 3.17% | +1.92 | 11.52% | +2.00% | +0.75 |
| **Fold 2** | 2025-07-09 → 2025-08-07 | +6.21% | +9.30% | 3.08% | +1.46 | 18.24% | -8.88% | -1.13 |
| **Fold 3** | 2025-08-09 → 2025-09-07 | +2.20% | +5.24% | 3.05% | +0.77 | 10.92% | -6.75% | -1.23 |
| **Fold 4** | 2025-09-08 → 2025-10-07 | +3.49% | +6.49% | 2.99% | +1.07 | 18.29% | +0.48% | +0.42 |
| **Fold 5** | 2025-10-09 → 2025-11-07 | +1.32% | +4.15% | 2.83% | +0.60 | 20.80% | +34.03% | +5.09 |
| **Mean** | — | **+4.10%** | **+7.12%** | **3.02%** | **+1.16** | **15.95%** | **+4.18%** | **+0.78** |

---

## 5. Cost Attribution Analysis

Under 1-hour rebalancing:
- **Fees:** 24.77% of capital per fold.
- **Slippage:** 12.38% of capital per fold.
- **Total Friction:** 37.15% per fold (Long-Only), completely overwhelming the +9.88% gross return.

Under 24-hour rebalancing:
- **Fees:** 2.01% of capital per fold.
- **Slippage:** 1.01% of capital per fold.
- **Total Friction:** 3.02% per fold (Long-Only).
- **Net Margin:** +4.10% net profit retained after all transaction costs.
