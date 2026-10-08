"""
tests/cross_sectional/test_p3_4_retraining.py
=============================================
P3-4 Retraining Policy & Anti-Thrashing Validation Test Suite.

Validates:
1. Retraining eligibility state transitions (NO_ACTION, MONITOR, REVIEW, RETRAIN_ELIGIBLE)
2. Persistence requirement (consecutive degraded/drifting alerts required)
3. Anti-thrashing cooldown enforcement (24h cooldown after triggering retraining)
"""

import pytest
from evaluation.model_health import ModelHealthAssessment, ModelHealthState
from evaluation.retraining_policy import RetrainingPolicyEngine, RetrainingStatus


def make_health(state: ModelHealthState) -> ModelHealthAssessment:
    return ModelHealthAssessment(
        timestamp="2026-06-01 00:00:00",
        model_version="v1",
        health_state=state,
        health_score=80.0,
        calibration_score=20.0,
        feature_drift_score=20.0,
        prediction_drift_score=20.0,
        performance_score=20.0,
        primary_reason="Test",
        reason_codes=["Test"],
        active_alerts_count=1,
        is_operational=True
    )


def test_retraining_persistence_and_cooldown():
    engine = RetrainingPolicyEngine(persistence_threshold=3, cooldown_seconds=3600.0)

    # 1. Healthy -> NO_ACTION
    dec1 = engine.evaluate_retraining_eligibility(make_health(ModelHealthState.HEALTHY), current_time_epoch=1000.0)
    assert dec1.status == RetrainingStatus.NO_ACTION
    assert not dec1.is_retraining_allowed

    # 2. First Drifting -> REVIEW (Persistence = 1)
    dec2 = engine.evaluate_retraining_eligibility(make_health(ModelHealthState.DRIFTING), current_time_epoch=1100.0)
    assert dec2.status == RetrainingStatus.REVIEW
    assert dec2.persistence_count == 1
    assert not dec2.is_retraining_allowed

    # 3. Second Drifting -> REVIEW (Persistence = 2)
    dec3 = engine.evaluate_retraining_eligibility(make_health(ModelHealthState.DRIFTING), current_time_epoch=1200.0)
    assert dec3.status == RetrainingStatus.REVIEW
    assert dec3.persistence_count == 2
    assert not dec3.is_retraining_allowed

    # 4. Third Drifting -> RETRAIN_ELIGIBLE (Persistence = 3 reached)
    dec4 = engine.evaluate_retraining_eligibility(make_health(ModelHealthState.DRIFTING), current_time_epoch=1300.0)
    assert dec4.status == RetrainingStatus.RETRAIN_ELIGIBLE
    assert dec4.is_retraining_allowed

    # 5. Fourth Alert during Cooldown -> Blocked by Cooldown
    dec5 = engine.evaluate_retraining_eligibility(make_health(ModelHealthState.DRIFTING), current_time_epoch=1500.0)
    assert dec5.cooldown_active
    assert not dec5.is_retraining_allowed # Anti-thrashing blocks immediate loop
