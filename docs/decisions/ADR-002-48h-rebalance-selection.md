# ADR-002: 48-Hour Rebalance Cadence Selection

## Status
Accepted / Frozen (P1-3)

## Context
Initial research evaluated 1-hour, 4-hour, 12-hour, 24-hour, and 48-hour rebalancing cadences for cross-sectional ranking.

## Decision
We selected a fixed 48-hour rebalance cadence as the canonical strategy cadence.

## Alternatives Considered
- 1-Hour Rebalancing: Produced higher gross theoretical turnover, but collapsed to -90.8% net return after realistic transaction costs and market friction.
- 24-Hour Rebalancing: Produced positive gross return but sub-optimal cost-to-signal efficiency.

## Consequences & Tradeoffs
- **Pros**: Drastically minimizes unnecessary portfolio turnover (reducing annual transaction costs by over 78%) while allowing predictive momentum features sufficient time to realize forward returns.
- **Cons**: Slower reaction to sudden intraday volatility spikes.
