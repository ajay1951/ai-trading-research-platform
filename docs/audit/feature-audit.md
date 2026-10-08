# Feature Engineering Audit & Causality Registry

**Audit Date:** October 2026  
**Auditor Profile:** Quantitative Feature Engineer & ML Quality Assessor  
**Scope:** All technical, statistical, momentum, volatility, and volume indicators in the platform.

---

## 1. Feature Registry & Causality Table

| Feature Name | Domain | Source Columns | Lookback Window (Bars) | Formula / Methodology | Causal (No Lookahead) | Leakage Risk | Used By Models | Status |
|---|---|---|---:|---|:---:|:---:|---|:---:|
| `return_1` | Price | `close` | 1 | $C_t / C_{t-1} - 1$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `return_3` | Price | `close` | 3 | $C_t / C_{t-3} - 1$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `return_6` | Price | `close` | 6 | $C_t / C_{t-6} - 1$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `return_12` | Price | `close` | 12 | $C_t / C_{t-12} - 1$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `return_24` | Price | `close` | 24 | $C_t / C_{t-24} - 1$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `log_return_1` | Price | `close` | 1 | $\ln(C_t / C_{t-1})$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `bar_spread` | Price | `high`, `low`, `close` | 1 | $(H_t - L_t) / C_t$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `body_ratio` | Price | `open`, `high`, `low`, `close` | 1 | $(C_t - O_t) / (H_t - L_t + \epsilon)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `upper_wick_ratio` | Price | `open`, `high`, `low`, `close` | 1 | $(H_t - \max(O_t, C_t)) / (H_t - L_t + \epsilon)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `lower_wick_ratio` | Price | `open`, `high`, `low`, `close` | 1 | $(\min(O_t, C_t) - L_t) / (H_t - L_t + \epsilon)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `volatility_12` | Volatility | `close` | 12 | $\sigma(\text{returns}, 12)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `volatility_24` | Volatility | `close` | 24 | $\sigma(\text{returns}, 24)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `volatility_48` | Volatility | `close` | 48 | $\sigma(\text{returns}, 48)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `atr_14` | Volatility | `high`, `low`, `close` | 14 | $\text{SMA}(\text{TrueRange}, 14)$ | Yes | None | Sizing Engine, Models | `ACTIVE` |
| `atr_norm` | Volatility | `high`, `low`, `close` | 14 | $\text{ATR}_{14} / C_t$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `parkinson_vol_24` | Volatility | `high`, `low` | 24 | $\sqrt{\frac{1}{4 \ln 2} \frac{1}{24} \sum \ln(H_i / L_i)^2}$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `bollinger_bandwidth`| Volatility | `close` | 20 | $(\text{Upper}_{20} - \text{Lower}_{20}) / \text{SMA}_{20}$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `rsi_14` | Momentum | `close` | 14 | $100 - (100 / (1 + RS))$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `macd` | Momentum | `close` | 26 | $(\text{EMA}_{12} - \text{EMA}_{26}) / C_t$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `macd_signal` | Momentum | `close` | 35 | $\text{EMA}_9(\text{MACD}) / C_t$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `macd_hist` | Momentum | `close` | 35 | $(\text{MACD} - \text{Signal}) / C_t$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `roc_6` | Momentum | `close` | 6 | $(C_t - C_{t-6}) / C_{t-6}$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `roc_12` | Momentum | `close` | 12 | $(C_t - C_{t-12}) / C_{t-12}$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `roc_24` | Momentum | `close` | 24 | $(C_t - C_{t-24}) / C_{t-24}$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `stoch_k` | Momentum | `high`, `low`, `close` | 14 | $100 \times \frac{C_t - \min(L, 14)}{\max(H, 14) - \min(L, 14)}$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `stoch_d` | Momentum | `high`, `low`, `close` | 17 | $\text{SMA}_3(\text{stoch\_k})$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `donchian_pos_20` | Momentum | `high`, `low`, `close` | 20 | $\frac{C_t - \min(L, 20)}{\max(H, 20) - \min(L, 20)}$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `volume_ratio_20` | Volume | `volume` | 20 | $V_t / \text{SMA}(V, 20)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `volume_zscore_20` | Volume | `volume` | 20 | $(V_t - \text{mean}(V, 20)) / \sigma(V, 20)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `vwap_deviation_24` | Volume | `high`, `low`, `close`, `volume` | 24 | $(C_t - \text{VWAP}_{24}) / \text{VWAP}_{24}$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |
| `obv_zscore_20` | Volume | `close`, `volume` | 20 | $(\text{OBV}_t - \text{mean}(\text{OBV}, 20)) / \sigma(\text{OBV}, 20)$ | Yes | None | LR, RF, LGBM, LSTM, Transformer | `ACTIVE` |

---

## 2. Leakage Protection Verification

1. **Window Causality:** Every rolling calculation strictly references index range $[t - W + 1 : t]$. No negative shifts or future-centering operations are present.
2. **Scaler Disjointness:** Feature scalers (`StandardScaler`) are instantiated and `.fit()` strictly on training slices $X_{\text{train}}$. In the test/validation phase, only `.transform()` is invoked. Tested via `tests/leakage/test_scaler_fit_only_train.py`.
3. **Future Candle Mutation Invariance:** Verified by mutating candle $t+1$ and confirming that feature vector at bar $t$ remains numerically identical (`tests/leakage/test_future_candle_mutation.py`).
4. **Target Label Separation:** The target column ($4$-hour forward return direction: $(C_{t+4} - C_t)/C_t > 0.002$) is strictly isolated from the feature feature matrix $X$ (`tests/leakage/test_label_leakage.py`).
