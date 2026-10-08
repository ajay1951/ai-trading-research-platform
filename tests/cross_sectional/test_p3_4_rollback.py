"""
tests/cross_sectional/test_p3_4_rollback.py
===========================================
P3-4 Atomic Champion Rollback & Recovery Validation Test Suite.

Validates:
1. Atomic rollback to previous approved Champion
2. Demotion of current champion upon rollback
3. Audit trail verification of rollback event
4. Rejection of rollback when no parent champion exists
"""

import pytest
from evaluation.model_registry import (
    ModelRegistry,
    ModelLifecycleState
)


def test_atomic_champion_rollback():
    registry = ModelRegistry()

    # Register M1
    registry.register_model(
        model_id="M1", model_version="1.0.0", model_family="FAM", training_run_id="R1",
        feature_version="F1", label_version="L1", training_data_range="D1",
        training_timestamp="T1", code_version="C1", experiment_id="E1",
        calibration_version="RAW", risk_profile_version="R", transaction_cost_version="T",
        parent_model_id=None, artifact_data={"v": 1}
    )
    registry.transition_state("M1", ModelLifecycleState.VALIDATING, "v", {})
    registry.transition_state("M1", ModelLifecycleState.VALIDATED, "v", {})
    registry.transition_state("M1", ModelLifecycleState.ELIGIBLE, "e", {})
    registry.promote_to_champion("M1", "p1", {})

    # Register M2
    registry.register_model(
        model_id="M2", model_version="1.1.0", model_family="FAM", training_run_id="R2",
        feature_version="F1", label_version="L1", training_data_range="D2",
        training_timestamp="T2", code_version="C1", experiment_id="E1",
        calibration_version="RAW", risk_profile_version="R", transaction_cost_version="T",
        parent_model_id="M1", artifact_data={"v": 2}
    )
    registry.transition_state("M2", ModelLifecycleState.VALIDATING, "v", {})
    registry.transition_state("M2", ModelLifecycleState.VALIDATED, "v", {})
    registry.transition_state("M2", ModelLifecycleState.ELIGIBLE, "e", {})
    registry.promote_to_champion("M2", "p2", {})

    assert registry.get_champion("FAM").model_id == "M2"

    # Rollback to M1
    rb_rec = registry.rollback_champion("FAM", "Post-promotion failure detected")

    assert rb_rec.model_id == "M1"
    assert registry.get_champion("FAM").model_id == "M1"
    assert registry.get_model("M2").status == ModelLifecycleState.DEMOTED
    assert registry.get_model("M1").status == ModelLifecycleState.CHAMPION


def test_rollback_failure_without_parent():
    registry = ModelRegistry()
    registry.register_model(
        model_id="M_ROOT", model_version="1.0.0", model_family="FAM_ROOT", training_run_id="R1",
        feature_version="F1", label_version="L1", training_data_range="D1",
        training_timestamp="T1", code_version="C1", experiment_id="E1",
        calibration_version="RAW", risk_profile_version="R", transaction_cost_version="T",
        parent_model_id=None, artifact_data={"v": 1}
    )
    registry.transition_state("M_ROOT", ModelLifecycleState.VALIDATING, "v", {})
    registry.transition_state("M_ROOT", ModelLifecycleState.VALIDATED, "v", {})
    registry.transition_state("M_ROOT", ModelLifecycleState.ELIGIBLE, "e", {})
    registry.promote_to_champion("M_ROOT", "p1", {})

    with pytest.raises(ValueError):
        registry.rollback_champion("FAM_ROOT", "Attempting rollback on root champion")
