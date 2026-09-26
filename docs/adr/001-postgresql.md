# ADR 001: PostgreSQL for Relational Trade & State Persistence

## Problem
The trading and backtesting platform requires reliable persistence for user orders, filled transactions, experiment metadata, and portfolio state across service restarts.

## Options
1. **SQLite / Flat JSON files**: Lightweight, but lacks concurrent write locking, ACID isolation under multi-worker setups, and complex query capabilities.
2. **PostgreSQL**: Industry-standard relational database with ACID compliance, robust indexing, concurrent access, and rich JSONB support.
3. **MongoDB**: Document database, but weaker relational integrity for accounting balances and ledger constraints.

## Decision
Adopt **PostgreSQL 15** as the primary relational datastore.

## Reason
Financial ledgers, trade logs, and portfolio accounting require strict transaction guarantees (ACID) to prevent double-spending and corrupted balances across distributed worker nodes.

## Trade-offs
Adds infrastructure operational complexity compared to flat JSON files, requiring containerization and migration management.

## Consequences
All trade fills and experiment states are permanently durable and queryable with SQL joins and indexing.
