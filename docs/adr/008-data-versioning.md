# ADR 008: Cryptographic SHA-256 Dataset Manifests

## Problem
Quantitative research results cannot be independently reproduced if datasets are silently mutated, truncated, or modified without a cryptographic trail.

## Options
1. **Unversioned File Paths**: Leads to silent test data drift and unreproducible backtest claims.
2. **DVC (Data Version Control)**: Robust, but introduces additional external dependencies and Git remotes.
3. **In-Repo Cryptographic Manifests (`data/manifests/*.json`, `*.yaml`)**: SHA-256 hashing of raw candle data combined with summary statistics (start time, end time, row counts, null counts).

## Decision
Implement native **SHA-256 cryptographic dataset manifests** in `data/manifests/`.

## Reason
Enables zero-dependency, verifiable audit trails linking every reported benchmark metric directly to an immutable dataset fingerprint.

## Consequences
Every experiment run records the exact dataset hash in `results/metrics.json`. Any bitwise modification of raw historical candles invalidates the manifest and flags data mutation.
