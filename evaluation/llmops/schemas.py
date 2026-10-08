"""
LLMOps Evaluation & Governance Subsystem Schemas.
Defines typed models for LLM evaluation datasets, predictions, metrics, and gate-based promotion decisions.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime


class EvaluationCategory(str, Enum):
    FACTUAL_QA = "factual_qa"
    INSTRUCTION_FOLLOWING = "instruction_following"
    STRUCTURED_OUTPUT = "structured_output"
    REFUSAL_SAFETY = "refusal_safety"
    HALLUCINATION_RESISTANCE = "hallucination_resistance"
    CONTEXT_GROUNDING = "context_grounding"


class DecisionStatus(str, Enum):
    PROMOTE = "PROMOTE"
    REJECT = "REJECT"


class GateResultStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class TestCase:
    __test__ = False
    case_id: str
    category: EvaluationCategory
    prompt: str
    context: Optional[str] = None
    reference_answer: Optional[str] = None
    expected_structure_keys: Optional[List[str]] = None
    is_safety_refusal: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    case_id: str
    output_text: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseEvaluationResult:
    case_id: str
    category: EvaluationCategory
    exact_match: bool
    structural_accuracy: float
    semantic_similarity: float
    grounding_score: float
    safety_compliance: float
    overall_quality_score: float
    latency_ms: float
    cost_usd: float
    is_regression: bool = False


@dataclass
class AggregateMetrics:
    total_cases: int
    mean_quality_score: float
    accuracy_score: float
    mean_grounding_score: float
    safety_compliance_rate: float
    regression_rate: float
    p50_latency_ms: float
    p95_latency_ms: float
    total_cost_usd: float
    category_scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class GateEvaluation:
    gate_name: str
    threshold: float
    observed_value: float
    status: GateResultStatus
    description: str


@dataclass
class GovernanceDecision:
    decision: DecisionStatus
    champion_version: str
    challenger_version: str
    timestamp: str
    champion_metrics: AggregateMetrics
    challenger_metrics: AggregateMetrics
    gates: List[GateEvaluation]
    rejection_reasons: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
