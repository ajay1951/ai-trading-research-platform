# Recruiter One-Pager: AI Trading Research & Model Governance Platform

## 1. Executive Summary
A quantitative machine learning platform built in Python that unifies **leakage-controlled walk-forward research validation**, **transaction-cost modeling**, **crash-resilient idempotent paper execution**, **real-time model calibration/drift monitoring**, and a **10-gate Champion/Challenger model governance framework with isolated shadow deployment and atomic rollback**.

**Primary Message**: Demonstrates end-to-end capabilities to build, validate, operate, monitor, govern, and safely evolve production-grade ML systems in high-stakes environments.

---

## 2. Key Engineering Highlights & Hard Numbers

- **Data & Research Integrity**: 5-Fold Purged Walk-Forward Optimization with 24-hour embargo buffers across a 13-asset universe. Zero lookahead bias proven via automated future-mutation unit tests.
- **Realistic Cost Modeling (P3-1F)**: Modeled 21.38 bps one-way / 42.76 bps round-trip friction. Demonstrated why 1H rebalancing collapsed (-90.8% net return) while 48H cadence preserved edge (+11.96% net return, 2.61 Sharpe).
- **Crash-Resilient Paper OMS**: SQLite WAL-backed transactional Order Management System with deterministic SHA-256 deduplication tokens, continuous 3-way external broker reconciliation, and automated crash recovery.
- **Continuous Model Intelligence (P3-3)**: Real-time Expected Calibration Error ($\text{ECE} \le 0.08$), Brier score tracking, Population Stability Index (PSI) drift detection, and multi-state health classification (`HEALTHY`, `DEGRADED`, `DRIFTING`, `UNRELIABLE`, `SUSPENDED`).
- **Model Governance & Shadow Deployment (P3-4 / P4-1)**:
  - 10-Gate Fail-Closed Promotion Hierarchy (Artifacts, Leakage, Calibration, Confidence Monotonicity, Drift, Economics, Risk Limits, Latency, Shadow Duration, Governance).
  - 75.8-Day (1819 hourly bars) longitudinal out-of-sample shadow study across 23,647 predictions.
  - Sub-2ms inference latency (P50: 1.21 ms, P95: 1.89 ms, Error Rate: 0.0%).
  - Bitwise non-interference between Champion and Challenger proven.
  - Fail-closed governance demonstrated: Challenger rejected despite +5.66% outperformance over Champion because absolute drawdown exceeded strict 20% risk limits during macro market stress.
- **Test Automation**: **402 / 402 passing Pytest unit/integration/fault-injection tests (100% pass rate, 0 regressions)**.

---

## 3. Technology Stack & Architecture Mapping

| Layer | Technologies | Engineering Purpose |
|---|---|---|
| **ML & Data Science** | LightGBM, Scikit-learn, NumPy, Pandas | Cross-sectional ranking, Purged WFO, Platt probability calibration, distribution drift (PSI/KS). |
| **Backend & APIs** | Python 3.12, FastAPI, Pydantic, Uvicorn | High-throughput async REST endpoints, real-time telemetry streaming, schema validation. |
| **Durable Storage** | SQLite (WAL Mode, ACID Transactions) | Low-latency transactional persistence for orders, fills, snapshots, and audit trails. |
| **Observability & Ops**| Prometheus, Grafana, Structured JSON Logging | Latency profiling (P50/P95), error rates, calibration ECE, health state exports. |
| **Testing & CI/CD** | Pytest, Pytest-Asyncio, Git | 402 deterministic unit, integration, soak, and fault-injection tests. |
| **Cloud Hosting** | Oracle Cloud Infrastructure, PM2, Nginx | Staging paper-trading deployment, process supervision, reverse proxy. |

---

## 4. Cross-Role Transferability

- **ML / AI Engineer**: Purged cross-validation, feature engineering, probability calibration, confidence auditing, distribution drift detection.
- **MLOps / Platform Engineer**: Model registry, immutable versioning, isolated shadow deployment, automated promotion gates, atomic rollback.
- **Backend / Systems Engineer**: ACID transactions, idempotent state machines, crash recovery, deduplication tokens, continuous reconciliation, sub-millisecond API design.
- **Reliability / SRE**: Deterministic soak testing, failure injection, circuit breakers, health checks, automated fail-closed error handling.

---

## 5. Contact & Repository
- **Repository**: `https://github.com/ajay1951/ai-trading-research-platform`
- **Full Case Study**: [`docs/case-study.md`](file:///c:/Users/ajayg/ai_crypto_bot/docs/case-study.md)
- **Architecture Decisions**: [`docs/decisions/`](file:///c:/Users/ajayg/ai_crypto_bot/docs/decisions/)
