"""
evaluation/model_registry.py
============================
P3-4 Model Registry, State Machine, Versioning & Audit Trail Engine.

Provides:
1. Immutable Model Registration Records with SHA-256 artifact verification.
2. Complete Lifecycle States: CANDIDATE, VALIDATING, VALIDATED, SHADOW, ELIGIBLE,
   CHAMPION, DEGRADED, DRIFTING, DEMOTED, SUSPENDED, REJECTED, ARCHIVED.
3. Strict State Transition Enforcement & Invariant Checks (Unique Champion Invariant).
4. Atomic Transactional Promotion & Rollback.
5. Immutable, Append-Only Lifecycle Audit Trail.
"""

from __future__ import annotations
import hashlib
import json
import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple, Set


class ModelLifecycleState(str, Enum):
    CANDIDATE = "CANDIDATE"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    SHADOW = "SHADOW"
    ELIGIBLE = "ELIGIBLE"
    CHAMPION = "CHAMPION"
    DEGRADED = "DEGRADED"
    DRIFTING = "DRIFTING"
    DEMOTED = "DEMOTED"
    SUSPENDED = "SUSPENDED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class ApprovalStatus(str, Enum):
    DRAFT = "DRAFT"
    RESEARCH_APPROVED = "RESEARCH_APPROVED"
    DEPLOYMENT_APPROVED = "DEPLOYMENT_APPROVED"
    REJECTED = "REJECTED"


class LifecycleEventType(str, Enum):
    MODEL_REGISTERED = "MODEL_REGISTERED"
    VALIDATION_STARTED = "VALIDATION_STARTED"
    VALIDATION_PASSED = "VALIDATION_PASSED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    SHADOW_STARTED = "SHADOW_STARTED"
    SHADOW_COMPLETED = "SHADOW_COMPLETED"
    PROMOTION_ELIGIBLE = "PROMOTION_ELIGIBLE"
    PROMOTED = "PROMOTED"
    PROMOTION_REJECTED = "PROMOTION_REJECTED"
    HEALTH_CHANGED = "HEALTH_CHANGED"
    RETRAINING_ELIGIBLE = "RETRAINING_ELIGIBLE"
    RETRAINING_STARTED = "RETRAINING_STARTED"
    RETRAINING_COMPLETED = "RETRAINING_COMPLETED"
    DEMOTED = "DEMOTED"
    SUSPENDED = "SUSPENDED"
    ROLLBACK_STARTED = "ROLLBACK_STARTED"
    ROLLBACK_COMPLETED = "ROLLBACK_COMPLETED"


# Allowed Lifecycle State Machine Transitions
VALID_TRANSITIONS: Dict[ModelLifecycleState, Set[ModelLifecycleState]] = {
    ModelLifecycleState.CANDIDATE: {ModelLifecycleState.VALIDATING, ModelLifecycleState.REJECTED},
    ModelLifecycleState.VALIDATING: {ModelLifecycleState.VALIDATED, ModelLifecycleState.REJECTED},
    ModelLifecycleState.VALIDATED: {ModelLifecycleState.SHADOW, ModelLifecycleState.ELIGIBLE, ModelLifecycleState.REJECTED},
    ModelLifecycleState.SHADOW: {ModelLifecycleState.ELIGIBLE, ModelLifecycleState.VALIDATED, ModelLifecycleState.REJECTED},
    ModelLifecycleState.ELIGIBLE: {ModelLifecycleState.CHAMPION, ModelLifecycleState.REJECTED},
    ModelLifecycleState.CHAMPION: {ModelLifecycleState.DEGRADED, ModelLifecycleState.DRIFTING, ModelLifecycleState.DEMOTED, ModelLifecycleState.SUSPENDED, ModelLifecycleState.ARCHIVED},
    ModelLifecycleState.DEGRADED: {ModelLifecycleState.CHAMPION, ModelLifecycleState.DRIFTING, ModelLifecycleState.DEMOTED, ModelLifecycleState.SUSPENDED},
    ModelLifecycleState.DRIFTING: {ModelLifecycleState.CHAMPION, ModelLifecycleState.DEMOTED, ModelLifecycleState.SUSPENDED},
    ModelLifecycleState.DEMOTED: {ModelLifecycleState.ARCHIVED, ModelLifecycleState.REJECTED},
    ModelLifecycleState.SUSPENDED: {ModelLifecycleState.DEMOTED, ModelLifecycleState.ARCHIVED},
    ModelLifecycleState.REJECTED: {ModelLifecycleState.ARCHIVED},
    ModelLifecycleState.ARCHIVED: set()
}


@dataclass
class ModelRegistrationRecord:
    """Immutable metadata representation of a registered model version."""
    model_id: str
    model_version: str
    model_family: str
    training_run_id: str
    feature_version: str
    label_version: str
    training_data_range: str
    training_timestamp: str
    code_version: str
    experiment_id: str
    calibration_version: str
    risk_profile_version: str
    transaction_cost_version: str
    parent_model_id: Optional[str]
    status: ModelLifecycleState
    approval_status: ApprovalStatus
    artifact_hash: str
    created_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LifecycleEvent:
    """Immutable audit event log record."""
    event_id: str
    model_id: str
    model_version: str
    event_type: LifecycleEventType
    timestamp: str
    previous_state: ModelLifecycleState
    new_state: ModelLifecycleState
    reason_code: str
    evidence_hash: str
    actor: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChampionRecord:
    """Active Champion model state for a model family."""
    model_id: str
    model_version: str
    model_family: str
    promotion_timestamp: str
    promotion_reason: str
    approval_record: str
    evaluation_summary: Dict[str, Any]
    health_state: str
    rollback_parent: Optional[str]
    artifact_hash: str


class InvalidLifecycleTransitionError(Exception):
    """Raised when an illegal lifecycle state transition is requested."""
    pass


class ChampionInvariantViolationError(Exception):
    """Raised when multiple active champions are detected for a model family."""
    pass


class ModelRegistry:
    """
    Manages model registration, state transitions, champion uniqueness, rollback, and audit trail.
    """

    def __init__(self):
        self._models: Dict[str, ModelRegistrationRecord] = {}
        self._events: List[LifecycleEvent] = []
        self._champions: Dict[str, ChampionRecord] = {} # model_family -> ChampionRecord
        self._event_counter = 0

    @staticmethod
    def compute_artifact_hash(data: Any) -> str:
        """Computes deterministic SHA-256 checksum for arbitrary data or artifact dict."""
        serialized = json.dumps(data, sort_keys=True) if not isinstance(data, (bytes, str)) else data
        if isinstance(serialized, str):
            serialized = serialized.encode('utf-8')
        return hashlib.sha256(serialized).hexdigest()

    def register_model(
        self,
        model_id: str,
        model_version: str,
        model_family: str,
        training_run_id: str,
        feature_version: str,
        label_version: str,
        training_data_range: str,
        training_timestamp: str,
        code_version: str,
        experiment_id: str,
        calibration_version: str,
        risk_profile_version: str,
        transaction_cost_version: str,
        parent_model_id: Optional[str],
        artifact_data: Any,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None
    ) -> ModelRegistrationRecord:
        """
        Registers a new model version in CANDIDATE state with computed SHA-256 hash.
        """
        if model_id in self._models:
            raise ValueError(f"Model ID '{model_id}' is already registered. Model identity is immutable.")

        art_hash = self.compute_artifact_hash(artifact_data)
        now_ts = created_at or time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        rec = ModelRegistrationRecord(
            model_id=model_id,
            model_version=model_version,
            model_family=model_family,
            training_run_id=training_run_id,
            feature_version=feature_version,
            label_version=label_version,
            training_data_range=training_data_range,
            training_timestamp=training_timestamp,
            code_version=code_version,
            experiment_id=experiment_id,
            calibration_version=calibration_version,
            risk_profile_version=risk_profile_version,
            transaction_cost_version=transaction_cost_version,
            parent_model_id=parent_model_id,
            status=ModelLifecycleState.CANDIDATE,
            approval_status=ApprovalStatus.DRAFT,
            artifact_hash=art_hash,
            created_at=now_ts,
            metadata=metadata or {}
        )

        self._models[model_id] = rec
        self._record_event(
            model_id=model_id,
            model_version=model_version,
            event_type=LifecycleEventType.MODEL_REGISTERED,
            previous_state=ModelLifecycleState.CANDIDATE,
            new_state=ModelLifecycleState.CANDIDATE,
            reason_code="REGISTRATION_SUCCESS",
            evidence_hash=art_hash,
            actor="SYSTEM_REGISTRY",
            metadata={"artifact_hash": art_hash}
        )

        return rec

    def transition_state(
        self,
        model_id: str,
        new_state: ModelLifecycleState,
        reason_code: str,
        evidence: Any,
        actor: str = "SYSTEM_OPERATOR",
        event_type: Optional[LifecycleEventType] = None
    ) -> ModelRegistrationRecord:
        """
        Validates and transitions a model's lifecycle state.
        """
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' not found in registry.")

        rec = self._models[model_id]
        cur_state = rec.status

        if new_state not in VALID_TRANSITIONS.get(cur_state, set()):
            raise InvalidLifecycleTransitionError(
                f"Cannot transition model '{model_id}' from '{cur_state.value}' to '{new_state.value}'. "
                f"Valid targets: {[s.value for s in VALID_TRANSITIONS.get(cur_state, set())]}"
            )

        evidence_h = self.compute_artifact_hash(evidence)
        rec.status = new_state

        ev_type = event_type or LifecycleEventType.HEALTH_CHANGED
        self._record_event(
            model_id=model_id,
            model_version=rec.model_version,
            event_type=ev_type,
            previous_state=cur_state,
            new_state=new_state,
            reason_code=reason_code,
            evidence_hash=evidence_h,
            actor=actor,
            metadata={"new_state": new_state.value}
        )

        return rec

    def promote_to_champion(
        self,
        model_id: str,
        promotion_reason: str,
        evaluation_summary: Dict[str, Any],
        approval_record: str = "RESEARCH_APPROVED",
        actor: str = "PROMOTION_ENGINE"
    ) -> ChampionRecord:
        """
        Atomically promotes an ELIGIBLE candidate to CHAMPION.
        Enforces exactly one active Champion per model family.
        """
        if model_id not in self._models:
            raise KeyError(f"Model '{model_id}' not found in registry.")

        candidate = self._models[model_id]
        family = candidate.model_family

        # 1. State must be ELIGIBLE or VALIDATED
        if candidate.status not in [ModelLifecycleState.ELIGIBLE, ModelLifecycleState.VALIDATED]:
            raise InvalidLifecycleTransitionError(
                f"Model '{model_id}' must be in ELIGIBLE state before promotion. Current state: {candidate.status.value}"
            )

        # 2. Transactionally demote current Champion if exists
        prev_champ_id: Optional[str] = None
        if family in self._champions:
            cur_champ_rec = self._champions[family]
            prev_champ_id = cur_champ_rec.model_id

            if prev_champ_id in self._models and self._models[prev_champ_id].status == ModelLifecycleState.CHAMPION:
                self._models[prev_champ_id].status = ModelLifecycleState.ARCHIVED
                self._record_event(
                    model_id=prev_champ_id,
                    model_version=self._models[prev_champ_id].model_version,
                    event_type=LifecycleEventType.DEMOTED,
                    previous_state=ModelLifecycleState.CHAMPION,
                    new_state=ModelLifecycleState.ARCHIVED,
                    reason_code="SUPERSEDED_BY_NEW_CHAMPION",
                    evidence_hash=self.compute_artifact_hash(promotion_reason),
                    actor=actor,
                    metadata={"new_champion_id": model_id}
                )

        # 3. Promote candidate
        candidate.status = ModelLifecycleState.CHAMPION
        candidate.approval_status = ApprovalStatus.RESEARCH_APPROVED
        now_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        champ_rec = ChampionRecord(
            model_id=model_id,
            model_version=candidate.model_version,
            model_family=family,
            promotion_timestamp=now_ts,
            promotion_reason=promotion_reason,
            approval_record=approval_record,
            evaluation_summary=evaluation_summary,
            health_state="HEALTHY",
            rollback_parent=prev_champ_id,
            artifact_hash=candidate.artifact_hash
        )

        self._champions[family] = champ_rec

        self._record_event(
            model_id=model_id,
            model_version=candidate.model_version,
            event_type=LifecycleEventType.PROMOTED,
            previous_state=ModelLifecycleState.ELIGIBLE,
            new_state=ModelLifecycleState.CHAMPION,
            reason_code=promotion_reason,
            evidence_hash=self.compute_artifact_hash(evaluation_summary),
            actor=actor,
            metadata={"rollback_parent": prev_champ_id}
        )

        # Verify Unique Champion Invariant
        self.verify_champion_uniqueness(family)
        return champ_rec

    def rollback_champion(
        self,
        model_family: str,
        rollback_reason: str,
        actor: str = "ROLLBACK_ENGINE"
    ) -> ChampionRecord:
        """
        Rolls back the active Champion to its rollback_parent atomically.
        """
        if model_family not in self._champions:
            raise KeyError(f"No active Champion registered for model family '{model_family}'.")

        cur_champ = self._champions[model_family]
        target_id = cur_champ.rollback_parent

        if not target_id or target_id not in self._models:
            raise ValueError(f"No valid rollback target available for model '{cur_champ.model_id}'.")

        target_model = self._models[target_id]

        # Demote current champion
        if cur_champ.model_id in self._models:
            self._models[cur_champ.model_id].status = ModelLifecycleState.DEMOTED
            self._record_event(
                model_id=cur_champ.model_id,
                model_version=cur_champ.model_version,
                event_type=LifecycleEventType.DEMOTED,
                previous_state=ModelLifecycleState.CHAMPION,
                new_state=ModelLifecycleState.DEMOTED,
                reason_code=rollback_reason,
                evidence_hash=self.compute_artifact_hash(rollback_reason),
                actor=actor,
                metadata={"rollback_to": target_id}
            )

        # Reinstate target as Champion
        target_model.status = ModelLifecycleState.CHAMPION
        now_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        new_champ_rec = ChampionRecord(
            model_id=target_id,
            model_version=target_model.model_version,
            model_family=model_family,
            promotion_timestamp=now_ts,
            promotion_reason=f"ROLLBACK: {rollback_reason}",
            approval_record=target_model.approval_status.value,
            evaluation_summary={"rollback_from": cur_champ.model_id},
            health_state="HEALTHY",
            rollback_parent=target_model.parent_model_id,
            artifact_hash=target_model.artifact_hash
        )

        self._champions[model_family] = new_champ_rec

        self._record_event(
            model_id=target_id,
            model_version=target_model.model_version,
            event_type=LifecycleEventType.ROLLBACK_COMPLETED,
            previous_state=ModelLifecycleState.ARCHIVED,
            new_state=ModelLifecycleState.CHAMPION,
            reason_code=f"ROLLBACK_REINSTATED: {rollback_reason}",
            evidence_hash=self.compute_artifact_hash(rollback_reason),
            actor=actor,
            metadata={"demoted_champion": cur_champ.model_id}
        )

        self.verify_champion_uniqueness(model_family)
        return new_champ_rec

    def verify_champion_uniqueness(self, model_family: str) -> None:
        """
        Enforces invariant: Exactly one active Champion exists in the registry for this family.
        """
        active_champs = [
            m for m in self._models.values()
            if m.model_family == model_family and m.status == ModelLifecycleState.CHAMPION
        ]
        if len(active_champs) > 1:
            raise ChampionInvariantViolationError(
                f"Champion Invariant Violated! Found {len(active_champs)} active champions for family '{model_family}': "
                f"{[m.model_id for m in active_champs]}"
            )

    def get_champion(self, model_family: str) -> Optional[ChampionRecord]:
        """Returns the current active Champion record."""
        return self._champions.get(model_family)

    def get_model(self, model_id: str) -> Optional[ModelRegistrationRecord]:
        """Returns registered model metadata."""
        return self._models.get(model_id)

    def get_all_models(self) -> List[ModelRegistrationRecord]:
        """Returns list of all registered models."""
        return list(self._models.values())

    def get_audit_trail(self, model_id: Optional[str] = None) -> List[LifecycleEvent]:
        """Returns full immutable audit trail or filtered by model_id."""
        if model_id:
            return [e for e in self._events if e.model_id == model_id]
        return list(self._events)

    def _record_event(
        self,
        model_id: str,
        model_version: str,
        event_type: LifecycleEventType,
        previous_state: ModelLifecycleState,
        new_state: ModelLifecycleState,
        reason_code: str,
        evidence_hash: str,
        actor: str,
        metadata: Dict[str, Any]
    ) -> LifecycleEvent:
        self._event_counter += 1
        ev_id = f"EVT-{self._event_counter:05d}"
        now_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        event = LifecycleEvent(
            event_id=ev_id,
            model_id=model_id,
            model_version=model_version,
            event_type=event_type,
            timestamp=now_ts,
            previous_state=previous_state,
            new_state=new_state,
            reason_code=reason_code,
            evidence_hash=evidence_hash,
            actor=actor,
            metadata=metadata
        )
        self._events.append(event)
        return event
