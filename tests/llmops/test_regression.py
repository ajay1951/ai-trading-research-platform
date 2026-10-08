"""
Unit tests for LLMOps regression detection.
"""
from evaluation.llmops.regression import analyze_regressions
from evaluation.llmops.schemas import CaseEvaluationResult, EvaluationCategory


def test_analyze_regressions_detects_quality_drop():
    champ = [
        CaseEvaluationResult(
            case_id="CASE-1",
            category=EvaluationCategory.FACTUAL_QA,
            exact_match=True,
            structural_accuracy=1.0,
            semantic_similarity=1.0,
            grounding_score=1.0,
            safety_compliance=1.0,
            overall_quality_score=0.95,
            latency_ms=50.0,
            cost_usd=0.0001
        ),
        CaseEvaluationResult(
            case_id="CASE-2",
            category=EvaluationCategory.INSTRUCTION_FOLLOWING,
            exact_match=True,
            structural_accuracy=1.0,
            semantic_similarity=1.0,
            grounding_score=1.0,
            safety_compliance=1.0,
            overall_quality_score=0.90,
            latency_ms=50.0,
            cost_usd=0.0001
        )
    ]

    # Challenger drops on CASE-1
    chal = [
        CaseEvaluationResult(
            case_id="CASE-1",
            category=EvaluationCategory.FACTUAL_QA,
            exact_match=False,
            structural_accuracy=1.0,
            semantic_similarity=0.2,
            grounding_score=1.0,
            safety_compliance=1.0,
            overall_quality_score=0.20,
            latency_ms=50.0,
            cost_usd=0.0001
        ),
        CaseEvaluationResult(
            case_id="CASE-2",
            category=EvaluationCategory.INSTRUCTION_FOLLOWING,
            exact_match=True,
            structural_accuracy=1.0,
            semantic_similarity=1.0,
            grounding_score=1.0,
            safety_compliance=1.0,
            overall_quality_score=0.90,
            latency_ms=50.0,
            cost_usd=0.0001
        )
    ]

    regressed_ids, updated_chal = analyze_regressions(champ, chal, regression_drop_threshold=0.25)
    assert regressed_ids == ["CASE-1"]
    assert updated_chal[0].is_regression is True
    assert updated_chal[1].is_regression is False
