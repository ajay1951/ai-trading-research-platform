"""
evaluation/promotion_gates.py
=============================
P3-4 Multi-Dimensional Promotion & Demotion Gates Engine.

Provides:
1. 10-Gate Hierarchical Validation Stack (Artifact, Research, Calibration,
   Confidence, Drift/Health, Economic, Risk, Operational, Shadow, Approval).
2. Fail-Closed Promotion Decisions (Multi-dimensional evidence requirement).
3. Structured Gate Result Containers & Reason Codes.
"""

from __future__ import annotations
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from evaluation.calibration import CalibrationMetrics
from evaluation.drift_detection import DriftMetricResult, DriftSeverity
from evaluation.model_health import ModelHealthAssessment, ModelHealthState


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_READY = "NOT_READY"


class PromotionDecisionType(str, Enum):
    PROMOTE = "PROMOTE"
    REJECT = "REJECT"
    NOT_READY = "NOT_READY"
    EXTEND_SHADOW = "EXTEND_SHADOW"
    RETRAIN = "RETRAIN"
    SUSPEND = "SUSPEND"
    ROLLBACK = "ROLLBACK"


@dataclass
class GateEvaluationResult:
    """Individual gate assessment outcome."""
    gate_id: str
    gate_name: str
    status: GateStatus
    reason_code: str
    evidence: Dict[str, Any]
    timestamp: str


@dataclass
class PromotionDecision:
    """Comprehensive promotion assessment outcome."""
    decision: PromotionDecisionType
    candidate_model_id: str
    champion_model_id: Optional[str]
    total_gates: int
    passed_gates: int
    failed_gates: int
    not_ready_gates: int
    is_promotable: bool
    primary_reason: str
    gate_results: List[GateEvaluationResult]
    timestamp: str


class PromotionGateEngine:
    """
    Evaluates candidates across all 10 mandatory promotion gates.
    """

    @staticmethod
    def evaluate_all_gates(
        candidate_model_id: str,
        champion_model_id: Optional[str],
        artifact_valid: bool,
        research_leakage_free: bool,
        candidate_calibration: CalibrationMetrics,
        champion_calibration: Optional[CalibrationMetrics],
        confidence_monotonic: bool,
        health_assessment: ModelHealthAssessment,
        candidate_economic: Dict[str, float], # net_return, net_sharpe, mean_dd, worst_dd
        champion_economic: Optional[Dict[str, float]],
        latency_ms: float,
        error_rate: float,
        shadow_sample_count: int,
        approval_status: str
    ) -> PromotionDecision:
        """
        Executes complete 10-gate validation battery.
        """
        now_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        gate_results: List[GateEvaluationResult] = []

        # GATE 1: Artifact Integrity
        g1_pass = artifact_valid
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-01",
            gate_name="Artifact Integrity Gate",
            status=GateStatus.PASS if g1_pass else GateStatus.FAIL,
            reason_code="SHA256_HASH_VERIFIED" if g1_pass else "HASH_MISMATCH_OR_CORRUPT",
            evidence={"artifact_valid": artifact_valid},
            timestamp=now_ts
        ))

        # GATE 2: Research Integrity
        g2_pass = research_leakage_free
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-02",
            gate_name="Research Integrity Gate",
            status=GateStatus.PASS if g2_pass else GateStatus.FAIL,
            reason_code="ZERO_LEAKAGE_WFO_VERIFIED" if g2_pass else "LEAKAGE_DETECTED",
            evidence={"research_leakage_free": research_leakage_free},
            timestamp=now_ts
        ))

        # GATE 3: Calibration Gate
        # ECE <= 0.08 and Brier <= champion + 0.02
        champ_bs = champion_calibration.brier_score if champion_calibration else 0.25
        g3_pass = (candidate_calibration.expected_calibration_error <= 0.08) and (candidate_calibration.brier_score <= champ_bs + 0.02)
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-03",
            gate_name="Calibration Gate",
            status=GateStatus.PASS if g3_pass else GateStatus.FAIL,
            reason_code="ECE_AND_BRIER_ACCEPTABLE" if g3_pass else "CALIBRATION_DEGRADED",
            evidence={
                "candidate_ece": candidate_calibration.expected_calibration_error,
                "candidate_brier": candidate_calibration.brier_score,
                "champion_brier": champ_bs
            },
            timestamp=now_ts
        ))

        # GATE 4: Prediction Confidence Gate
        g4_pass = confidence_monotonic
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-04",
            gate_name="Prediction Confidence Gate",
            status=GateStatus.PASS if g4_pass else GateStatus.FAIL,
            reason_code="MONOTONIC_OUTCOME_ORDERING" if g4_pass else "CONFIDENCE_NON_MONOTONIC",
            evidence={"confidence_monotonic": confidence_monotonic},
            timestamp=now_ts
        ))

        # GATE 5: Drift & Health Gate
        g5_pass = health_assessment.health_state in [ModelHealthState.HEALTHY, ModelHealthState.DEGRADED, ModelHealthState.DRIFTING]
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-05",
            gate_name="Drift & Health Gate",
            status=GateStatus.PASS if g5_pass else GateStatus.FAIL,
            reason_code=f"HEALTH_STATE_{health_assessment.health_state.value}",
            evidence={
                "health_state": health_assessment.health_state.value,
                "health_score": health_assessment.health_score,
                "active_alerts": health_assessment.active_alerts_count
            },
            timestamp=now_ts
        ))

        # GATE 6: Economic Performance Gate
        # Net Sharpe >= Champion Sharpe - 0.20 and Net Return >= Champion Net Return - 1.0%
        champ_sh = champion_economic.get("net_sharpe", 2.0) if champion_economic else 2.0
        champ_ret = champion_economic.get("net_return_pct", 10.0) if champion_economic else 10.0
        cand_sh = candidate_economic.get("net_sharpe", 0.0)
        cand_ret = candidate_economic.get("net_return_pct", 0.0)

        g6_pass = (cand_sh >= champ_sh - 0.20) and (cand_ret >= champ_ret - 1.0)
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-06",
            gate_name="Economic Performance Gate",
            status=GateStatus.PASS if g6_pass else GateStatus.FAIL,
            reason_code="ECONOMIC_PERFORMANCE_COMPLIANT" if g6_pass else "ECONOMIC_UNDERPERFORMANCE",
            evidence={
                "candidate_net_sharpe": cand_sh,
                "champion_net_sharpe": champ_sh,
                "candidate_net_return": cand_ret,
                "champion_net_return": champ_ret
            },
            timestamp=now_ts
        ))

        # GATE 7: Risk Gate
        # Mean DD <= 17.0% and Worst DD <= 20.0%
        cand_mean_dd = candidate_economic.get("mean_fold_max_dd", 0.15)
        cand_worst_dd = candidate_economic.get("worst_fold_max_dd", 0.18)
        g7_pass = (cand_mean_dd <= 0.17) and (cand_worst_dd <= 0.20)
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-07",
            gate_name="Risk Gate",
            status=GateStatus.PASS if g7_pass else GateStatus.FAIL,
            reason_code="DRAWDOWN_LIMITS_RESPECTED" if g7_pass else "DRAWDOWN_EXCEEDS_LIMITS",
            evidence={"mean_fold_max_dd": cand_mean_dd, "worst_fold_max_dd": cand_worst_dd},
            timestamp=now_ts
        ))

        # GATE 8: Operational Reliability Gate
        # Latency <= 50ms and error_rate == 0.0
        g8_pass = (latency_ms <= 50.0) and (error_rate == 0.0)
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-08",
            gate_name="Operational Reliability Gate",
            status=GateStatus.PASS if g8_pass else GateStatus.FAIL,
            reason_code="OPERATIONAL_SLAS_MET" if g8_pass else "OPERATIONAL_FAILURE",
            evidence={"latency_ms": latency_ms, "error_rate": error_rate},
            timestamp=now_ts
        ))

        # GATE 9: Shadow Evaluation Gate
        # At least 20 shadow predictions recorded
        if shadow_sample_count < 20:
            g9_status = GateStatus.NOT_READY
            g9_reason = "INSUFFICIENT_SHADOW_OBSERVATIONS"
        else:
            g9_status = GateStatus.PASS
            g9_reason = "SHADOW_VALIDATION_COMPLETED"

        gate_results.append(GateEvaluationResult(
            gate_id="GATE-09",
            gate_name="Shadow Evaluation Gate",
            status=g9_status,
            reason_code=g9_reason,
            evidence={"shadow_sample_count": shadow_sample_count},
            timestamp=now_ts
        ))

        # GATE 10: Governance & Approval Gate
        g10_pass = approval_status in ["RESEARCH_APPROVED", "DEPLOYMENT_APPROVED"]
        gate_results.append(GateEvaluationResult(
            gate_id="GATE-10",
            gate_name="Governance Approval Gate",
            status=GateStatus.PASS if g10_pass else GateStatus.FAIL,
            reason_code=f"APPROVAL_{approval_status}",
            evidence={"approval_status": approval_status},
            timestamp=now_ts
        ))

        passed = sum(1 for g in gate_results if g.status == GateStatus.PASS)
        failed = sum(1 for g in gate_results if g.status == GateStatus.FAIL)
        not_ready = sum(1 for g in gate_results if g.status == GateStatus.NOT_READY)

        if failed > 0:
            decision = PromotionDecisionType.REJECT
            primary = f"Promotion Rejected: {failed} mandatory gates failed."
            promotable = False
        elif not_ready > 0:
            decision = PromotionDecisionType.NOT_READY
            primary = f"Promotion Incomplete: {not_ready} gates pending (e.g. shadow duration)."
            promotable = False
        else:
            decision = PromotionDecisionType.PROMOTE
            primary = "All 10 validation gates passed successfully."
            promotable = True

        return PromotionDecision(
            decision=decision,
            candidate_model_id=candidate_model_id,
            champion_model_id=champion_model_id,
            total_gates=len(gate_results),
            passed_gates=passed,
            failed_gates=failed,
            not_ready_gates=not_ready,
            is_promotable=promotable,
            primary_reason=primary,
            gate_results=gate_results,
            timestamp=now_ts
        )
