# LinkedIn Project Description: AI Trading Research & Model Governance Platform

🚀 **AI Trading Research & Model Governance Platform**

I built an end-to-end quantitative ML platform in Python that bridges research validation, MLOps model governance, and reliable backend systems:

🔹 **Research Integrity**: Built a 5-Fold Purged Walk-Forward cross-validation engine with 24-hour embargo buffers across a 13-asset universe, with zero lookahead bias validated via future-mutation tests.
🔹 **Transaction Cost Realism**: Modeled realistic exchange fees, spread, and slippage (21.38 bps base), demonstrating why 48H rebalancing preserved positive net edge (+11.96% net return, 2.61 Sharpe) while 1H rebalancing collapsed.
🔹 **MLOps & Model Governance**: Designed an immutable Model Registry with SHA-256 artifact hashing, real-time probability calibration tracking (ECE, Brier), PSI drift detection, and a 10-Gate Fail-Closed Promotion Hierarchy with atomic rollback.
🔹 **Isolated Shadow Deployment**: Executed a 75.8-day longitudinal study over 23,600+ predictions (P50 latency: 1.21 ms, 0% errors), proving bitwise non-interference between Champion and Challenger models.
🔹 **Backend Reliability**: Built a durable SQLite WAL Order Management System with deterministic deduplication tokens, crash recovery, and continuous 3-way external broker reconciliation.
🔹 **Verification**: Backed by a 402-test automated Pytest suite (100% pass rate).

Technologies: Python 3.12, LightGBM, Scikit-learn, FastAPI, SQLite WAL, Prometheus, Grafana, Pytest, Docker.

🔗 Full Case Study & Architecture: https://github.com/ajay1951/ai-trading-research-platform
