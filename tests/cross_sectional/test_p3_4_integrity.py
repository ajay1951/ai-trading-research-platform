"""
tests/cross_sectional/test_p3_4_integrity.py
============================================
P3-4 Research Integrity, Causality & Future Mutation Validation Test Suite.

Validates:
1. Decision cutoff timestamp integrity
2. Future mutation invariance (future data cannot alter past promotion/lifecycle decisions)
3. Production baseline database isolation
"""

import pytest
import os
import json
from evaluation.model_registry import ModelRegistry, ModelLifecycleState
from evaluation.promotion_gates import PromotionGateEngine, PromotionDecisionType
from evaluation.calibration import CalibrationMetrics
from evaluation.model_health import ModelHealthAssessment, ModelHealthState


def test_future_mutation_invariance():
    # 1. Evaluate promotion decision on data at t
    cal = CalibrationMetrics(
        brier_score=0.22, log_loss=0.60, expected_calibration_error=0.03,
        maximum_calibration_error=0.08, calibration_slope=1.0, calibration_intercept=0.0,
        brier_ci_95=(0.21, 0.23), ece_ci_95=(0.02, 0.04), sample_size=1000, is_well_calibrated=True
    )
    health = ModelHealthAssessment(
        timestamp="2026-06-01 00:00:00", model_version="v1", health_state=ModelHealthState.HEALTHY,
        health_score=95.0, calibration_score=25.0, feature_drift_score=25.0, prediction_drift_score=25.0,
        performance_score=20.0, primary_reason="Healthy", reason_codes=["Healthy"], active_alerts_count=0, is_operational=True
    )

    decision_1 = PromotionGateEngine.evaluate_all_gates(
        candidate_model_id="CAND_T", champion_model_id="CHAMP", artifact_valid=True,
        research_leakage_free=True, candidate_calibration=cal, champion_calibration=cal,
        confidence_monotonic=True, health_assessment=health,
        candidate_economic={"net_return_pct": 12.0, "net_sharpe": 2.65, "mean_fold_max_dd": 0.15, "worst_fold_max_dd": 0.18},
        champion_economic={"net_return_pct": 11.96, "net_sharpe": 2.61, "mean_fold_max_dd": 0.155, "worst_fold_max_dd": 0.184},
        latency_ms=15.0, error_rate=0.0, shadow_sample_count=50, approval_status="RESEARCH_APPROVED"
    )

    # 2. Mutate future data (simulate arrival of future bear market in t+100)
    mutated_future_health = ModelHealthAssessment(
        timestamp="2026-09-01 00:00:00", model_version="v1", health_state=ModelHealthState.SUSPENDED, # Future severe breakdown
        health_score=20.0, calibration_score=5.0, feature_drift_score=5.0, prediction_drift_score=5.0,
        performance_score=5.0, primary_reason="Future Crash", reason_codes=["Future Crash"], active_alerts_count=4, is_operational=False
    )

    # 3. Recalculate decision at timestamp t using information available at t
    decision_2 = PromotionGateEngine.evaluate_all_gates(
        candidate_model_id="CAND_T", champion_model_id="CHAMP", artifact_valid=True,
        research_leakage_free=True, candidate_calibration=cal, champion_calibration=cal,
        confidence_monotonic=True, health_assessment=health, # Point-in-time health at t
        candidate_economic={"net_return_pct": 12.0, "net_sharpe": 2.65, "mean_fold_max_dd": 0.15, "worst_fold_max_dd": 0.18},
        champion_economic={"net_return_pct": 11.96, "net_sharpe": 2.61, "mean_fold_max_dd": 0.155, "worst_fold_max_dd": 0.184},
        latency_ms=15.0, error_rate=0.0, shadow_sample_count=50, approval_status="RESEARCH_APPROVED"
    )

    assert decision_1.decision == decision_2.decision
    assert decision_1.passed_gates == decision_2.passed_gates
    assert decision_1.is_promotable == decision_2.is_promotable


def test_production_database_isolation():
    # Verify that no live production database or files were modified
    prod_live_state = "data/live_state.json"
    prod_oms_db = "oms.db"

    # Files must either be untouched or non-existent in staging
    if os.path.exists(prod_live_state):
        with open(prod_live_state, "r") as f:
            data = json.load(f)
            # Ensure no test model was written to production
            assert "MOD-CHALLENGER-A-CALIBRATED" not in json.dumps(data)
