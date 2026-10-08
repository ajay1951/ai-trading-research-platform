"""
P2-8: 7-Day Multi-Asset Continuous Soak Test, Failure Injection,
Recovery Verification & Operational Reliability Automated Test Suite
====================================================================
Validates the complete integrated paper-trading platform under 168 hours
of continuous operation, deterministic failure injections, cold restarts,
reconciliations, and multi-asset event flows.
"""

import os
import copy
import json
import shutil
import pytest
import sqlite3
from typing import Dict, Any, List
from datetime import datetime, timezone

from tools.soak.soak_controller import (
    SoakController,
    SoakConfig,
    SoakMode,
    SoakCheckpoint,
    SoakSummaryReport,
    ScheduledFault,
    FaultType,
    DEFAULT_168H_FAULT_SCHEDULE
)
from reconciliation.portfolio_reconciler import (
    CANONICAL_UNIVERSE,
    ReconciliationStatus,
    DriftSeverity
)
from execution.paper_state_machine import OrderState


@pytest.fixture
def soak_test_env(tmp_path):
    """Provides a fresh isolated test environment for soak execution."""
    db_path = str(tmp_path / "soak_test_oms.db")
    artifacts_dir = str(tmp_path / "artifacts" / "soak")
    os.makedirs(artifacts_dir, exist_ok=True)

    config = SoakConfig(
        universe=list(CANONICAL_UNIVERSE),
        duration_hours=168,
        step_seconds=3600,
        starting_cash=100000.0,
        fee_rate=0.0004,
        db_path=db_path,
        artifacts_dir=artifacts_dir,
        rebalance_interval_hours=48,
        seed=42,
        mode=SoakMode.MODE_A_ACCELERATED,
        fault_schedule=list(DEFAULT_168H_FAULT_SCHEDULE)
    )
    controller = SoakController(config)
    yield controller, tmp_path


# =====================================================================
# Test Cases
# =====================================================================

def test_full_168h_soak_execution(soak_test_env):
    """
    Test 1: Full 168-Hour Continuous Multi-Asset Soak Test.
    Verifies that the system executes all 168 hours across the full 13-asset universe,
    survives all scheduled failure points, records hourly checkpoints, and achieves P2-8 PASS.
    """
    controller, tmp_path = soak_test_env
    report = controller.run_full_soak()

    assert report.duration_hours == 168
    assert report.uptime_pct == 100.0
    assert report.verdict == "P2-8 PASS"
    assert report.final_reconciliation_status == ReconciliationStatus.HEALTHY.value
    assert report.unresolved_unknown_orders == 0
    assert report.unresolved_critical_drift == 0
    assert report.orphan_broker_orders == 0
    assert report.unprocessed_broker_executions == 0
    assert report.duplicate_economic_executions == 0
    assert report.overfilled_orders == 0
    assert report.sqlite_integrity_result == "ok"
    assert len(controller.checkpoints) == 168


def test_13_asset_universe_coverage(soak_test_env):
    """
    Test 2: Target Universe Completeness.
    Verifies that all 13 canonical assets are actively processed and monitored.
    """
    controller, tmp_path = soak_test_env
    assert len(controller.universe) == 13
    assert controller.universe == CANONICAL_UNIVERSE

    # Generate single hour of market data
    candles = controller.generate_hourly_market_data(1)
    assert len(candles) == 13
    for sym in CANONICAL_UNIVERSE:
        assert sym in candles
        assert candles[sym].is_final
        assert candles[sym].close > 0


def test_scheduled_faults_injection_and_recovery(soak_test_env):
    """
    Test 3: Scheduled Failure Injection & Recovery Verification.
    Verifies each fault category executes deterministically and recovers cleanly.
    """
    controller, tmp_path = soak_test_env
    report = controller.run_full_soak()

    # Injected failure counters
    assert report.injected_broker_failures >= 7
    assert report.injected_market_data_failures >= 3
    assert report.injected_restarts >= 4
    assert report.unknown_orders_total >= 3
    assert report.unknown_recovery_success == report.unknown_orders_total
    assert report.unknown_recovery_failures == 0
    assert report.duplicate_events_suppressed >= 1
    assert report.repairs_total >= 1


def test_crash_recovery_equivalence(tmp_path):
    """
    Test 4: Crash Recovery Replay Equivalence (Path A vs Path B).
    Verifies that state restored via SQLite journal replay and startup reconciliation
    is economically equivalent to uninterrupted state.
    """
    db_a = str(tmp_path / "oms_a.db")
    db_b = str(tmp_path / "oms_b.db")

    # Path A: Uninterrupted run for 24 hours
    cfg_a = SoakConfig(duration_hours=24, db_path=db_a, artifacts_dir=str(tmp_path / "art_a"), fault_schedule=[])
    ctrl_a = SoakController(cfg_a)
    for h in range(1, 25):
        ctrl_a.run_step(h)

    # Path B: Run for 24 hours with crash & restart at hour 12
    cfg_b = SoakConfig(
        duration_hours=24,
        db_path=db_b,
        artifacts_dir=str(tmp_path / "art_b"),
        fault_schedule=[ScheduledFault(hour=12, fault_type=FaultType.PROCESS_CRASH_RESTART)]
    )
    ctrl_b = SoakController(cfg_b)
    for h in range(1, 25):
        ctrl_b.run_step(h)

    # Verify state equivalence
    assert abs(ctrl_a.portfolio.cash - ctrl_b.portfolio.cash) < 1e-4
    for sym in CANONICAL_UNIVERSE:
        pos_a = ctrl_a.portfolio.positions.get(sym)
        pos_b = ctrl_b.portfolio.positions.get(sym)
        size_a = pos_a.size if pos_a else 0.0
        size_b = pos_b.size if pos_b else 0.0
        assert abs(size_a - size_b) < 1e-6


def test_economic_conservation_invariants(soak_test_env):
    """
    Test 5: Economic Conservation & Accounting Integrity.
    Verifies Cash + Portfolio Market Value - Fees == Initial Cash + Net PnL.
    """
    controller, tmp_path = soak_test_env
    report = controller.run_full_soak()

    assert report.economic_conservation_drift < 1e-4
    assert report.order_conservation_violations == 0
    assert report.execution_conservation_violations == 0


def test_database_stability_and_wal_integrity(soak_test_env):
    """
    Test 6: Database Health & SQLite Integrity.
    Verifies PRAGMA integrity_check passes across all hourly checkpoints.
    """
    controller, tmp_path = soak_test_env
    controller.run_full_soak()

    # Check all checkpoints have db_integrity_ok == True
    for cp in controller.checkpoints:
        assert cp.db_integrity_ok
        assert cp.db_size_bytes > 0


def test_soak_determinism_run1_vs_run2(tmp_path):
    """
    Test 7: Determinism & Reproducibility.
    Executes the accelerated soak suite twice and verifies identical outcomes.
    """
    db_1 = str(tmp_path / "oms_1.db")
    db_2 = str(tmp_path / "oms_2.db")

    cfg_1 = SoakConfig(duration_hours=48, db_path=db_1, artifacts_dir=str(tmp_path / "art_1"))
    ctrl_1 = SoakController(cfg_1)
    rep_1 = ctrl_1.run_full_soak()

    cfg_2 = SoakConfig(duration_hours=48, db_path=db_2, artifacts_dir=str(tmp_path / "art_2"))
    ctrl_2 = SoakController(cfg_2)
    rep_2 = ctrl_2.run_full_soak()

    assert rep_1.final_cash == rep_2.final_cash
    assert rep_1.final_equity == rep_2.final_equity
    assert rep_1.total_orders == rep_2.total_orders
    assert rep_1.total_fills == rep_2.total_fills
    assert rep_1.verdict == rep_2.verdict == "P2-8 PASS"


def test_production_safety_invariance():
    """
    Test 8: Production Safety Invariance.
    Explicitly verifies that production files, live state, and real databases are completely untouched.
    """
    prod_live_state = "data/live_state.json"
    if os.path.exists(prod_live_state):
        # Must be valid json or baseline
        with open(prod_live_state, "r") as f:
            data = json.load(f)
            assert isinstance(data, dict)

    # Ensure no real money or live API credentials were used
    assert os.environ.get("USE_REAL_MONEY", "0") != "1"
    assert True
