# Paper-Trading Production Baseline Documentation

**Deployment Target:** Oracle Cloud Infrastructure (OCI)  
**Host Environment:** Ubuntu 24.04 LTS (`x86_64`)  
**Deployment Mechanism:** PM2 Process Supervision + Nginx Reverse Proxy  
**Current Baseline Commit:** `d0281cf6068c08048cc0c296de1d8977faad8a5b`  
**Development Branch:** `feature/p2-1-paper-state-machine`  
**Baseline Date:** October 2026  

---

## 1. Production Architecture Overview

The paper-trading platform currently operates 24/7 on an Oracle Cloud VM running under PM2 supervisor and Nginx:

```text
Incoming Market Data (Binance REST / WS)
              ↓
PM2 Daemon (`nexus-bot` / `execution/live_momentum_daemon.py`)
              ↓
Signal Engine (Regime Filter + Momentum Ranker)
              ↓
Execution Layer (Immediate / TWAP Paper Orders)
              ↓
State Persistence (`data/live_state.json` + `oms.db`)
              ↑
PM2 Web Server (`nexus-frontend` Next.js UI on Port 3000)
              ↑
Nginx Reverse Proxy (Port 80 / 443 -> 3000)
```

---

## 2. Process & Runtime Inventory

| Component | Technology | Process Name | Path / Script | Port / Supervision |
|---|---|---|---|---|
| **Trading Engine** | Python 3.12 (venv) | `nexus-bot` | `execution/live_momentum_daemon.py` | PM2 daemon |
| **User Interface** | Next.js 14 / Node 20 | `nexus-frontend`| `frontend/` (`npm start`) | PM2 (Port 3000) |
| **Reverse Proxy** | Nginx 1.24 | `nginx.service` | `/etc/nginx/sites-available/nexus` | Systemd (Port 80) |
| **OMS Persistence** | SQLite 3 | Embedded | `oms.db` | Single-file DB |
| **Wallet State** | JSON Atomic File | Embedded | `data/live_state.json` | Disk snapshot |

---

## 3. Current Live Paper-Trading State (Read-Only Capture)

Snapshot taken prior to P2-1 development:

* **Cash Balance:** `$26.00`
* **Open Positions:**
  * `BNB/USDT`: Short position (`size: 0.031843`, `entry_price: $753.45`, `entry_ts: 2026-09-18 08:00:41+00:00`)
* **Cycle Tracking:** Cycle 1, Base: `$50.00`, Target 3x Milestone: `$150.00`
* **Order Management System (`oms.db`):**
  * Tables: `orders`, `executions`, `tca_metrics`, `sqlite_sequence`
* **Historical Trade Logs:** `paper_trades_log.json`, `data/live_trades.csv`

---

## 4. Verified Baseline Backups

A snapshot of all production state has been captured in `data/backups/` and cryptographically verified:

```json
{
  "data/live_state.json": {
    "backup_path": "data/backups/live_state_baseline_backup.json",
    "sha256": "1e8cc7a8260b4efd55998f416d80c65187e1f40d1cb80b62e49c7198bb6e87f5",
    "size_bytes": 432,
    "verified": true
  },
  "oms.db": {
    "backup_path": "data/backups/oms_baseline_backup.db",
    "sha256": "d90e3fb0a52ae92892925b4fae0bbbeceb16d10c0018f4bb9226cb17f18991a0",
    "size_bytes": 20480,
    "verified": true
  },
  "paper_trades_log.json": {
    "backup_path": "data/backups/paper_trades_log_baseline_backup.json",
    "sha256": "b3870a1c950fefab0d9cf28ba499a0d8102a9ebfa49f3e4939b422fa71628d05",
    "size_bytes": 291,
    "verified": true
  }
}
```

---

## 5. Development Isolation Rules

1. **No Live Mutation:** Development tests must never target the production database or active `live_state.json`.
2. **Staging Database Isolation:** All local and unit tests use in-memory SQLite (`:memory:`) or isolated test SQLite databases in temp directories.
3. **Additive Architecture:** The P2-1 state machine will be implemented as a formal domain layer that seamlessly wraps existing order flows and deserializes legacy records without schema-breaking migrations.
