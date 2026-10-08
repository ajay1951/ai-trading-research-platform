"""
tests/cross_sectional/test_p3_4_promotion.py
============================================
P3-4 Multi-Gate Promotion & Demotion Validation Test Suite.

Validates:
1. 10-Gate promotion hierarchy evaluation
2. Rejection of candidate with superior return but inferior calibration / high drawdown
3. Rejection of candidates with invalid artifact hashes or leakage
4. Pending shadow duration leading to NOT_READY status
"""

import pytest
from evaluation.calibration import CalibrationMetrics
from evaluation.model_health import ModelHealthEngine, ModelHealthState
from evaluation.promotion_gates import PromotionGateEngine, GateStatus, PromotionDecisionType


def test_promotion_gates_all_pass():
    cal = CalibrationMetrics(
        brier_score=0.22, log_loss=0.60, expected_calibration_error=0.03,
        maximum_calibration_error=0.08, calibration_slope=1.0, calibration_intercept=0.0,
        brier_ci_95=(0.21, 0.23), ece_ci_95=(0.02, 0.04), sample_size=1000, is_well_calibrated=True
    )

    health = ModelHealthEngine.assess_health("2026-06-01", "v1.1", calibration=cal, rolling_hit_rate=0.52)

    decision = PromotionGateEngine.evaluate_all_gates(
        candidate_model_id="CAND_GOOD",
        champion_model_id="CHAMP_V1",
        artifact_valid=True,
        research_leakage_free=True,
        candidate_calibration=cal,
        champion_calibration=cal,
        confidence_monotonic=True,
        health_assessment=health,
        candidate_economic={"net_return_pct": 12.5, "net_sharpe": 2.70, "mean_fold_max_dd": 0.14, "worst_fold_max_dd": 0.17},
        champion_economic={"net_return_pct": 11.96, "net_sharpe": 2.61, "mean_fold_max_dd": 0.155, "worst_fold_max_dd": 0.184},
        latency_ms=12.0,
        error_rate=0.0,
        shadow_sample_count=50,
        approval_status="RESEARCH_APPROVED"
    )

    assert decision.decision == PromotionDecisionType.PROMOTE
    assert decision.is_promotable
    assert decision.passed_gates == 10
    assert decision.failed_gates == 0


def test_rejection_of_overfitted_high_return_candidate():
    cal_bad = CalibrationMetrics(
        brier_score=0.35, log_loss=0.95, expected_calibration_error=0.18, # Bad calibration
        maximum_calibration_error=0.40, calibration_slope=0.4, calibration_intercept=-0.3,
        brier_ci_95=(0.33, 0.37), ece_ci_95=(0.16, 0.20), sample_size=1000, is_well_calibrated=False
    )
    health_bad = ModelHealthEngine.assess_health("2026-06-01", "v1.1", calibration=cal_bad, rolling_hit_rate=0.45)

    decision = PromotionGateEngine.evaluate_all_gates(
        candidate_model_id="CAND_OVERFIT",
        champion_model_id="CHAMP_V1",
        artifact_valid=True,
        research_leakage_free=True,
        candidate_calibration=cal_bad,
        champion_calibration=None,
        confidence_monotonic=False, # Non-monotonic
        health_assessment=health_bad,
        candidate_economic={"net_return_pct": 25.0, "net_sharpe": 2.0, "mean_fold_max_dd": 0.25, "worst_fold_max_dd": 0.32}, # High return but huge DD
        champion_economic={"net_return_pct": 11.96, "net_sharpe": 2.61, "mean_fold_max_dd": 0.155, "worst_fold_max_dd": 0.184},
        latency_ms=10.0,
        error_rate=0.0,
        shadow_sample_count=50,
        approval_status="RESEARCH_APPROVED"
    )

    # Must be REJECTED despite +25.0% return
    assert decision.decision == PromotionDecisionType.REJECT
    assert not decision.is_promotable
    assert decision.failed_gates >= 2
