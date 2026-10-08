# Resume Project Entry: AI Trading Research & Model Governance Platform

## Version 1: ATS / Keyword-Optimized Version

**AI Trading Research & Model Governance Platform** | *Python, LightGBM, FastAPI, SQLite WAL, MLOps, LLMOps, Prometheus, Pytest*
- Architected a quantitative ML research platform in Python featuring 5-Fold Purged Walk-Forward Optimization with 24-hour embargo buffers, preventing lookahead leakage across a 13-asset universe.
- Built a transactional SQLite WAL-backed Order Management System (OMS) with deterministic SHA-256 deduplication tokens and automated crash recovery, validated across a deterministic 168-hour continuous soak test harness.
- Implemented MLOps model intelligence including Expected Calibration Error ($\text{ECE} \le 0.08$), Brier score tracking, and Population Stability Index (PSI) drift detection with automated multi-state health alerts.
- Designed a 10-Gate Fail-Closed Model Governance Engine with isolated shadow evaluation and atomic rollback; evaluated a 75.8-day longitudinal study over 23,600+ predictions (P50 latency 1.21 ms, 0% error rate), rejecting the Challenger model when it failed the drawdown risk gate.
- Built a provider-agnostic LLMOps benchmark and 5-gate evaluation subsystem (`evaluation/llmops/`) validating structured output, context grounding, safety refusal, and regression tracking.
- Maintained 417 passing automated Pytest tests across unit, integration, fault-injection, and LLMOps evaluation scenarios with 0 errors and 0 warnings.

---

## Version 2: Technical Depth Version (ML / MLOps / Backend Focus)

**AI Trading Research & Model Governance Platform** | *Python, LightGBM, Scikit-learn, FastAPI, SQLite, Prometheus, Docker*
- **Research Integrity & Cost Realism**: Designed cross-sectional ranking models evaluated under 5-Fold Purged Walk-Forward Optimization with 24-bar embargoes; engineered a 21.38 bps one-way transaction cost engine, demonstrating that 48-hour rebalancing preserved edge (+11.96% return, 2.61 Net Sharpe) while 1-hour cadence collapsed (-90.8% return) under turnover drag.
- **MLOps Lifecycle & Governance**: Implemented an immutable Model Registry with SHA-256 checksums, unique Champion enforcement, and an isolated shadow evaluation harness; enforced a 10-gate fail-closed promotion hierarchy rejecting candidates that breach risk limits.
- **Backend Reliability & Data Reconciliation**: Engineered an idempotent order state machine with continuous 3-way broker reconciliation, sub-millisecond SQLite WAL persistence, and automated crash recovery handling partial fills, network drops, and state drift.
- **LLMOps Governance Subsystem**: Implemented a provider-agnostic LLM benchmarking harness with deterministic evaluation metrics (exact match, token Jaccard, grounding, refusal compliance) and fail-closed promotion gates.
- **Test Automation**: Authored 417 comprehensive tests covering temporal leakage, counterfactual future mutations, broker fault injections, calibration audits, and LLMOps gate transitions.

---

## Version 3: Short / Compact Version

**AI Trading Research & Model Governance Platform** | *Python, LightGBM, FastAPI, SQLite WAL, MLOps, LLMOps, Pytest*
- Built a quantitative ML platform featuring leakage-controlled Purged Walk-Forward validation, realistic transaction cost modeling (21.38 bps base), and correlation-aware risk management across 13 assets.
- Developed a transactional, crash-resilient OMS with idempotent state machines, SQLite WAL persistence, and continuous external broker reconciliation.
- Engineered a 10-gate Champion/Challenger model governance framework with isolated shadow evaluation, drift detection, and atomic rollback; validated over 1,819 unseen hourly bars with 417 automated tests passing.
- Added a provider-agnostic LLMOps evaluation module demonstrating how quantitative governance architectures transfer to LLM release decisions.
