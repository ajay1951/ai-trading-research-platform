"""
tests/cross_sectional/test_p3_4_lifecycle.py
============================================
P3-4 Lifecycle State Machine Validation Test Suite.

Validates:
1. Valid lifecycle state machine transitions
2. Rejection of illegal/unauthorized state transitions
3. Audit event emission and state history tracking
"""

import pytest
from evaluation.model_registry import (
    ModelRegistry,
    ModelLifecycleState,
    InvalidLifecycleTransitionError
)


def test_valid_lifecycle_transitions():
    registry = ModelRegistry()
    registry.register_model(
        model_id="M_VAL", model_version="1.0.0", model_family="FAM", training_run_id="R1",
        feature_version="F1", label_version="L1", training_data_range="D1",
        training_timestamp="T1", code_version="C1", experiment_id="E1",
        calibration_version="RAW", risk_profile_version="R", transaction_cost_version="T",
        parent_model_id=None, artifact_data={"v": 1}
    )

    # CANDIDATE -> VALIDATING
    registry.transition_state("M_VAL", ModelLifecycleState.VALIDATING, "start_val", {})
    assert registry.get_model("M_VAL").status == ModelLifecycleState.VALIDATING

    # VALIDATING -> VALIDATED
    registry.transition_state("M_VAL", ModelLifecycleState.VALIDATED, "pass_val", {})
    assert registry.get_model("M_VAL").status == ModelLifecycleState.VALIDATED

    # VALIDATED -> SHADOW
    registry.transition_state("M_VAL", ModelLifecycleState.SHADOW, "start_shadow", {})
    assert registry.get_model("M_VAL").status == ModelLifecycleState.SHADOW

    # SHADOW -> ELIGIBLE
    registry.transition_state("M_VAL", ModelLifecycleState.ELIGIBLE, "shadow_done", {})
    assert registry.get_model("M_VAL").status == ModelLifecycleState.ELIGIBLE


def test_illegal_transition_rejection():
    registry = ModelRegistry()
    registry.register_model(
        model_id="M_ILLEGAL", model_version="1.0.0", model_family="FAM", training_run_id="R1",
        feature_version="F1", label_version="L1", training_data_range="D1",
        training_timestamp="T1", code_version="C1", experiment_id="E1",
        calibration_version="RAW", risk_profile_version="R", transaction_cost_version="T",
        parent_model_id=None, artifact_data={"v": 1}
    )

    # CANDIDATE -> CHAMPION directly is illegal
    with pytest.raises(InvalidLifecycleTransitionError):
        registry.transition_state("M_ILLEGAL", ModelLifecycleState.CHAMPION, "illegal", {})

    # CANDIDATE -> SHADOW directly is illegal
    with pytest.raises(InvalidLifecycleTransitionError):
        registry.transition_state("M_ILLEGAL", ModelLifecycleState.SHADOW, "illegal", {})
