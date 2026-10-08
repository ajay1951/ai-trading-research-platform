# Prioritized System Improvement Roadmap (P0 to P3)

**Audit Date:** October 2026  
**Auditor Profile:** Lead Quantitative Architect & Engineering Director  
**Guiding Principle:** Evidence first, changes second. No resume-fluff technologies.

---

## 1. P0 — Critical (Immediate Research Rigor & Correctness)

### P0-1: Cross-Sectional Multi-Asset Ranking Engine
- **Problem:** Assets are currently evaluated in isolated single-asset backtests without cross-sectional momentum ranking.
- **Evidence:** `training/universe_benchmark.py` iterates through symbols individually rather than ranking relative strength across the 13-asset universe.
- **Why it matters:** Single-asset 1h crypto models have low signal-to-noise. Cross-sectional momentum (e.g. Long Top 2 / Short Bottom 2) significantly reduces market beta and absorbs market-wide churn.
- **Files affected:** `training/universe_benchmark.py`, `models/portfolio_models.py`, `execution/live_momentum_daemon.py`.
- **Implementation complexity:** Medium (2–3 days).
- **Expected benefit:** Reduces market direction risk; captures cross-asset momentum dispersion.
- **Priority:** `P0`

### P0-2: Dynamic Transaction Cost & Non-Linear Market Impact Model
- **Problem:** Transaction costs currently use fixed 12 bps friction without size-dependent non-linear market impact.
- **Evidence:** `training/benchmark_suite.py:simulate_strategy_returns` applies a static linear scalar (`fee_rate + slippage`).
- **Why it matters:** Real-world trades suffer square-root law market impact ($\sigma \sqrt{V / \text{ADV}}$) as position size scales.
- **Files affected:** `training/benchmark_suite.py`, `core/tca.py`.
- **Implementation complexity:** Low-Medium (1 day).
- **Expected benefit:** Eliminates capacity over-estimation for larger simulated fund sizes.
- **Priority:** `P0`

---

## 2. P1 — High (ML Engineering, Robustness & Evaluation)

### P1-1: Hyperparameter Optimization with Purged Cross-Validation
- **Problem:** Tree and neural network hyperparameters are static constants across all walk-forward folds.
- **Evidence:** `training/walk_forward.py` sets fixed `n_estimators=100, max_depth=5` for LightGBM across all 5 folds.
- **Why it matters:** Dynamic market regimes require adaptive regularization (learning rate decay, tree depth control).
- **Files affected:** `training/walk_forward.py`.
- **Implementation complexity:** Medium (2 days).
- **Expected benefit:** Prevents overfitting to historical training splits while optimizing out-of-sample validation error.
- **Priority:** `P1`

### P1-2: Automated Test Coverage for WebSocket Streaming & Live Ingestion Faults
- **Problem:** WebSocket reconnects are mocked in unit tests, but edge cases involving corrupted L2 snapshots need end-to-end regression tests.
- **Evidence:** `tests/execution/test_websocket_reconnect.py` uses simple mock coroutines.
- **Why it matters:** Real exchanges disconnect frequently during volatility spikes.
- **Files affected:** `tests/execution/test_live_ingestion_edge_cases.py`.
- **Implementation complexity:** Medium (1–2 days).
- **Expected benefit:** Bulletproof live paper-trading uptime.
- **Priority:** `P1`

---

## 3. P2 — Medium (Observability & Developer Experience)

### P2-1: Live Model Drift & Population Stability Index (PSI) Tracker
- **Problem:** Model feature distribution shifts over time are not tracked in real-time Prometheus telemetry.
- **Evidence:** `api/main.py` tracks HTTP request latency and request counts, but not input feature distribution drift.
- **Why it matters:** Crypto feature distributions shift dramatically between bull, bear, and consolidation regimes.
- **Files affected:** `api/main.py`, `observability/prometheus.yml`.
- **Implementation complexity:** Low (1 day).
- **Expected benefit:** Automated alerts when live market data distribution diverges from training data.
- **Priority:** `P2`

### P2-2: Interactive Trade Visualizer with Multi-Timeframe Overlays
- **Problem:** Trade visualizer in `data/backtest_trades_viewer.html` displays single-timeframe trades without multi-timeframe regime indicators.
- **Evidence:** Visual inspection of `data/backtest_trades_viewer.html`.
- **Why it matters:** Enhances qualitative inspection of entry/exit timing for quant researchers.
- **Files affected:** `data/backtest_trades_viewer.html`.
- **Implementation complexity:** Low (1 day).
- **Expected benefit:** Faster qualitative review of model trade entries.
- **Priority:** `P2`

---

## 4. P3 — Optional (Nice-to-Have Extensions)

### P3-1: Multi-Broker Routing Interface (CCXT Pro / Bybit / OKX)
- **Problem:** Live daemon defaults strictly to Binance.
- **Evidence:** `execution/live_momentum_daemon.py:90` initializes `ccxt.binance`.
- **Why it matters:** Enables cross-exchange arbitrage and diversified exchange counterparty risk.
- **Files affected:** `execution/live_momentum_daemon.py`.
- **Implementation complexity:** Medium.
- **Priority:** `P3`
