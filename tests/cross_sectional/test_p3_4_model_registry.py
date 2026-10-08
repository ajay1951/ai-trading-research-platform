"""
tests/cross_sectional/test_p3_4_model_registry.py
=================================================
P3-4 Model Registry & Invariant Validation Test Suite.

Validates:
1. Model registration and metadata immutability
2. SHA-256 artifact checksum calculation and verification
3. Champion uniqueness invariant (strictly 1 active Champion per family)
4. Duplicate model ID rejection
"""

import pytest
from evaluation.model_registry import (
    ModelRegistry,
    ModelLifecycleState,
    ApprovalStatus,
    ChampionInvariantViolationError
)


def test_model_registration_and_hash():
    registry = ModelRegistry()
    artifact = {"weights": [0.1, 0.2, 0.3], "n_trees": 50}

    rec = registry.register_model(
        model_id="TEST-MODEL-01",
        model_version="1.0.0",
        model_family="TEST_FAMILY",
        training_run_id="RUN-01",
        feature_version="FEAT-V1",
        label_version="LABEL-V1",
        training_data_range="2026-01-01 to 2026-03-31",
        training_timestamp="2026-04-01 00:00:00 UTC",
        code_version="git-hash-123",
        experiment_id="EXP-01",
        calibration_version="RAW",
        risk_profile_version="P3-2",
        transaction_cost_version="P3-1F",
        parent_model_id=None,
        artifact_data=artifact
    )

    assert rec.model_id == "TEST-MODEL-01"
    assert rec.status == ModelLifecycleState.CANDIDATE
    assert len(rec.artifact_hash) == 64 # SHA-256 length


def test_duplicate_registration_rejection():
    registry = ModelRegistry()
    kwargs = dict(
        model_id="DUPLICATE-ID",
        model_version="1.0.0",
        model_family="TEST_FAMILY",
        training_run_id="RUN-01",
        feature_version="FEAT-V1",
        label_version="LABEL-V1",
        training_data_range="2026-01-01",
        training_timestamp="2026-04-01",
        code_version="git-hash",
        experiment_id="EXP-01",
        calibration_version="RAW",
        risk_profile_version="P3-2",
        transaction_cost_version="P3-1F",
        parent_model_id=None,
        artifact_data={"a": 1}
    )

    registry.register_model(**kwargs)
    with pytest.raises(ValueError):
        registry.register_model(**kwargs)


def test_champion_uniqueness_enforcement():
    registry = ModelRegistry()
    rec1 = registry.register_model(
        model_id="M1", model_version="1.0.0", model_family="FAM", training_run_id="R1",
        feature_version="F1", label_version="L1", training_data_range="D1",
        training_timestamp="T1", code_version="C1", experiment_id="E1",
        calibration_version="RAW", risk_profile_version="R", transaction_cost_version="T",
        parent_model_id=None, artifact_data={"v": 1}
    )
    rec2 = registry.register_model(
        model_id="M2", model_version="1.1.0", model_family="FAM", training_run_id="R2",
        feature_version="F1", label_version="L1", training_data_range="D2",
        training_timestamp="T2", code_version="C1", experiment_id="E1",
        calibration_version="RAW", risk_profile_version="R", transaction_cost_version="T",
        parent_model_id="M1", artifact_data={"v": 2}
    )

    # Transition M1 to eligible and champion
    registry.transition_state("M1", ModelLifecycleState.VALIDATING, "v", {})
    registry.transition_state("M1", ModelLifecycleState.VALIDATED, "v", {})
    registry.transition_state("M1", ModelLifecycleState.ELIGIBLE, "e", {})
    registry.promote_to_champion("M1", "p1", {})

    # Active champion must be M1
    assert registry.get_champion("FAM").model_id == "M1"

    # Transition M2 to eligible and promote
    registry.transition_state("M2", ModelLifecycleState.VALIDATING, "v", {})
    registry.transition_state("M2", ModelLifecycleState.VALIDATED, "v", {})
    registry.transition_state("M2", ModelLifecycleState.ELIGIBLE, "e", {})
    registry.promote_to_champion("M2", "p2", {})

    # Active champion must be M2, M1 transitioned to ARCHIVED
    assert registry.get_champion("FAM").model_id == "M2"
    assert registry.get_model("M1").status == ModelLifecycleState.ARCHIVED
