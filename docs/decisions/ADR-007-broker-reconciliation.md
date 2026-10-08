# ADR-007: Continuous External Broker Reconciliation

## Status
Accepted / Frozen (P2-7)

## Context
Silent slippage, unexpected fee deductions, liquidation ticks, and partial fills create drift between internal portfolio accounting and true external broker balances.

## Decision
We implemented a continuous three-way portfolio reconciler (`PortfolioReconciler`) that compares internal OMS positions, cash, and active orders against authoritative broker snapshots on every rebalance cycle, enforcing scoped trading halts upon critical drift detection.

## Alternatives Considered
- Periodic End-of-Day Batch Reconciliation: Rejected as too slow to prevent runaway drift in 24/7 crypto markets.
- Trusting Internal OMS Exclusively: Rejected because broker is the absolute financial ground truth.

## Consequences & Tradeoffs
- **Pros**: Detects unmodeled drift instantly; guarantees mathematical balance sheet conservation:
  $$\text{Cash}_{\text{final}} = \text{Cash}_{\text{init}} - \sum \text{Buys} + \sum \text{Sells} - \sum \text{Fees}$$
- **Cons**: Adds a network round-trip query to each rebalance cycle.
