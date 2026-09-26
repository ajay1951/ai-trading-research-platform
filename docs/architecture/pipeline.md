# Quantitative Research & Production Pipeline Architecture
## AI Trading Research Platform

```text
Market Data
    ↓
Data Validation (OHLCV frequency, price bounds, timezone UTC)
    ↓
Feature Engineering (Point-in-time technical, volatility, momentum, volume)
    ↓
Temporal Dataset Construction (Purged Walk-Forward Optimization + Embargo)
    ↓
Baseline & ML Models (Buy & Hold, MA, LogReg, RF, LightGBM, LSTM, Transformer)
    ↓
Execution Timing (Signal at t close, Fill at t+1 open)
    ↓
Transaction Cost Engine (0.04% fee + 0.02% slippage = 12 bps round-trip)
    ↓
Risk Controls (Volatility-parity sizing, drawdown limits, circuit breaker)
    ↓
Statistical Evaluation (Monte Carlo 1,000 paths, Bootstrap Sharpe CI, Regime splits)
    ↓
Artifacts & Reports (artifacts/benchmark/, results/metrics.json)
    ↓
FastAPI Service Layer & Asynchronous Workers (Celery + Redis)
```

---

## 1. Data Engineering & Integrity Flow
1. **Source Data**: Hourly OHLCV candles retrieved from exchange endpoints.
2. **Automated Validator (`data/validator.py`)**:
   - Ensures zero timestamp gaps or flags missing bars.
   - Enforces price hierarchy: $\text{Low} \le \text{Open}, \text{Close} \le \text{High}$ and $\text{Price} > 0$.
   - Rejects negative volumes and non-monotonic timestamps.
3. **Cryptographic Manifest (`data/manifest.py`)**:
   - Generates SHA-256 fingerprint for dataset versioning (`artifacts/benchmark/run_metadata.json`).

## 2. Causal Feature Engineering
- Feature extractors (`features/price.py`, `volatility.py`, `momentum.py`, `volume.py`) enforce point-in-time calculation.
- Feature values at time $t$ depend solely on information available at or before $t$.
- Future candle mutation regression tests (`tests/leakage/test_future_candle_mutation.py`) assert that mutating future candle $t+k$ causes zero variation in historic features.

## 3. Temporal Validation & Splitter
- **Purged Walk-Forward Optimization (WFO)**:
  - Divides time-series into chronologically non-overlapping train, validation, and test folds.
  - **Embargo Buffer**: Maintains a 24-hour embargo gap after training periods to eliminate serial correlation leakage from rolling indicator lookbacks.

## 4. Execution Timing & Cost Engine
- **Point-in-Time Timing**: Signals computed using bar close $t$ are scheduled for execution at bar open $t+1$.
- **Trading Frictions**: Every simulated execution deducts 0.04% maker/taker fee and 0.02% slippage per fill.

## 5. Risk Controls & Circuit Breakers
- **Position Sizing (`risk/position_sizing.py`)**: Volatility-parity allocation sizing positions inversely proportional to realized volatility.
- **Drawdown Limit (`risk/drawdown.py`)**: Tracks high-water mark; enforces mandatory cash defense when drawdown reaches 10%.
- **Emergency Circuit Breaker (`risk/circuit_breaker.py`)**: Fast-tripping circuit breaker that immediately halts orders on adverse volatility spikes.

## 6. Service Architecture & Infrastructure
- **FastAPI Backend (`api/`)**: High-throughput REST API with Pydantic request validation and Request ID middleware.
- **Celery Worker (`tasks/`)**: Asynchronous worker pool for background backtests and training jobs.
- **Redis 7**: Sub-millisecond state caching and Celery message broker.
- **PostgreSQL 15**: Relational persistence for orders, ledger transactions, and experiment metadata.
- **Prometheus**: Metrics collection scraping `/metrics` for request counts and latency histograms.

## 7. Interactive Quantitative Workstation
- Real-time trading terminal built with Next.js and Tailwind CSS.
- Live order execution telemetry, TWAP order slicing visualization, active risk limits monitoring, and full blotter auditing.
- UI screenshots and visual interface references are archived in [docs/screenshots/](../screenshots/).
