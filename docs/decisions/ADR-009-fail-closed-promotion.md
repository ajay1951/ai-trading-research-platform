# ADR-009: 10-Gate Fail-Closed Promotion Hierarchy

## Status
Accepted / Frozen (P3-4)

## Context
Standard ML workflows often promote models based solely on higher test-set accuracy or historical backtest return, leading to severe live losses from uncalibrated probabilities, higher drawdowns, or latency spikes.

## Decision
We established a strict 10-Gate Fail-Closed Promotion Hierarchy:
1. Artifact Integrity
2. Research Integrity (Leakage-free, Purged WFO)
3. Calibration Gate (ECE $\le 0.08$)
4. Prediction Confidence Monotonicity
5. Model Drift & Health
6. Economic Gate (Net of P3-1F friction)
7. Risk Gate (Max drawdown limits)
8. Operational Reliability (Latency $\le 50$ms, Error rate $= 0.0\%$)
9. Shadow Evaluation Duration ($\ge 20$ cycles)
10. Governance Approval

If ANY single gate fails, the candidate is **REJECTED**.

## Alternatives Considered
- Return-Only Promotion: Rejected because high-return models often achieve returns by taking catastrophic tail risk.
- Weighted Scoring Threshold: Rejected because critical risk or calibration failures must be blockingvetoes.

## Consequences & Tradeoffs
- **Pros**: Completely eliminates dangerous overfitted promotions.
- **Cons**: High standard for candidate acceptance; models that fail risk thresholds during market crashes are rejected even if they outperform the Champion relatively.
