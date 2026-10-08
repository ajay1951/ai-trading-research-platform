# Portfolio Project Page: AI Trading Research & Model Governance Platform

## Hero Section
**AI Trading Research & Model Governance Platform**  
*A research-grade quantitative ML platform combining leakage-controlled walk-forward validation, realistic transaction-cost modeling, crash-resilient idempotent paper execution, continuous model health monitoring, and a 10-gate Champion/Challenger model governance framework with isolated shadow deployment and atomic rollback.*

[View Source on GitHub](https://github.com/ajay1951/ai-trading-research-platform) | [Read Architecture Decisions](https://github.com/ajay1951/ai-trading-research-platform/tree/main/docs/decisions) | [View Full Case Study](https://github.com/ajay1951/ai-trading-research-platform/blob/main/docs/case-study.md)

---

## The Problem
Many quantitative and applied ML systems fail upon deployment due to three critical engineering gaps:
1. **Research Leakage**: Overlapping data splits and lookahead bias produce inflated in-sample performance.
2. **Execution Friction & Unreliability**: Unmodeled transaction costs, network disconnects, and process crashes cause severe economic drift and duplicate fills.
3. **Absence of Model Governance**: Models are deployed based purely on historical backtest returns without tracking probability calibration, distribution drift, or operational inference latency.

---

## The Engineering Solution
We designed and validated an integrated platform solving these challenges across four pillars:

### 1. Leakage-Free Research Engine
- **5-Fold Purged Walk-Forward Optimization**: Enforces strictly chronological training and validation folds.
- **24-Bar Embargo Buffers**: Prevents autoregressive label overlap.
- **13-Asset Canonical Universe**: Cross-sectional ranking across top crypto assets (`BTC`, `ETH`, `SOL`, `BNB`, `XRP`, `DOGE`, `ADA`, `AVAX`, `LINK`, `NEAR`, `LTC`, `DOT`, `SUI`).

### 2. Transaction Cost Realism (P3-1F)
- **Institutional Cost Modeling**: Accounts for 10.0 bps exchange fee, 5.0 bps half-spread, and 6.38 bps volatility slippage (21.38 bps one-way / 42.76 bps round-trip).
- **Turnover Efficiency**: Proved that 48H rebalancing preserves positive net alpha (+11.96% return, 2.61 Sharpe) while high-frequency 1H rebalancing destroys capital (-90.8% return).

### 3. Crash-Resilient Execution & Reconciliation
- **Durable SQLite WAL OMS**: ACID-compliant persistence for all orders, fills, and account snapshots.
- **Idempotency**: Deterministic SHA-256 client order ID tokens prevent duplicate orders during network retries.
- **Continuous 3-Way Reconciliation**: Compares internal OMS against authoritative broker state on every cycle to detect and halt unmodeled drift.

### 4. MLOps Model Governance & Shadow Deployment
- **Model Registry**: Immutable records with SHA-256 artifact verification and unique Champion enforcement.
- **Continuous Intelligence**: Tracks Expected Calibration Error ($\text{ECE} \le 0.08$), Brier score, and Population Stability Index (PSI) drift.
- **10-Gate Fail-Closed Promotion Hierarchy**: Enforces artifact integrity, research validity, calibration, confidence monotonicity, health, economics, risk limits, latency ($\le 50\text{ms}$), shadow duration, and governance approvals.
- **Isolated Shadow Deployment**: Proven bitwise non-interference between Champion and Challenger models over a 75.8-day (1819 hourly bars) longitudinal out-of-sample study.
- **Atomic Rollback**: One-click transactional pointer reinstatement of previous approved Champions.

---

## Hard Performance & Reliability Numbers
- **Total Automated Tests**: 402 / 402 passing Pytest tests (100% pass rate, 0 regressions).
- **Longitudinal Shadow Evaluation**: 1,819 unseen hourly bars (75.8 days) across 23,647 point-in-time predictions.
- **Directional Agreement**: 98.13% behavioral agreement between Champion and Challenger.
- **Inference Latency**: P50 = 1.21 ms, P95 = 1.89 ms (Sub-2ms SLA compliance).
- **Prediction Reliability**: 0.0% error rate, 0 missing or NaN predictions.

---

## Negative Results: Research Integrity in Practice
We treat negative results as vital research findings:
- **1H Rebalancing**: Failed under transaction costs (-90.8% return).
- **Long/Short Top-2/Bottom-2**: Failed due to borrow fee asymmetry and short squeeze risk.
- **Inverse-Volatility Sizing**: Failed to outperform equal 50/50 weighting on a risk-adjusted basis.
- **Challenger B Promotion**: Rejected by Gate 3 and Gate 7 due to poor calibration ($\text{ECE} = 0.18$) and excessive drawdown (32.0%) despite higher gross return.
- **P4-1 Challenger A Outcome**: Preserved +5.66% more capital than Champion during a macro downtrend, but was correctly **REJECTED** by Gate 7 because absolute drawdown exceeded the 20% limit.

---

## Technical Stack
- **Core Languages**: Python 3.12, SQL
- **ML Frameworks**: LightGBM, Scikit-learn, NumPy, Pandas
- **Backend & APIs**: FastAPI, Pydantic, Uvicorn
- **Persistence**: SQLite WAL (ACID transactions)
- **Monitoring & SRE**: Prometheus, Grafana, Structured JSON Logging
- **Test Infrastructure**: Pytest, Pytest-Asyncio, Git
