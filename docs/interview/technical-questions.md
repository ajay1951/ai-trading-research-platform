# Quantitative & ML Engineering Technical Interview Guide

**Audit Date:** October 2026  
**Auditor Profile:** Skeptical Technical Interviewer & Quantitative Researcher  
**Scope:** Technical interview questions and authoritative answers derived solely from the actual codebase.

---

### Q1: Why did you implement Purged Walk-Forward Cross-Validation instead of standard K-Fold CV?
**Answer:** Standard K-Fold randomly shuffles data or evaluates past data using models trained on future folds, introducing extreme lookahead bias. Even simple time-series splitting can suffer from serial correlation if adjacent samples share overlapping feature lookbacks. Purged walk-forward validation enforces strict temporal ordering ($t_0 \to t_1 \to t_2$) where each test fold is completely Out-Of-Sample (OOS) relative to the training history, accurately simulating live forward deployment.

### Q2: Why is an Embargo buffer necessary between train and test splits?
**Answer:** Financial returns exhibit short-term serial autocorrelation, and multi-bar technical features (e.g. 24-bar volatility or 26-bar MACD) span across split boundaries. If a test set begins immediately at bar $T+1$ without an embargo, information from the training tail leaks into the test fold's feature calculation. An embargo of 24 bars (`data/splitting.py:TemporalSplitter`) guarantees complete statistical separation.

### Q3: How is data leakage concretely prevented in your feature pipeline?
**Answer:**
1. **Window Causality:** Every feature formula in `features/technical.py` is calculated strictly over historical lookback slices `[:t]`.
2. **Scaler Isolation:** `StandardScaler` is fitted *only* on $X_{\text{train}}$ and merely transforms $X_{\text{val}}$ and $X_{\text{test}}$ (`tests/leakage/test_scaler_fit_only_train.py`).
3. **Future Mutation Invariance:** Unit tests (`tests/leakage/test_future_candle_mutation.py`) mutate bar $t+1$ and assert that feature vector $X_t$ is mathematically invariant.
4. **Target Separation:** The forward target return is computed after feature extraction and excluded from the feature matrix.

### Q4: Why do you enforce $t+1$ bar open execution instead of $t$ bar close?
**Answer:** In realistic trading, a signal generated at the close of candle $t$ cannot be executed at price $C_t$ because calculating features and submitting an order takes non-zero latency. Executing at $O_{t+1}$ (the open of the next bar) eliminates "impossible execution" lookahead bias and represents real-world market entry.

### Q5: How are transaction fees and slippage modeled in the backtest engine?
**Answer:** In `training/benchmark_suite.py:simulate_strategy_returns`, every state change incurs:
- **Maker/Taker Fee:** 0.04% per fill (8 bps round-trip).
- **Slippage Deduction:** 0.02% adverse price impact (4 bps round-trip).
- Total round-trip friction is 12 bps (0.12%), directly deducted from portfolio equity upon position entry and exit.

### Q6: Why use Stationary Block Bootstrapping instead of standard IID bootstrap for Sharpe ratios?
**Answer:** Standard IID bootstrapping assumes observations are independent and identically distributed. Financial returns have volatility clustering and autoregressive dynamics. Block bootstrapping (`evaluation/statistical_tests.py:bootstrap_sharpe_ci`) resamples contiguous blocks of 24 bars, preserving the underlying autocorrelation structure when calculating 95% confidence intervals.

### Q7: Why can a Sharpe ratio of 3.77 or 4.08 from 4 to 9 trades be misleading?
**Answer:** A Sharpe ratio is annualized by $\sqrt{8760}$ (for 1h data). When a strategy executes very few trades (e.g. $N=4$), the denominator (standard deviation of periodic returns) is near zero because the strategy sat in cash for 98% of the time. The evaluation engine's `check_metric_stability()` flags this small-sample clustering as statistically unstable.

### Q8: Why did your walk-forward experiment produce a -36.47% out-of-sample return despite passing all tests?
**Answer:** This is an honest empirical result. A 1h directional classifier trained on standard technical features achieves ~53% raw accuracy. However, across 388 trades, trading turnover and 12 bps in round-trip friction compound to -36.47% net return. Hiding or over-optimizing this result would be bad science. It demonstrates that raw 1h tabular signals cannot be traded aggressively without higher-timeframe regime filters and volatility parity sizing.

### Q9: What happens when transaction costs increase from 0 bps to 50 bps?
**Answer:** At 0 bps (frictionless), the strategy shows +14.82% return with a Sharpe of +1.42. At the breakeven boundary of ~6.5 bps, net edge becomes zero. At 12 bps, return is -36.47%, and at 50 bps, return drops to -88.60%. This stress test proves that execution costs are the primary determinant of high-turnover strategy viability.

### Q10: How does the system handle exchange failures or disconnects in live paper trading?
**Answer:**
1. **Network Retries:** Exponential backoff on CCXT errors.
2. **Circuit Breakers:** `CircuitBreaker` trips after 5 consecutive errors or if realized slippage exceeds 1.5%, halting order emission (`risk/circuit_breaker.py`).
3. **State Recovery:** The daemon persists active positions and wallet balances to `data/live_state.json` on every loop, automatically recovering state upon reboot (`execution/live_momentum_daemon.py`).

### Q11: What architectural changes would be mandatory before deploying real institutional capital?
**Answer:**
1. Real-time WebSocket order book L2/L3 streaming instead of REST polling.
2. Dynamic Transaction Cost Analysis (Almgren-Chriss or Kyle's Lambda market impact).
3. Cross-sectional multi-asset factor ranking (e.g., long top decile, short bottom decile).
4. Multi-party execution signing and institutional custody API integration (e.g., Fireblocks / Coinbase Prime).
