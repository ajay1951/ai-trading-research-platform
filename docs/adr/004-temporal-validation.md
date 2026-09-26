# ADR 004: Purged Walk-Forward Optimization with Embargo

## Problem
Standard machine learning cross-validation (e.g. random K-fold or shuffled train/test splits) violates the arrow of time in financial time-series, leaking future autocorrelation and volatility information into past predictions.

## Options
1. **Random K-Fold Cross Validation**: Guarantees severe lookahead bias; unusable for financial trading research.
2. **Standard Chronological Split**: Better, but single static split suffers from regime bias (e.g. testing only in a bull market).
3. **Purged Walk-Forward Optimization (WFO) with Embargo**: Sliding temporal train/test windows with an embargo gap between folds to eliminate serial correlation bleed.

## Decision
Enforce **Purged Walk-Forward Optimization with Embargo** across all platform model evaluations.

## Reason
Guarantees that models are evaluated across multiple changing regimes (bull, bear, sideways) without lookahead or autocorrelation leakage.

## Consequences
Every test suite verifies non-overlapping time boundaries and embargo compliance before model benchmarking is accepted.
