# ADR 005: Realistic Transaction Cost Modeling

## Problem
Backtests evaluated under zero-cost assumptions present fictitious profitability, masking strategies that churn capital and generate negative real P&L due to exchange fees and market impact.

## Options
1. **Zero-Fee Modeling**: Unrealistic; rejects zero-cost results from research consideration.
2. **Fixed Flat Fee**: Deducts exchange tier fee (e.g. 0.04%), but ignores market impact and slippage.
3. **Compound Cost Model (Maker/Taker Fee + Slippage)**: 0.04% maker fee + 0.02% slippage on entry and exit (12 bps round trip).

## Decision
Mandate **0.04% maker fee + 0.02% slippage (12 bps round trip)** as the default cost baseline for all crypto strategies.

## Reason
Reflects institutional execution reality on tier-1 perpetual futures venues (Binance, Bybit) including order book crossing friction.

## Consequences
High-churn strategies fail quickly during automated testing, ensuring only robust alpha signals pass to paper trading.
