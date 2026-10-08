# ADR-003: P3-1F Corrected Base Transaction Cost Model

## Status
Accepted / Frozen (P3-1F)

## Context
Early backtests assumed either zero friction or unrealistic flat 5 bps fees. During P3-1, an advanced cost model with an explicit execution delay term was introduced, but audit (P3-1F) revealed that the delay term double-counted the execution gap since P&L accounting already commenced at the execution bar open ($t+1$).

## Decision
We adopted the P3-1F Corrected Base Transaction Cost Model:
$$\text{Cost}_{\text{one-way}} = 10.0\text{ bps (Exchange Fee)} + 5.0\text{ bps (Half-Spread)} + 6.38\text{ bps (Volatility Slippage)} = 21.38\text{ bps}$$
Round-trip modeled friction is strictly **42.76 bps**.

## Alternatives Considered
- Constant 5 bps Taker Fee: Rejected as severely over-optimistic for crypto mid-cap assets.
- Explicit Delay Penalty added to $t+1$ execution: Rejected during P3-1F audit for mathematical double-counting.

## Consequences & Tradeoffs
- **Pros**: Perfectly mirrors realistic institutional crypto execution friction without synthetic double-counting.
- **Cons**: Substantially penalizes high-turnover strategies, requiring higher predictive threshold filters.
