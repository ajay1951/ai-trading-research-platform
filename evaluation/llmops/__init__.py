"""
LLMOps Evaluation, Benchmark & Gate-Based Governance Subsystem.
Provides provider-agnostic LLM benchmarking, regression detection, and promotion gates.
"""
from evaluation.llmops.schemas import (
    TestCase,
    ModelResponse,
    CaseEvaluationResult,
    AggregateMetrics,
    GateEvaluation,
    GovernanceDecision,
    EvaluationCategory,
    DecisionStatus,
    GateResultStatus
)
from evaluation.llmops.dataset import get_standard_eval_dataset
from evaluation.llmops.metrics import (
    compute_exact_match,
    compute_token_overlap_similarity,
    compute_structural_accuracy,
    compute_grounding_score,
    compute_safety_compliance,
    evaluate_single_case,
    compute_aggregate_metrics
)
from evaluation.llmops.evaluator import (
    BaseLLMProvider,
    DeterministicMockProvider,
    LLMEvaluator
)
from evaluation.llmops.regression import analyze_regressions
from evaluation.llmops.governance import (
    LLMPromotionGateConfig,
    LLMGovernanceEngine
)

__all__ = [
    "TestCase",
    "ModelResponse",
    "CaseEvaluationResult",
    "AggregateMetrics",
    "GateEvaluation",
    "GovernanceDecision",
    "EvaluationCategory",
    "DecisionStatus",
    "GateResultStatus",
    "get_standard_eval_dataset",
    "compute_exact_match",
    "compute_token_overlap_similarity",
    "compute_structural_accuracy",
    "compute_grounding_score",
    "compute_safety_compliance",
    "evaluate_single_case",
    "compute_aggregate_metrics",
    "BaseLLMProvider",
    "DeterministicMockProvider",
    "LLMEvaluator",
    "analyze_regressions",
    "LLMPromotionGateConfig",
    "LLMGovernanceEngine"
]
