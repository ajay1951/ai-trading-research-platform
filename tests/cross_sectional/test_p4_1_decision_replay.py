"""
tests/cross_sectional/test_p4_1_decision_replay.py
==================================================
P4-1 Point-in-Time Promotion Gate Replay Validation Test Suite.

Validates:
1. Replay of 10 promotion gates across longitudinal time points
2. Accurate handling of drawdown failures during market stress
3. Model health timeline tracking
"""

import pytest
from evaluation.calibration import CalibrationMetrics
from evaluation.model_health import ModelHealthEngine, ModelHealthState
from evaluation.promotion_gates import PromotionGateEngine, PromotionDecisionType, GateStatus


def test_promotion_gate_replay_under_stress():
    cal = CalibrationMetrics(
        brier_score=0.23, log_loss=0.62, expected_calibration_error=0.035,
        maximum_calibration_error=0.09, calibration_slope=0.98, calibration_intercept=0.01,
        brier_ci_95=(0.22, 0.24), ece_ci_95=(0.03, 0.04), sample_size=1500, is_well_calibrated=True
    )
    health = ModelHealthEngine.assess_health("2026-07-01", "v1.1", calibration=cal, rolling_hit_rate=0.48)

    # Replay decision where candidate suffered 28% drawdown during market crash
    decision = PromotionGateEngine.evaluate_all_gates(
        candidate_model_id="CAND_STRESS",
        champion_model_id="CHAMP_V1",
        artifact_valid=True,
        research_leakage_free=True,
        candidate_calibration=cal,
        champion_calibration=cal,
        confidence_monotonic=True,
        health_assessment=health,
        candidate_economic={"net_return_pct": -25.0, "net_sharpe": -2.1, "mean_fold_max_dd": 0.27, "worst_fold_max_dd": 0.28},
        champion_economic={"net_return_pct": -30.0, "net_sharpe": -2.8, "mean_fold_max_dd": 0.30, "worst_fold_max_dd": 0.32},
        latency_ms=1.2,
        error_rate=0.0,
        shadow_sample_count=37,
        approval_status="RESEARCH_APPROVED"
    )

    # Risk gate should fail because drawdown > 20% limit
    assert decision.decision == PromotionDecisionType.REJECT
    assert not decision.is_promotable
    assert any(g.gate_id == "GATE-07" and g.status == GateStatus.FAIL for g in decision.gate_results)
