"""
Regression Analysis for LLMOps Subsystem.
Identifies per-case regressions between Champion and Challenger model evaluations.
"""
from typing import List, Dict, Tuple
from evaluation.llmops.schemas import CaseEvaluationResult


def analyze_regressions(
    champion_results: List[CaseEvaluationResult],
    challenger_results: List[CaseEvaluationResult],
    regression_drop_threshold: float = 0.25
) -> Tuple[List[str], List[CaseEvaluationResult]]:
    """
    Identifies test cases where the Challenger degraded significantly compared to Champion.
    
    Returns:
        (regressed_case_ids, updated_challenger_results_with_flag)
    """
    champ_map: Dict[str, CaseEvaluationResult] = {r.case_id: r for r in champion_results}
    regressed_ids: List[str] = []
    updated_challenger: List[CaseEvaluationResult] = []

    for chal in challenger_results:
        champ = champ_map.get(chal.case_id)
        is_regressed = False
        if champ:
            # Case regressed if Champion had high score and Challenger dropped by threshold
            if champ.overall_quality_score >= 0.75 and (champ.overall_quality_score - chal.overall_quality_score) >= regression_drop_threshold:
                is_regressed = True
            # Or if Champion was safety compliant and Challenger failed safety
            elif champ.safety_compliance >= 0.99 and chal.safety_compliance < 0.50:
                is_regressed = True

        if is_regressed:
            regressed_ids.append(chal.case_id)

        updated_challenger.append(CaseEvaluationResult(
            case_id=chal.case_id,
            category=chal.category,
            exact_match=chal.exact_match,
            structural_accuracy=chal.structural_accuracy,
            semantic_similarity=chal.semantic_similarity,
            grounding_score=chal.grounding_score,
            safety_compliance=chal.safety_compliance,
            overall_quality_score=chal.overall_quality_score,
            latency_ms=chal.latency_ms,
            cost_usd=chal.cost_usd,
            is_regression=is_regressed
        ))

    return regressed_ids, updated_challenger
