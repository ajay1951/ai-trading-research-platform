# Walk-Forward Optimization Audit Report — EXP-WFO-001

## 1. Executive Summary
- **Experiment ID**: `EXP-WFO-001`
- **Asset**: `BTCUSDT` (1h timeframe)
- **Model**: LightGBM
- **Methodology**: 5-Fold Purged Walk-Forward Cross-Validation with 1% Embargo Buffer
- **Trading Frictions**: 0.04% maker fee + 0.02% slippage (12 bps round-trip)
- **Dataset Hash**: `151b72be3a6cb775776b8869eae8da13a45a10fc6dfd2c0ea855a36a288c4f68`
- **Commit SHA**: `5ee004cc8db4dd4164175d242538e2732c97fb64`

## 2. Walk-Forward Performance Summary
- **Profitable Folds**: 1 of 5 (20.0%)
- **Total Compounded Return**: -36.47%
- **Mean Fold Sharpe Ratio**: -2.13
- **Continuous OOS Max Drawdown**: 41.61%
- **Total OOS Trades Executed**: 388
- **Initial Balance**: $1000.00
- **Ending Balance**: $635.31

## 3. Fold-by-Fold Performance Table
| Fold | In-Sample Train Period | Out-of-Sample Test Period | Return (%) | Sharpe | Sortino | Max DD (%) | Trades |
|:---:|:---|:---|:---:|:---:|:---:|:---:|:---:|
| **1** | `2025-03-26 09:00:00+00:00 to 2025-06-04 21:00:00+00:00` | `2025-06-22 08:00:00+00:00 to 2025-09-08 08:00:00+00:00` | **-10.76%** | -3.98 | -2.08 | 11.86% | 102 |
| **2** | `2025-03-26 09:00:00+00:00 to 2025-08-14 10:00:00+00:00` | `2025-09-13 08:00:00+00:00 to 2025-11-30 08:00:00+00:00` | **-13.10%** | -2.53 | -1.54 | 19.22% | 97 |
| **3** | `2025-03-26 09:00:00+00:00 to 2025-10-23 23:00:00+00:00` | `2025-12-05 08:00:00+00:00 to 2026-02-21 08:00:00+00:00` | **-16.02%** | -3.22 | -1.59 | 19.46% | 84 |
| **4** | `2025-03-26 09:00:00+00:00 to 2026-01-02 12:00:00+00:00` | `2026-02-26 08:00:00+00:00 to 2026-05-15 08:00:00+00:00` | **-4.82%** | -1.80 | -0.83 | 8.57% | 65 |
| **5** | `2025-03-26 09:00:00+00:00 to 2026-03-14 02:00:00+00:00` | `2026-05-20 08:00:00+00:00 to 2026-08-06 08:00:00+00:00` | **+2.49%** | 0.89 | 0.30 | 5.30% | 40 |

## 4. Methodological Guards
1. **Purged Embargo Discipline**: An embargo buffer separating training and test periods eliminates lookahead contamination from rolling technical indicators.
2. **Strict Standardizer Fitting**: Feature scalers are fit strictly on training folds and applied out-of-sample.
3. **Execution Realism**: All entries and exits incur exchange taker fees and execution slippage.
