# Experiment EXP-001 — Out-Of-Sample Benchmark Run

## Overview
- **Model**: PyTorch LSTM
- **Dataset**: `BTCUSDT-1h-v1` (data/BTCUSDT_1h_historical.csv)
- **Dataset Hash**: `151b72be3a6cb775776b8869eae8da13a45a10fc6dfd2c0ea855a36a288c4f68`
- **Git Commit**: `138fda1e52c3c93f3ef700182eb05b7d6465d5dd`
- **Execution**: Signal at bar close $t$, fill at bar open $t+1$
- **Frictions**: 0.04% maker fee + 0.02% slippage per fill (12 bps round-trip)

## Empirical Performance Results
- **Net Return**: +8.26%
- **Annualized Sharpe**: 4.08
- **Sortino Ratio**: 2.01
- **Max Drawdown**: 2.74%
- **Calmar Ratio**: 3.02
- **Total Trades**: 9
- **Win Rate**: 88.9%
- **Profit Factor**: 53.84

## Temporal Partitions
- **Train Period**: `2025-09-09 01:00:00+00:00` to `2026-04-28 22:00:00+00:00` (5566 bars)
- **Embargo**: 24 bars
- **Validation Period**: `2026-04-29 23:00:00+00:00` to `2026-06-18 14:00:00+00:00` (1192 bars)
- **Embargo**: 24 bars
- **Test Period**: `2026-06-19 15:00:00+00:00` to `2026-08-06 08:00:00+00:00` (1146 bars)

## Artifact Files
- `metadata.json`: Experiment provenance and cryptographic dataset manifest.
- `config.yaml`: Exact hyperparameter and execution configuration.
- `metrics.json`: Evaluated out-of-sample performance metrics.
- `trades.csv`: Complete trade execution ledger (9 trades).
- `equity_curve.csv`: Step-by-step mark-to-market equity curve and returns.
