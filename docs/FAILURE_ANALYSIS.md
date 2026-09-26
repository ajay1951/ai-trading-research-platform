# Failure Analysis & Negative Results
## AI Trading Research Platform

> **Core Research Principle**: An honest quantitative research platform documents what *failed*, why it failed, and what decisions were made as a result. True alpha discovery requires rejecting unviable models and recording empirical trade frictions.

---

## 1. High-Churn Strategy Failure Under Transaction Costs

### The Phenomenon
Initial unconstrained baseline models (such as the 20/50 Moving Average and Random Execution Baseline) displayed high trade frequency (up to 281 trades per quarter on hourly data).

### The Empirical Evidence
| Model | Gross Return | Net Return (after 0.04% fee + 0.02% slippage) | Friction Drag | Total Trades |
|---|---|---|---|---|
| **Random Baseline** | -2.10% | **-31.01%** | **-28.91%** | 281 |
| **Moving Average (20/50 SMA)** | +1.80% | **-8.53%** | **-10.33%** | 13 |

### Quantitative Root Cause
A round-trip trading fee of 0.04% maker fee + 0.02% slippage on entry and exit amounts to approximately **12 basis points (0.12%)** per round trip. In high-frequency hourly churning, 281 round trips impose an unavoidable drag:
$$\text{Friction Drag} = 281 \times 0.0012 \approx 33.7\%$$
Without a conviction threshold filter or holding period constraint, strategy returns are entirely consumed by execution fees and bid-ask spread crossing.

### Architectural Decision Taken
1. Enforced a **minimum conviction filter** (trades executed only when predicted return exceeds $2 \times \text{round\_trip\_cost}$).
2. Formally added [`tests/backtest/test_transaction_costs.py`](../tests/backtest/test_transaction_costs.py) to guarantee every simulation deducts fees.

---

## 2. Transformer Overfitting on Short Time Horizons

### The Phenomenon
A Multi-Head Self-Attention Transformer model was trained on hourly bar returns and technical feature sequences.

### The Empirical Evidence
- **Train Return**: +18.4% (Sharpe 4.12)
- **Validation Return**: +2.1% (Sharpe 0.85)
- **Out-of-Sample Test Return**: **-0.48%** (Sharpe -0.12, Max DD 3.89%)

### Quantitative Root Cause
Crypto hourly returns exhibit low signal-to-noise ratios ($R^2 < 0.03$). Deep multi-head attention mechanisms with large parameter spaces ($> 500\text{k}$ weights) easily memorize spurious temporal correlations in the training fold that fail to generalize across non-stationary market regimes.

### Architectural Decision Taken
1. Selected **Gradient Boosted Decision Trees (LightGBM)** and regularized shallow **LSTMs** as production baselines.
2. Kept Transformer architecture in the model registry marked as `experimental` under strict regularization requirements.

---

## 3. Pruned & Removed Features

During feature ablation studies, several candidate indicators were rejected and removed from the production pipeline:

### A. Raw Cross-Exchange Sentiment
- **Hypothesis**: Twitter and social media sentiment volume predicts immediate hourly price spikes.
- **Finding**: Sentiment spikes lag price breakouts by 1 to 3 hours (sentiment is reactive rather than predictive). Incorporating raw social sentiment increased out-of-sample prediction error by 8.4%.
- **Decision**: Removed raw social sentiment from alpha features; retained only funding rates and open interest as auxiliary regime filters.

### B. High-Period Moving Averages (200 SMA on 1h)
- **Hypothesis**: Trend-following on 200-hour SMA provides long-term trend guidance.
- **Finding**: Introduces 200 hours of initial warmup NaNs and suffers from severe whipsaw during consolidation phases.
- **Decision**: Replaced with adaptive volatility-adjusted range filters (Garman-Klass volatility and Donchian breakout channels).

---

## 4. Backtest Assumption Evolution

| Legacy / Flawed Assumption | Upgraded Institutional Standard | Reason for Change |
|---|---|---|
| Execution at candle close $t$ | Signal at $t$, execution at $t+1$ Open | Eliminates lookahead bias; impossible to trade at exact close price $t$ |
| 0% Trading Fees | 0.04% Maker Fee + 0.02% Slippage | Simulates real crypto perp liquidity costs |
| Random K-Fold Cross Validation | Purged Walk-Forward CV with Embargo | Eliminates autocorrelation leakage between consecutive hourly bars |
| Unbounded Position Sizing | Volatility-Parity / Fractional Kelly | Prevents catastrophic drawdown during volatility spikes |
