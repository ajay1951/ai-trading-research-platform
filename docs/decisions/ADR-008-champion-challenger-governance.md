# ADR-008: Champion / Challenger Lifecycle Architecture

## Status
Accepted / Frozen (P3-4)

## Context
Deploying updated predictive models directly into production creates severe operational and economic risks if the new model suffers from distribution drift, overfitting, or calibration breakdown.

## Decision
We implemented a strict Champion/Challenger model registry architecture. Exactly one active Champion is permitted per model family. New candidate models must pass isolated shadow evaluation and multi-dimensional promotion gates before becoming eligible for promotion.

## Alternatives Considered
- Direct Hot-Swapping of Models: Rejected due to lack of longitudinal validation.
- In-Memory Model Pointers: Rejected because pointers are lost upon restart; registry metadata is persisted with SHA-256 artifact hashing.

## Consequences & Tradeoffs
- **Pros**: Zero live disruption; guarantees auditability, traceability, and version control for every inference.
- **Cons**: Requires managing concurrent shadow inference instances.
