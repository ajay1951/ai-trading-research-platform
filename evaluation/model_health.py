"""
evaluation/model_health.py
==========================
P3-3 Deterministic Model Health & Diagnostic Status Engine.

Provides:
1. Model Health States: HEALTHY, DEGRADED, DRIFTING, UNRELIABLE, SUSPENDED.
2. Transparent Rule-Based Health Scoring (0 to 100).
3. Structured, Auditable Reason Codes & Explanations.
4. Non-Interfering Monitoring Layer: Observation & alerting only.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from evaluation.calibration import CalibrationMetrics
from evaluation.drift_detection import DriftMetricResult, DriftSeverity, DriftType


class ModelHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DRIFTING = "DRIFTING"
    UNRELIABLE = "UNRELIABLE"
    SUSPENDED = "SUSPENDED"


@dataclass
class ModelHealthAssessment:
    """Complete diagnostic assessment of model health status."""
    timestamp: str
    model_version: str
    health_state: ModelHealthState
    health_score: float # 0 to 100
    calibration_score: float # 0 to 25
    feature_drift_score: float # 0 to 25
    prediction_drift_score: float # 0 to 25
    performance_score: float # 0 to 25
    primary_reason: str
    reason_codes: List[str]
    active_alerts_count: int
    is_operational: bool


class ModelHealthEngine:
    """
    Evaluates multi-dimensional diagnostic metrics to assign transparent health states.
    """

    @staticmethod
    def assess_health(
        timestamp: str,
        model_version: str,
        calibration: Optional[CalibrationMetrics] = None,
        feature_drifts: Optional[List[DriftMetricResult]] = None,
        prediction_drift: Optional[DriftMetricResult] = None,
        rolling_hit_rate: Optional[float] = None,
        rolling_brier: Optional[float] = None
    ) -> ModelHealthAssessment:
        """
        Combines calibration, feature drift, prediction drift, and rolling performance.
        """
        reasons: List[str] = []
        alerts_count = 0

        # 1. Calibration Health (25 pts)
        cal_score = 25.0
        if calibration is not None:
            if calibration.expected_calibration_error > 0.15:
                cal_score -= 15.0
                reasons.append(f"High calibration error: ECE = {calibration.expected_calibration_error:.4f} > 0.15")
                alerts_count += 1
            elif calibration.expected_calibration_error > 0.08:
                cal_score -= 8.0
                reasons.append(f"Moderate calibration error: ECE = {calibration.expected_calibration_error:.4f} > 0.08")

            if calibration.calibration_slope < 0.60 or calibration.calibration_slope > 1.40:
                cal_score -= 5.0
                reasons.append(f"Uncalibrated slope: {calibration.calibration_slope:.2f} outside [0.60, 1.40]")

        cal_score = max(0.0, cal_score)

        # 2. Feature Drift Health (25 pts)
        feat_score = 25.0
        if feature_drifts:
            high_drifts = [f for f in feature_drifts if f.severity == DriftSeverity.HIGH]
            mod_drifts = [f for f in feature_drifts if f.severity == DriftSeverity.MODERATE]

            if len(high_drifts) >= 3:
                feat_score -= 18.0
                reasons.append(f"Severe feature drift: {len(high_drifts)} features with high PSI > 0.25")
                alerts_count += 1
            elif len(high_drifts) >= 1 or len(mod_drifts) >= 4:
                feat_score -= 10.0
                reasons.append(f"Moderate feature drift: {len(high_drifts)} high, {len(mod_drifts)} moderate drifting features")
            elif len(mod_drifts) >= 1:
                feat_score -= 4.0

        feat_score = max(0.0, feat_score)

        # 3. Prediction Drift Health (25 pts)
        pred_score = 25.0
        if prediction_drift is not None:
            if prediction_drift.severity == DriftSeverity.HIGH:
                pred_score -= 18.0
                reasons.append(f"Severe prediction drift: PSI = {prediction_drift.psi:.4f} > 0.25")
                alerts_count += 1
            elif prediction_drift.severity == DriftSeverity.MODERATE:
                pred_score -= 10.0
                reasons.append(f"Moderate prediction drift: PSI = {prediction_drift.psi:.4f} > 0.10")

        pred_score = max(0.0, pred_score)

        # 4. Performance Health (25 pts)
        perf_score = 25.0
        if rolling_hit_rate is not None:
            if rolling_hit_rate < 0.40:
                perf_score -= 18.0
                reasons.append(f"Hit rate collapse: rolling hit rate = {rolling_hit_rate:.2%} < 40.0%")
                alerts_count += 1
            elif rolling_hit_rate < 0.48:
                perf_score -= 8.0
                reasons.append(f"Sub-par hit rate: rolling hit rate = {rolling_hit_rate:.2%} < 48.0%")

        perf_score = max(0.0, perf_score)

        total_score = cal_score + feat_score + pred_score + perf_score

        # Determine State
        if alerts_count >= 3 or total_score < 40.0:
            state = ModelHealthState.SUSPENDED
            primary = "Critical model breakdown: Multiple critical failure alerts active."
        elif alerts_count >= 2 or total_score < 60.0:
            state = ModelHealthState.UNRELIABLE
            primary = "Unreliable predictions: High calibration or performance degradation."
        elif pred_score <= 15.0 or feat_score <= 15.0 or total_score < 75.0:
            state = ModelHealthState.DRIFTING
            primary = "Distribution drift detected: Input features or predictions shifting."
        elif total_score < 90.0:
            state = ModelHealthState.DEGRADED
            primary = "Mild degradation: Minor calibration or feature distribution shift."
        else:
            state = ModelHealthState.HEALTHY
            primary = "Healthy: Acceptable calibration, stable distributions, and normal performance."

        return ModelHealthAssessment(
            timestamp=timestamp,
            model_version=model_version,
            health_state=state,
            health_score=round(total_score, 1),
            calibration_score=round(cal_score, 1),
            feature_drift_score=round(feat_score, 1),
            prediction_drift_score=round(pred_score, 1),
            performance_score=round(perf_score, 1),
            primary_reason=primary,
            reason_codes=reasons if reasons else ["Normal operational baseline"],
            active_alerts_count=alerts_count,
            is_operational=state in [ModelHealthState.HEALTHY, ModelHealthState.DEGRADED, ModelHealthState.DRIFTING]
        )
