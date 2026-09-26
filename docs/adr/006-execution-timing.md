# ADR 006: Point-in-Time Execution Timing

## Problem
Simulating trade execution at the close price of candle $t$ assumes instantaneous model inference and fills at the exact millisecond of bar completion, which is physically impossible in live trading.

## Options
1. **Execution at Close($t$)**: Flawed lookahead assumption.
2. **Signal at Close($t$), Execution at Open($t+1$)**: Enforces realistic latency gap allowing feature extraction, model inference, and order routing.

## Decision
All backtests compute features up to candle close $t$, generate signals at $t$, and execute fills at the **Open price of candle $t+1$**.

## Reason
Completely eliminates lookahead bias and matches the mechanical sequence of live order dispatch engines.

## Consequences
Automated regression tests verify that no information from candle $t+1$ is available when generating signals for bar $t$.
