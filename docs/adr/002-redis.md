# ADR 002: Redis for In-Memory Caching & Message Brokering

## Problem
Real-time WebSocket market tickers and fast-path circuit breakers demand sub-millisecond data retrieval. Furthermore, distributed tasks require a high-throughput queue broker.

## Options
1. **In-Memory Python Dict**: Zero latency within a single process, but cannot be shared across multiple Uvicorn worker processes or Celery nodes.
2. **RabbitMQ**: Advanced message broker, but lacks native key-value caching capabilities for ticker storage.
3. **Redis**: In-memory data store supporting sub-millisecond key-value operations, Pub/Sub channels, and Celery broker queues.

## Decision
Adopt **Redis 7** for both state caching and task queue brokering.

## Reason
Consolidates real-time price caching, rate-limiting counters, and task queue transport into a single operational dependency.

## Consequences
Worker nodes and web endpoints share synchronized real-time portfolio and price state without disk I/O bottlenecks.
