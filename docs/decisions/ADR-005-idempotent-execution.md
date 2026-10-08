# ADR-005: Idempotent Execution & Deduplication Tokens

## Status
Accepted / Frozen (P2-2)

## Context
Network retries, WebSocket reconnection replays, and concurrent signal generators can cause double-order submissions, accidental over-positioning, and account liquidation.

## Decision
Every logical order is tagged with a deterministic SHA-256 client order ID (`client_order_id = hash(symbol, side, quantity, price, rebalance_ts)`). The OMS and Broker Adapter enforce unique constraint checks on this token.

## Alternatives Considered
- Random UUIDv4 tokens: Rejected because retries generate distinct UUIDs, causing duplicate fills.
- Time-based deduplication window: Rejected because clock skew can bypass the window.

## Consequences & Tradeoffs
- **Pros**: 100% duplicate-execution prevention across network drops, retry loops, and broker reconnections.
- **Cons**: Requires deterministic parameter serialization.
