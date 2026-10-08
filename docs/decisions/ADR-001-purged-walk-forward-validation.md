# ADR-001: Purged Walk-Forward Optimization (WFO) Validation

## Status
Accepted / Frozen (P1-1)

## Context
Standard cross-validation (e.g. k-fold) causes catastrophic label and feature leakage in financial time series due to serial correlation, overlapping return horizons, and lookahead bias.

## Decision
We implemented a strict 5-Fold Purged Walk-Forward Optimization scheme with a mandatory 24-bar (24-hour) embargo period between training and out-of-sample evaluation folds.

## Alternatives Considered
- Standard K-Fold Cross-Validation: Rejected due to lookahead leakage across temporal boundaries.
- Simple Train/Test Split: Rejected because a single test period cannot capture varying market regimes (bull, bear, sideways).

## Consequences & Tradeoffs
- **Pros**: Completely eliminates temporal leakage; reproduces realistic rolling out-of-sample performance across macro regimes.
- **Cons**: Reduces total effective sample size per fold due to the 24-bar embargo buffer.
