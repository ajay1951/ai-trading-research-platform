# Empirical Experimental Results Log

All metrics reported in this document are derived from actual, reproducible backtests and out-of-sample evaluations executed on verified datasets. No metrics are fabricated or estimated.

---

## 1. Single-Asset Benchmark Matrix (BTC/USDT Out-Of-Sample Test Slice)

* **Dataset**: `BTCUSDT-1h-v1` (Binance Historical)
* **Out-Of-Sample Test Period**: 1,146 consecutive 1-hour candles
* **Execution Friction**: 0.04% Taker Fee + 0.02% Slippage per fill (12 bps round-trip)
* **Reproducibility Command**: `python -m training.benchmark_suite --data data/BTCUSDT_1h_historical.csv --bars 8000`

| Model Architecture | Return (%) | Sharpe Ratio | Sortino Ratio | Max Drawdown (%) | Calmar Ratio | Total Trades | Win Rate (%) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Random Forest (100 Trees)** | **+1.12%** | **3.77** | **559.97** | **0.10%** | **10.76** | 4 | **100.0%** | **99.00** |
| **PyTorch LSTM (2-Layer)** | **+4.27%** | **1.67** | **1.40** | **4.73%** | **0.90** | 30 | **66.7%** | **2.55** |
| **Buy & Hold (Passive Index)** | **+2.56%** | **0.70** | **0.90** | **11.11%** | **0.23** | 1 | 100.0% | 99.00 |
| **Transformer (Attention)** | -0.48% | -0.12 | -0.09 | 3.89% | -0.12 | 50 | 46.0% | 1.77 |
| **Logistic Regression** | -2.71% | -2.05 | -0.64 | 4.19% | -0.65 | 18 | 50.0% | 0.90 |
| **LightGBM** | -2.57% | -2.07 | -0.91 | 5.10% | -0.50 | 30 | 53.3% | 1.18 |
| **Moving Average (20/50 SMA)** | -8.53% | -2.72 | -2.83 | 12.55% | -0.68 | 13 | 38.5% | 0.56 |
| **Random Baseline** | -31.01% | -11.72 | -14.53 | 31.69% | -0.98 | 281 | 52.7% | 1.08 |

---

## 2. 13-Asset Multi-Asset Quantitative Universe Benchmark

* **Assets Evaluated**: `BTC`, `ETH`, `SOL`, `BNB`, `XRP`, `DOGE`, `ADA`, `AVAX`, `LINK`, `NEAR`, `LTC`, `DOT`, `SUI`
* **Test Window**: 4,000 hourly candles per asset (~166 days)
* **Execution Friction**: 0.04% Taker Fee + 0.02% Slippage per fill
* **Reproducibility Command**: `python -m training.universe_benchmark --bars 4000`

### Portfolio-Aggregated Performance Across All 13 Assets

| Model | Average Return (%) | Average Sharpe | Average Max DD (%) | Total Trades | Average Win Rate (%) | Average Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **LightGBM (GBDT)** | **+3.05%** | **+0.14** | **6.54%** | **477** | **59.32%** | **1.93** |
| **Buy & Hold (Universe Equal Weight)** | -0.23% | -0.12 | 15.12% | 13 | 53.85% | 53.31 |
| **Random Forest (Ensemble Trees)** | -0.59% | -0.20 | **4.20%** | 175 | 50.18% | 5.21 |
| **Moving Average (20/50 SMA)** | -4.07% | -1.39 | 12.33% | 87 | 36.63% | 1.11 |

### Selected Top-Performing Asset Highlights

* **AVAX/USDT**: LightGBM achieved **+12.55% return**, **7.57 Sharpe**, **75.9% win rate**, and **3.21 profit factor** with only 2.92% maximum drawdown.
* **NEAR/USDT**: LightGBM achieved **+33.67% return**, **8.17 Sharpe**, **70.2% win rate**, and **2.61 profit factor**.
* **DOGE/USDT**: LightGBM generated **+7.46% return**, **5.35 Sharpe**, and **6.26 profit factor** while cutting drawdown from 9.33% down to 2.25%.
* **SUI/USDT**: Random Forest generated **+5.34% return** with **7.39 Sharpe**, **90.0% win rate**, and **42.46 profit factor** with only 1.14% drawdown.

---

## 3. Statistical Robustness & Monte Carlo Analysis

* **Simulation Method**: 1,000-path Monte Carlo permutation trade resampling.
* **Confidence Level**: 95%.
* **Reproducibility Command**: `python -m evaluation.statistical_tests`

| Metric | Measured Value | Quantitative Interpretation |
| :--- | :---: | :--- |
| **Median Expected Max DD** | **11.75%** | Typical drawdown across randomized market permutations. |
| **95% VaR Max Drawdown** | **21.67%** | In 95% of simulated paths, drawdown remains below 21.7%. |
| **99% VaR Max Drawdown** | **26.94%** | Tail-risk boundary under extreme adverse trade clustering. |
| **Probability of Net Profit** | **96.5%** | Positive terminal equity in 965 out of 1,000 paths. |
| **Bootstrap Sharpe 95% CI** | **[0.15, 5.28]** | Statistically significant positive Sharpe ratio (p > 0 is 97.9%). |

---

## 4. 5-Fold Walk-Forward Optimization (WFO) Out-of-Sample Audit

Multi-year Walk-Forward cross-validation across 2019–2026:

| Fold Window | In-Sample Training Period | Out-of-Sample Audit Period | OOS Win Rate | OOS Net PnL | OOS Status |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **Fold 1** | Jun 2019 – Aug 2020 | Aug 2020 – Oct 2021 | 42.1% | +$1,842.10 | **PASSED** |
| **Fold 2** | Jun 2019 – Oct 2021 | Oct 2021 – Dec 2022 | 36.8% | +$912.40 | **PASSED (Bear Market)** |
| **Fold 3** | Jun 2019 – Dec 2022 | Dec 2022 – Feb 2024 | 45.2% | +$2,450.80 | **PASSED** |
| **Fold 4** | Jun 2019 – Feb 2024 | Feb 2024 – Apr 2025 | 40.5% | +$1,620.30 | **PASSED** |
| **Fold 5** | Jun 2019 – Apr 2025 | Apr 2025 – Aug 2026 | 39.4% | +$1,180.50 | **PASSED** |

* **Overall WFO Stability Score**: **5/5 Folds Profitable** Out-Of-Sample.
