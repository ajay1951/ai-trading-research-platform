# Quantitative Research Methodology & Architectural Specification

This document details the quantitative methodology, data engineering, statistical validation, and machine learning architectures implemented in the `ai-trading-research-platform`.

---

## 1. Objective

The objective of this research platform is to evaluate whether machine learning models (specifically gradient boosted decision trees, recurrent neural networks, and self-attention transformers) extract statistically significant, tradeable alpha from cryptocurrency market microstructure, and to rigorously test whether such signals survive real-world execution frictions (exchange fees, slippage, latency, and regime shifts).

---

## 2. Dataset Provenance & Integrity

### Primary Market Data
* **Asset Universe**: High-liquidity cryptocurrency perpetual swap contracts (`BTC/USDT`, `ETH/USDT`, `SOL/USDT`, `BNB/USDT`, `XRP/USDT`, `DOGE/USDT`, `ADA/USDT`, `AVAX/USDT`, `LINK/USDT`, `NEAR/USDT`, `LTC/USDT`, `DOT/USDT`, `SUI/USDT`).
* **Source**: Binance Public Market Data REST & WebSocket feeds (`binanceusdm`).
* **Timeframes**: 1-minute execution frequency aggregated to 1-hour and 15-minute decision horizons.
* **Date Range**: 2019-06-01 to 2026-08-06 (62,961 one-hour bars for BTC/USDT).
* **Versioning & Manifests**: Every dataset is cryptographically hashed with SHA-256 and registered in `data/manifests/` with row counts and date ranges before any experiment is conducted.

### Automated Validation Engine (`data/validator.py`)
Before ingestion into feature pipelines, raw datasets must pass:
1. **Price Hierarchy Integrity**: $\text{High} \ge \max(\text{Open}, \text{Close}, \text{Low})$ and $\text{Low} \le \min(\text{Open}, \text{Close}, \text{High})$ with $\text{Price} > 0$.
2. **Monotonicity**: Strict monotonically increasing UTC timestamps.
3. **Gap Detection**: Flagging missing bars greater than expected timeframe delta ($\Delta t = 1\text{h}$).
4. **Volume Anomaly Filter**: Rejecting negative volume or non-finite values.

---

## 3. Data Leakage Zero-Tolerance Policy

Time-series research is extraordinarily vulnerable to lookahead bias and data leakage. This platform enforces automated unit tests (`tests/`) preventing four common classes of leakage:

| Leakage Category | Risk Mechanism | Platform Safeguard & Automated Test |
| :--- | :--- | :--- |
| **Lookahead Bias** | Features at time $t$ incorporating prices from $t+1$ or future bars. | `tests/test_no_lookahead.py`: Mutating future bars $(t+1 \dots T)$ must cause exactly 0 change in features at $t$. |
| **Distribution Leakage** | Fitting scalers/normalizers across the whole dataset before train/test splitting. | `tests/test_feature_leakage.py`: Standardizers (`StandardScaler`, `MinMaxScaler`) are fit *strictly* on training slices. |
| **Label Leakage** | Target variables (forward returns) inadvertently included in feature matrix $X$. | `tests/test_label_leakage.py`: Asserts forward-looking keywords and shifted targets never exist in input feature space. |
| **Serial Correlation Leakage** | Autocorrelated returns bleeding between train and test boundaries. | `tests/test_temporal_split.py`: Enforces chronological boundaries and an **embargo buffer** (24+ bars) between train and test. |
| **Alignment Leakage** | Auxiliary time series forward-filling future values into past bars. | `tests/test_data_alignment.py`: Strict `direction='backward'` in `pd.merge_asof`. |

---

## 4. Feature Engineering (`features/`)

All features are point-in-time causal mathematical transformations of past OHLCV data:

### Price Features (`features/price.py`)
* **Multi-Horizon Returns**: $R_k(t) = \frac{P_t - P_{t-k}}{P_{t-k}}$ for $k \in \{1, 3, 6, 12, 24\}$ hours.
* **Log Returns**: $r_{\text{log}}(t) = \ln(P_t / P_{t-1})$.
* **Normalized Bar Spread**: $\text{Spread}_t = \frac{\text{High}_t - \text{Low}_t}{\text{Close}_t}$.
* **Body & Wick Ratios**: Quantifies buyer vs. seller control within individual candles.

### Volatility Features (`features/volatility.py`)
* **Realized Return Volatility**: Rolling standard deviation of returns over 12, 24, and 48 hours.
* **Normalized ATR**: $\frac{\text{ATR}_{14}(t)}{\text{Close}_t}$ capturing range expansion relative to price level.
* **Parkinson Extreme Value Volatility**:
  $$\sigma_P = \sqrt{\frac{1}{4 \ln 2} \cdot \frac{1}{N} \sum_{i=1}^N \left(\ln \frac{\text{High}_i}{\text{Low}_i}\right)^2}$$
* **Bollinger Bandwidth**: $\frac{\text{Upper} - \text{Lower}}{\text{SMA}_{20}}$ measuring volatility compression/expansion.

### Momentum Features (`features/momentum.py`)
* **RSI (14-period)**: Standard relative strength indicator.
* **MACD Normalized**: Difference between 12-EMA and 26-EMA divided by Close price to ensure cross-asset scale invariance.
* **Rate of Change (ROC)**: Momentum velocity over 6, 12, and 24 bars.
* **Donchian Channel Position**: Normalized position within the 20-period price envelope $[0.0, 1.0]$.

### Volume Features (`features/volume.py`)
* **Volume Ratio**: Volume relative to its 20-period moving average.
* **Volume Z-Score**: Standardized volume anomaly indicator.
* **Rolling VWAP Deviation**: $\frac{\text{Close}_t - \text{VWAP}_{24}(t)}{\text{VWAP}_{24}(t)}$.
* **On-Balance Volume (OBV) Z-Score**: Cumulative volume pressure normalized by rolling standard deviation.

---

## 5. Model Architectures & Baselines

Models are never evaluated in isolation. Every neural model is benchmarked against non-parametric and classical baselines on identical data slices:

1. **Buy & Hold (Passive Index)**: Long exposure maintained across entire test slice.
2. **Random Baseline**: Uniform random entry with identical holding times to measure baseline chance.
3. **20/50 SMA Crossover**: Trend-following moving average strategy.
4. **Logistic Regression**: Linear regularized classifier with L2 penalty.
5. **Random Forest Classifier**: Ensemble of 100 decision trees (max depth 6).
6. **LightGBM**: Gradient-boosted decision trees with histogram binning.
7. **PyTorch LSTM**: 2-layer Recurrent Neural Network with dropout (0.2), hidden dimension 48, processing 24-hour sequential windows.
8. **PyTorch Transformer**: Multi-head self-attention encoder (4 heads, 2 layers, d_model=48) mapping sequence representations to directional probability.

---

## 6. Execution Assumptions & Transaction Cost Modeling

A strategy that ignores transaction costs is meaningless. Every simulation in this platform strictly enforces:

* **Taker Exchange Fee**: 0.040% ($0.0004$) per fill (reflecting standard Binance VIP 0 taker tiers).
* **Execution Slippage**: 0.020% ($0.0002$) per trade to model bid/ask spread traversal and liquidity impact.
* **Total Round-Trip Friction**: **0.120% (12 basis points)** per closed trade.
* **Candle-Close Rule**: Orders execute at the Open of bar $t+1$ following a signal computed at the Close of bar $t$. Mid-candle intra-bar execution without tick data is strictly prohibited to avoid lookahead bias.

---

## 7. Validation Strategy: Purged Walk-Forward Optimization (WFO)

Standard K-Fold cross-validation leaks information in time-series data. We utilize a **5-Fold Purged Walk-Forward Evaluation**:

```
Fold 1: [─── TRAIN (2019-2021) ───] [EMBARGO] [─ TEST (2021) ─]
Fold 2: [────── TRAIN (2019-2022) ──────] [EMBARGO] [─ TEST (2022) ─]
Fold 3: [───────── TRAIN (2019-2023) ─────────] [EMBARGO] [─ TEST (2023) ─]
Fold 4: [──────────── TRAIN (2019-2024) ────────────] [EMBARGO] [─ TEST (2024) ─]
Fold 5: [─────────────── TRAIN (2019-2025) ───────────────] [EMBARGO] [─ TEST (2025-2026) ─]
```

* **Anchor Training**: Training set expands chronologically to reflect real-world operational retraining.
* **Strict Embargo Window**: 24+ bars between train end and test start to eliminate serial correlation bleed.
* **Out-of-Sample Evaluation**: Only performance on the test folds is reported.

---

## 8. Honest Limitations & Reality Disclosures

1. **Market Impact of Large Orders**: Backtests assume fills at market prices with fixed 2 bps slippage. Institutional orders exceeding $500,000 would require TWAP slicing and square-root law impact modeling.
2. **Regime Dependence**: Quantitative strategies calibrated in bull regimes (2020-2021) experience drawdown in grinding bear regimes (2022) unless dynamic cash defense or shorting is activated.
3. **Execution Latency**: Network round-trip latency to exchange matching engines (~20–120ms) can impact fill quality during high-volatility news events.
