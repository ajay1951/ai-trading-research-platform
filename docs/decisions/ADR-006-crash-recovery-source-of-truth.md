# ADR-006: Crash Recovery & Authoritative State Hydration

## Status
Accepted / Frozen (P2-4)

## Context
Following an abrupt crash or power loss, the system must recover without placing redundant orders or corrupting portfolio accounting.

## Decision
On startup, the system recovers state from the durable SQLite WAL journal, queries the broker for open orders, reconciles in-flight orders, and transitions pending states to terminal states before accepting new trading cycles.

## Alternatives Considered
- Cold Restart (Wiping state and starting fresh): Rejected because open broker positions and orders would become untracked orphans.
- Snapshot-only restoration: Rejected because operations between snapshots would be lost.

## Consequences & Tradeoffs
- **Pros**: Zero state drift across crashes; seamless recovery in under 50 milliseconds.
- **Cons**: Requires explicit startup recovery synchronization phase before event loop activation.
