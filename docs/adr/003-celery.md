# ADR 003: Celery for Asynchronous Background Execution

## Problem
Quantitative backtests across multi-asset universes and model hyperparameter sweeps can take minutes to hours. Running these synchronously on FastAPI HTTP request threads blocks the event loop and leads to HTTP gateway timeouts.

## Options
1. **BackgroundTasks (FastAPI native)**: Simple, but runs in the same process memory; fails if the API pod crashes and cannot scale workers across multiple machines.
2. **Celery**: Distributed task queue with worker pools, task retries, timeout management, and distributed monitoring.
3. **Temporal.io**: Powerful workflow engine, but introduces significant architectural overhead for current scale.

## Decision
Adopt **Celery** with Redis broker for asynchronous quantitative jobs.

## Reason
Decouples user-facing API responsiveness from compute-intensive backtesting and statistical Monte Carlo workloads.

## Consequences
Backtests return an immediate task ID with status polling endpoints (`/api/v1/backtests/{task_id}`).
