# ADR-004: SQLite WAL Durable Order Management System (OMS)

## Status
Accepted / Frozen (P2-1, P2-4)

## Context
In-memory order management creates single-point-of-failure vulnerabilities during unexpected process termination, kernel panics, or cloud host restarts.

## Decision
We implemented a durable, transactional Order Management System (OMS) backed by SQLite with Write-Ahead Logging (`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL`).

## Alternatives Considered
- Pure In-Memory State: Rejected due to catastrophic state loss upon process crash.
- External Distributed DB (PostgreSQL/CockroachDB): Rejected for local/embedded execution overhead; SQLite WAL provides zero-network overhead with ACID guarantees.

## Consequences & Tradeoffs
- **Pros**: Sub-millisecond write latency, ACID transactions, instant recovery from process crashes with zero journal corruption.
- **Cons**: Requires single-writer process concurrency control.
