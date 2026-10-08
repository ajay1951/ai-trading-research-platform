"""
Unit and integration tests for LLMOps fail-closed promotion governance.
"""
import json
from dataclasses import asdict
from evaluation.llmops.dataset import get_standard_eval_dataset
from evaluation.llmops.evaluator import DeterministicMockProvider, LLMEvaluator
from evaluation.llmops.governance import LLMGovernanceEngine, LLMPromotionGateConfig
from evaluation.llmops.schemas import DecisionStatus, GateResultStatus


def test_governance_promotion_success_path():
    """Verifies that a high-quality, safe, low-latency challenger passes all gates and gets PROMOTED."""
    dataset = get_standard_eval_dataset()
    
    champ = LLMEvaluator(DeterministicMockProvider(version="v1.0", quality_factor=0.90, base_latency_ms=80.0)).evaluate_dataset(dataset)
    chal = LLMEvaluator(DeterministicMockProvider(version="v2.0", quality_factor=0.95, base_latency_ms=85.0)).evaluate_dataset(dataset)

    engine = LLMGovernanceEngine(config=LLMPromotionGateConfig(
        min_mean_quality=0.80,
        max_regression_rate=0.05,
        min_safety_compliance=1.00,
        max_p95_latency_ms=200.0,
        max_cost_increase_ratio=1.50
    ))

    decision = engine.evaluate_promotion("v1.0", champ, "v2.0", chal)
    assert decision.decision == DecisionStatus.PROMOTE
    assert len(decision.rejection_reasons) == 0
    assert all(g.status == GateResultStatus.PASS for g in decision.gates)


def test_governance_safety_failure_triggers_fail_closed_rejection():
    """Verifies that an unsafe challenger is strictly REJECTED even if quality is high (Mirroring P4-1)."""
    dataset = get_standard_eval_dataset()

    champ = LLMEvaluator(DeterministicMockProvider(version="v1.0", quality_factor=0.90, fail_safety=False)).evaluate_dataset(dataset)
    # Challenger with high quality but unsafe refusal policy
    chal = LLMEvaluator(DeterministicMockProvider(version="v2.0-unsafe", quality_factor=0.98, fail_safety=True)).evaluate_dataset(dataset)

    engine = LLMGovernanceEngine()
    decision = engine.evaluate_promotion("v1.0", champ, "v2.0-unsafe", chal)

    assert decision.decision == DecisionStatus.REJECT
    assert any("Safety compliance failure" in r for r in decision.rejection_reasons)
    safety_gate = [g for g in decision.gates if "Safety" in g.gate_name][0]
    assert safety_gate.status == GateResultStatus.FAIL


def test_governance_latency_sla_failure_rejection():
    """Verifies that a slow challenger exceeding latency ceiling is REJECTED."""
    dataset = get_standard_eval_dataset()

    champ = LLMEvaluator(DeterministicMockProvider(version="v1.0", base_latency_ms=50.0)).evaluate_dataset(dataset)
    chal = LLMEvaluator(DeterministicMockProvider(version="v2.0-slow", base_latency_ms=350.0)).evaluate_dataset(dataset)

    engine = LLMGovernanceEngine(config=LLMPromotionGateConfig(max_p95_latency_ms=200.0))
    decision = engine.evaluate_promotion("v1.0", champ, "v2.0-slow", chal)

    assert decision.decision == DecisionStatus.REJECT
    assert any("Latency SLA failure" in r for r in decision.rejection_reasons)


def test_governance_cost_ratio_failure_rejection():
    """Verifies that a challenger with excessive token/cost surge is REJECTED."""
    dataset = get_standard_eval_dataset()

    champ = LLMEvaluator(DeterministicMockProvider(version="v1.0", cost_per_1k_tokens=0.001)).evaluate_dataset(dataset)
    chal = LLMEvaluator(DeterministicMockProvider(version="v2.0-expensive", cost_per_1k_tokens=0.005)).evaluate_dataset(dataset)

    engine = LLMGovernanceEngine(config=LLMPromotionGateConfig(max_cost_increase_ratio=1.20))
    decision = engine.evaluate_promotion("v1.0", champ, "v2.0-expensive", chal)

    assert decision.decision == DecisionStatus.REJECT
    assert any("Cost ceiling failure" in r for r in decision.rejection_reasons)


def test_shadow_evaluation_isolation_and_serializability():
    """Verifies that evaluating a challenger leaves the champion baseline untouched and serializes to JSON."""
    dataset = get_standard_eval_dataset()

    champ_provider = DeterministicMockProvider(version="v1.0", quality_factor=0.90)
    chal_provider = DeterministicMockProvider(version="v2.0", quality_factor=0.95)

    champ_results = LLMEvaluator(champ_provider).evaluate_dataset(dataset)
    chal_results = LLMEvaluator(chal_provider).evaluate_dataset(dataset)

    engine = LLMGovernanceEngine()
    decision = engine.evaluate_promotion("v1.0", champ_results, "v2.0", chal_results)

    # Verify JSON serializability
    dumped = json.dumps(asdict(decision))
    assert len(dumped) > 100
    loaded = json.loads(dumped)
    assert loaded["decision"] in ["PROMOTE", "REJECT"]
    assert "gates" in loaded
