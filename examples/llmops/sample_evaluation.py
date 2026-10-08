"""
Sample LLMOps Evaluation Runner.
Executes deterministic comparative evaluation between Champion and Challenger models
and writes machine-readable governance artifacts to results/llmops/sample_evaluation.json.
"""
import os
import sys
import json
from dataclasses import asdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from evaluation.llmops.dataset import get_standard_eval_dataset
from evaluation.llmops.evaluator import DeterministicMockProvider, LLMEvaluator
from evaluation.llmops.governance import LLMGovernanceEngine, LLMPromotionGateConfig


def run_sample_llmops_evaluation(output_path: str = "results/llmops/sample_evaluation.json"):
    """Runs a complete LLMOps evaluation pipeline and persists the artifact."""
    dataset = get_standard_eval_dataset()

    # Champion Provider (v1.0 - Stable baseline)
    champ_provider = DeterministicMockProvider(
        version="v1.0-champion",
        quality_factor=0.92,
        fail_safety=False,
        base_latency_ms=85.0,
        cost_per_1k_tokens=0.0015
    )
    champ_evaluator = LLMEvaluator(champ_provider)
    champ_results = champ_evaluator.evaluate_dataset(dataset)

    # Challenger Provider (v2.0 - Higher quality, but test fail-closed governance scenario)
    chal_provider = DeterministicMockProvider(
        version="v2.0-candidate",
        quality_factor=0.96,
        fail_safety=False,
        base_latency_ms=92.0,
        cost_per_1k_tokens=0.0018
    )
    chal_evaluator = LLMEvaluator(chal_provider)
    chal_results = chal_evaluator.evaluate_dataset(dataset)

    # Governance Engine
    governance = LLMGovernanceEngine(config=LLMPromotionGateConfig(
        min_mean_quality=0.85,
        max_regression_rate=0.05,
        min_safety_compliance=1.00,
        max_p95_latency_ms=200.0,
        max_cost_increase_ratio=1.30
    ))

    decision = governance.evaluate_promotion(
        champion_version="v1.0-champion",
        champion_results=champ_results,
        challenger_version="v2.0-candidate",
        challenger_results=chal_results
    )

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(asdict(decision), f, indent=2)

    print(f"[LLMOps] Evaluation complete. Decision: {decision.decision.value}")
    print(f"[LLMOps] Champion Quality: {decision.champion_metrics.mean_quality_score:.4f}, Challenger Quality: {decision.challenger_metrics.mean_quality_score:.4f}")
    print(f"[LLMOps] Saved artifact to: {output_path}")

    return decision


if __name__ == "__main__":
    run_sample_llmops_evaluation()
