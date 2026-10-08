# ADR-010: Isolated Shadow Evaluation & Execution Non-Interference

## Status
Accepted / Frozen (P3-4, P4-1)

## Context
Evaluating Challenger models in production environments can inadvertently corrupt execution state, mutate account balances, or trigger unintended orders if not strictly isolated.

## Decision
Challenger models execute in an isolated shadow harness receiving identical market data features as the Champion. The Challenger produces predictions, confidence scores, and hypothetical Top-2 allocations, but is completely decoupled from the Order Management System, Order Routing, and Portfolio Balances.

## Alternatives Considered
- Live A/B Capital Splitting: Rejected because capital should not be risked on unvalidated candidate models.
- Offline-Only Evaluation: Rejected because offline evaluation cannot measure real-time inference latency and streaming data agreement.

## Consequences & Tradeoffs
- **Pros**: 100% execution non-interference (bitwise identical Champion execution proven); enables live operational testing with zero financial risk.
- **Cons**: Requires running concurrent inference passes per bar.
