# Resume Project Entry: AI Trading Research & Model Governance Platform

## Version 1: ATS / Keyword-Optimized Version

**AI Trading Research & Model Governance Platform** | *Python, LightGBM, FastAPI, SQLite WAL, MLOps, Prometheus, Pytest*
- Architected an end-to-end quantitative ML platform in Python featuring 5-Fold Purged Walk-Forward Optimization with 24-hour embargo buffers, eliminating lookahead bias across a 13-asset universe.
- Built a durable SQLite WAL-backed Order Management System (OMS) with deterministic SHA-256 deduplication tokens, ACID transactions, and automated crash recovery, validated across a 168-hour continuous soak test.
- Implemented real-time MLOps model intelligence including Expected Calibration Error ($\text{ECE} \le 0.08$), Brier score tracking, and Population Stability Index (PSI) drift detection with automated multi-state health alerts.
- Designed a 10-Gate Fail-Closed Model Governance Engine with isolated shadow evaluation and atomic rollback; executed a 75.8-day longitudinal study over 23,600+ predictions (P50 latency 1.21 ms, 0% error rate).
- Validated system reliability through a 402-test automated Pytest suite covering unit, integration, and fault-injection scenarios (100% pass rate).

---

## Version 2: Technical Depth Version (ML / MLOps / Backend Focus)

**AI Trading Research & Model Governance Platform** | *Python, LightGBM, Scikit-learn, FastAPI, SQLite, Prometheus, Docker*
- **Research Integrity & Cost Realism**: Designed cross-sectional momentum models evaluated under 5-Fold Purged Walk-Forward Optimization with 24-bar embargoes; engineered a 21.38 bps one-way transaction cost engine, revealing that 48-hour rebalancing preserved positive net edge (+11.96% net return, 2.61 Sharpe) while 1-hour cadence collapsed (-90.8% net return).
- **Production-Grade MLOps & Governance**: Implemented an immutable Model Registry with SHA-256 checksums, unique Champion enforcement, and an isolated shadow deployment harness with proven bitwise non-interference; enforced a 10-gate fail-closed promotion hierarchy rejecting overfitted candidates and uncontained drawdowns.
- **Backend Reliability & Data Reconciliation**: Engineered an idempotent order state machine with continuous 3-way broker reconciliation, sub-millisecond WAL persistence, and automated crash recovery handling partial fills, network disconnects, and unmodeled drift.
- **Test Engineering**: Authored 402 comprehensive tests covering temporal leakage, counterfactual future mutations, broker fault injections, calibration audits, and stress testing.

---

## Version 3: Short / Compact Version

**AI Trading Research & Model Governance Platform** | *Python, LightGBM, FastAPI, SQLite WAL, MLOps, Pytest*
- Built a research-grade ML platform featuring leakage-free Purged Walk-Forward validation, realistic transaction cost modeling (21.38 bps base), and correlation-aware risk management across 13 crypto assets.
- Developed an ACID-compliant, crash-resilient OMS with idempotent state machines and continuous external broker reconciliation.
- Engineered a 10-gate Champion/Challenger model governance framework with isolated shadow evaluation, drift detection, and atomic rollback; validated over 1,819 unseen hourly bars with 402 automated tests passing.
