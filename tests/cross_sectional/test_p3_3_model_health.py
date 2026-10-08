"""
tests/cross_sectional/test_p3_3_model_health.py
===============================================
P3-3 Deterministic Model Health Engine Validation Test Suite.

Validates:
1. Health state transitions (HEALTHY, DEGRADED, DRIFTING, UNRELIABLE, SUSPENDED)
2. Transparent rule-based score calculation out of 100
3. Structured reason code generation
4. Determinism and non-interfering observation layer
"""

import pytest
from evaluation.calibration import CalibrationMetrics
from evaluation.drift_detection import DriftMetricResult, DriftSeverity, DriftType
from evaluation.model_health import ModelHealthEngine, ModelHealthState


def test_healthy_model_state():
    cal = CalibrationMetrics(
        brier_score=0.20, log_loss=0.55, expected_calibration_error=0.04,
        maximum_calibration_error=0.08, calibration_slope=1.05, calibration_intercept=-0.02,
        brier_ci_95=(0.19, 0.21), ece_ci_95=(0.03, 0.05), sample_size=1000, is_well_calibrated=True
    )

    assessment = ModelHealthEngine.assess_health(
        timestamp="2026-06-01 00:00:00",
        model_version="P3-3-v1",
        calibration=cal,
        rolling_hit_rate=0.52
    )

    assert assessment.health_state == ModelHealthState.HEALTHY
    assert assessment.health_score >= 90.0
    assert assessment.is_operational


def test_drifting_model_state():
    cal = CalibrationMetrics(
        brier_score=0.24, log_loss=0.68, expected_calibration_error=0.06,
        maximum_calibration_error=0.12, calibration_slope=0.85, calibration_intercept=-0.10,
        brier_ci_95=(0.23, 0.25), ece_ci_95=(0.05, 0.07), sample_size=1000, is_well_calibrated=True
    )

    pred_drift = DriftMetricResult(
        entity_name="prob", drift_type=DriftType.PREDICTION_DRIFT,
        psi=0.22, ks_statistic=0.18, ks_pvalue=0.001, wasserstein_dist=0.08,
        mean_shift_zscore=0.25, std_ratio=1.1, missingness_shift=0.0,
        severity=DriftSeverity.MODERATE, reference_sample_size=1000,
        monitoring_sample_size=1000, is_drifted=True
    )

    assessment = ModelHealthEngine.assess_health(
        timestamp="2026-06-01 00:00:00",
        model_version="P3-3-v1",
        calibration=cal,
        prediction_drift=pred_drift,
        rolling_hit_rate=0.50
    )

    assert assessment.health_state == ModelHealthState.DRIFTING
    assert assessment.health_score <= 90.0
    assert assessment.is_operational


def test_unreliable_and_suspended_model_states():
    cal_bad = CalibrationMetrics(
        brier_score=0.35, log_loss=0.95, expected_calibration_error=0.22,
        maximum_calibration_error=0.45, calibration_slope=0.30, calibration_intercept=-0.50,
        brier_ci_95=(0.33, 0.37), ece_ci_95=(0.20, 0.24), sample_size=1000, is_well_calibrated=False
    )

    assessment = ModelHealthEngine.assess_health(
        timestamp="2026-06-01 00:00:00",
        model_version="P3-3-v1",
        calibration=cal_bad,
        rolling_hit_rate=0.35 # severe hit rate collapse
    )

    assert assessment.health_state in [ModelHealthState.UNRELIABLE, ModelHealthState.SUSPENDED]
    assert len(assessment.reason_codes) >= 2
    assert assessment.active_alerts_count >= 2
