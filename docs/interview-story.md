# Engineering Interview Stories: AI Trading Research & Model Governance Platform

This document prepares detailed STAR (Situation, Task, Action, Result, Learning) interview answers covering 10 key technical challenges solved in this platform.

---

## Story 1: Preventing Lookahead Leakage with Purged Walk-Forward Optimization
- **Situation**: Standard $k$-fold cross-validation caused severe lookahead leakage in financial time series due to serial correlation and overlapping return calculation windows.
- **Task**: Design a rigorous validation splitter that guarantees zero future information leaks into training folds.
- **Action**: Implemented 5-Fold Purged Walk-Forward Optimization (WFO) with a 24-bar embargo buffer between folds. Feature scalers and indicators were fitted strictly on training fold observations. Developed automated counterfactual future-mutation unit tests that alter post-$t$ data and verify that decisions at $t$ remain bitwise identical.
- **Result**: Completely eliminated lookahead leakage across the 13-asset universe.
- **Learning**: Time series cross-validation requires temporal purging; standard shuffling or simple train/test splits severely over-estimate live performance.

---

## Story 2: Correcting Transaction-Cost Double Counting (The P3-1F Audit)
- **Situation**: During Phase P3-1, an advanced transaction-cost model with an explicit execution delay penalty was implemented.
- **Task**: Audit cost calculations to ensure mathematical and economic fidelity.
- **Action**: Identified that the explicit delay penalty double-counted the execution gap because portfolio accounting already commenced at the execution bar open ($t+1$). Removed the redundant delay term, formulated the P3-1F Base Model (21.38 bps base), and authored synthetic regression proof tests.
- **Result**: Established an audited, realistic cost framework (42.76 bps round-trip) that accurately models exchange fees, spread, and slippage.
- **Learning**: Always trace P&L timestamps back to exact execution price bars to prevent synthetic double-counting of friction.

---

## Story 3: Discovering Why High-Frequency Cross-Sectional Ranking Failed
- **Situation**: Initial research explored 1-hour, 4-hour, 12-hour, 24-hour, and 48-hour rebalancing cadences for cross-sectional momentum ranking.
- **Task**: Determine the optimal rebalancing frequency that maximizes net risk-adjusted returns after realistic transaction costs.
- **Action**: Evaluated gross vs net returns across all cadences under the 21.38 bps cost model.
- **Result**: 1-hour rebalancing collapsed to -90.8% net return due to excessive turnover drag (78% higher cost), whereas 48-hour rebalancing preserved a positive net edge (+11.96% net return, 2.61 Net Sharpe).
- **Learning**: Predictive accuracy is useless if portfolio turnover consumes the signal; rebalance cadence must be aligned with signal decay and execution friction.

---

## Story 4: Controlling Portfolio Concentration with Correlation Ceilings
- **Situation**: Cross-sectional Top-2 ranking frequently selected two highly correlated crypto assets (e.g., SOL and AVAX during a layer-1 rally), creating double-exposure concentration risk.
- **Task**: Implement dynamic risk controls without introducing excessive turnover.
- **Action**: Developed a correlation-aware exposure controller that computes rolling 24-hour return correlation between Top-2 assets and scales exposure down when correlation exceeds $\rho > 0.80$.
- **Result**: Mitigated severe portfolio drawdown during simultaneous asset selloffs while maintaining baseline 50/50 sizing during normal regimes.
- **Learning**: Asset selection algorithms must account for cross-asset covariance, not just individual ranking scores.

---

## Story 5: ACID-Compliant Crash Recovery in a Distributed Trading System
- **Situation**: In-memory order management creates catastrophic state loss and orphan positions if a worker process crashes during an active rebalance.
- **Task**: Build a zero-loss, crash-resilient Order Management System (OMS).
- **Action**: Implemented an ACID-compliant SQLite WAL-backed OMS (`PRAGMA synchronous=FULL`). On process boot, the system recovers state from the durable journal, queries external broker APIs for open orders, reconciles pending transitions, and hydrates the in-memory state before accepting new trading cycles. Validated across a 168-hour continuous soak test with 18 scheduled crash restarts.
- **Result**: Sub-50ms crash recovery with zero state drift and zero orphan orders.
- **Learning**: Durable write-ahead logging combined with broker hydration is far more reliable than complex in-memory state replication.

---

## Story 6: Resolving Ambiguous Broker Order States & UNKNOWN Recovery
- **Situation**: During network timeouts or HTTP 503 drops, an order submission may succeed at the broker but fail to return a response to the client, entering an `UNKNOWN` state.
- **Task**: Prevent duplicate order placement and resolve `UNKNOWN` states safely.
- **Action**: Tagged every logical order with a deterministic SHA-256 client order ID token. Built a broker polling recovery engine with exponential backoff and circuit-breaking halts if state remains ambiguous.
- **Result**: 100% duplicate-execution prevention across network drops and simulated broker outages.
- **Learning**: Client-generated deterministic idempotency tokens are essential for distributed transactional safety.

---

## Story 7: Continuous 3-Way Portfolio Reconciliation
- **Situation**: Subtle slippage, rounding errors, and unexpected fee deductions cause internal OMS accounting to drift from true external broker balances over time.
- **Task**: Ensure continuous mathematical conservation of the portfolio balance sheet.
- **Action**: Engineered `PortfolioReconciler` to perform automated three-way reconciliation (OMS positions, cash, and active orders vs external broker snapshots) on every rebalance cycle, enforcing balance sheet conservation:
  $$\text{Cash}_{\text{final}} = \text{Cash}_{\text{init}} - \sum \text{Buys} + \sum \text{Sells} - \sum \text{Fees}$$
- **Result**: Discrepancies exceeding 0.01% trigger scoped trading halts, preventing silent economic drift.
- **Learning**: In financial and billing systems, external entity state is the ultimate source of truth; reconcile continuously rather than in end-of-day batch jobs.

---

## Story 8: Real-Time Model Calibration & Distribution Drift Monitoring
- **Situation**: ML models can maintain high accuracy while their predicted probabilities become severely miscalibrated, leading to improper position sizing and unexpected drawdowns.
- **Task**: Implement real-time model intelligence and drift detection.
- **Action**: Built an MLOps monitoring engine computing Expected Calibration Error ($\text{ECE} \le 0.08$), Brier Score, and Population Stability Index (PSI) drift across features and predictions. Integrated a multi-state health classifier (`HEALTHY`, `DEGRADED`, `DRIFTING`, `UNRELIABLE`, `SUSPENDED`).
- **Result**: Automated detection of probability miscalibration and feature drift before financial losses occurred.
- **Learning**: Probability calibration and distribution stability are far more important in live decision-making than raw classification accuracy.

---

## Story 9: Rejecting Overfitted Models with 10-Gate Fail-Closed Promotion
- **Situation**: Candidate model Challenger B produced high historical backtest returns (+25.0%) but exhibited poor calibration ($\text{ECE} = 0.18$) and excessive drawdown (32.0%).
- **Task**: Prevent dangerous "return-only" model deployments.
- **Action**: Designed a 10-Gate Fail-Closed Promotion Hierarchy evaluating artifact hashes, leakage, calibration, confidence monotonicity, drift, economics, risk limits, latency, shadow duration, and governance approvals.
- **Result**: Challenger B was automatically **REJECTED** by Gate 3 and Gate 7, proving that the governance system prevents reckless model promotion.
- **Learning**: Model promotion must be multi-dimensional and fail-closed; higher return should never override risk, calibration, or operational constraints.

---

## Story 10: P4-1 Extended Unseen Validation & Fail-Closed Governance
- **Situation**: Challenger A preserved +5.66% more capital and had a lower drawdown than the Champion during a 75.8-day unseen macro market downtrend.
- **Task**: Determine whether Challenger A should be promoted to Champion based on predefined governance rules.
- **Action**: Replayed all 10 promotion gates on the 1819-bar longitudinal shadow dataset.
- **Result**: While Challenger A demonstrated consistent relative outperformance, Gate 7 issued a **REJECT** because both models experienced absolute drawdowns exceeding the strict 20.0% max limit during the market downturn. The Champion was retained.
- **Learning**: A robust governance framework must adhere strictly to predefined risk limits; outperforming a benchmark in a bear market does not justify promoting a model if absolute risk constraints are breached.
