"""
evaluation/retraining_policy.py
===============================
P3-4 Retraining Policy & Anti-Thrashing Engine.

Provides:
1. Deterministic Retraining Eligibility (NO_ACTION, MONITOR, REVIEW, RETRAIN_ELIGIBLE).
2. Persistence Requirement (Multi-alert confirmation before triggering retraining).
3. Anti-Thrashing Cooldown Enforcement (Prevents infinite drift->retrain loops).
"""

from __future__ import annotations
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from evaluation.model_health import ModelHealthState, ModelHealthAssessment


class RetrainingStatus(str, Enum):
    NO_ACTION = "NO_ACTION"
    MONITOR = "MONITOR"
    REVIEW = "REVIEW"
    RETRAIN_ELIGIBLE = "RETRAIN_ELIGIBLE"


@dataclass
class RetrainingDecision:
    """Decision outcome regarding model retraining eligibility."""
    status: RetrainingStatus
    persistence_count: int
    cooldown_active: bool
    is_retraining_allowed: bool
    reason_code: str
    message: str
    timestamp: str


class RetrainingPolicyEngine:
    """
    Evaluates model health history to determine retraining eligibility with cooldown.
    """

    def __init__(
        self,
        persistence_threshold: int = 3,
        cooldown_seconds: float = 86400.0 # 24 hours
    ):
        self.persistence_threshold = persistence_threshold
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_alerts = 0
        self.last_retrain_timestamp: Optional[float] = None

    def evaluate_retraining_eligibility(
        self,
        health_assessment: ModelHealthAssessment,
        current_time_epoch: Optional[float] = None
    ) -> RetrainingDecision:
        """
        Evaluates health assessment against persistence thresholds and cooldown.
        """
        now_epoch = current_time_epoch or time.time()
        now_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(now_epoch))

        # Check cooldown
        cooldown_active = False
        if self.last_retrain_timestamp is not None:
            elapsed = now_epoch - self.last_retrain_timestamp
            if elapsed < self.cooldown_seconds:
                cooldown_active = True

        state = health_assessment.health_state

        if state == ModelHealthState.HEALTHY:
            self.consecutive_alerts = 0
            return RetrainingDecision(
                status=RetrainingStatus.NO_ACTION,
                persistence_count=0,
                cooldown_active=cooldown_active,
                is_retraining_allowed=False,
                reason_code="MODEL_HEALTHY",
                message="Model is in HEALTHY operational state. No retraining required.",
                timestamp=now_ts
            )

        # Increment persistence for non-healthy states
        self.consecutive_alerts += 1

        if state == ModelHealthState.DEGRADED:
            status = RetrainingStatus.MONITOR
            code = "HEALTH_DEGRADED_MONITORING"
            msg = f"Model is DEGRADED. Monitoring persistence ({self.consecutive_alerts}/{self.persistence_threshold})."
        elif state == ModelHealthState.DRIFTING:
            if self.consecutive_alerts >= self.persistence_threshold:
                status = RetrainingStatus.RETRAIN_ELIGIBLE
                code = "PERSISTENT_DRIFT_RETRAIN_ELIGIBLE"
                msg = f"Persistent DRIFTING state across {self.consecutive_alerts} evaluations. Retraining eligible."
            else:
                status = RetrainingStatus.REVIEW
                code = "DRIFT_REVIEW_REQUIRED"
                msg = f"Model DRIFTING detected. Review active ({self.consecutive_alerts}/{self.persistence_threshold})."
        elif state in [ModelHealthState.UNRELIABLE, ModelHealthState.SUSPENDED]:
            status = RetrainingStatus.RETRAIN_ELIGIBLE
            code = f"CRITICAL_HEALTH_{state.value}_RETRAIN"
            msg = f"Critical model health state: {state.value}. Retraining immediately eligible."
        else:
            status = RetrainingStatus.MONITOR
            code = "UNKNOWN_STATE_MONITOR"
            msg = "Monitoring status."

        allowed = (status == RetrainingStatus.RETRAIN_ELIGIBLE) and not cooldown_active

        if allowed:
            self.last_retrain_timestamp = now_epoch

        return RetrainingDecision(
            status=status,
            persistence_count=self.consecutive_alerts,
            cooldown_active=cooldown_active,
            is_retraining_allowed=allowed,
            reason_code=code,
            message=msg,
            timestamp=now_ts
        )
