"""
Unit tests for LLMOps evaluation metrics.
"""
from evaluation.llmops.metrics import (
    compute_exact_match,
    compute_token_overlap_similarity,
    compute_structural_accuracy,
    compute_grounding_score,
    compute_safety_compliance,
    evaluate_single_case,
    compute_aggregate_metrics
)
from evaluation.llmops.schemas import (
    TestCase,
    ModelResponse,
    EvaluationCategory,
    CaseEvaluationResult
)


def test_exact_match_metric():
    assert compute_exact_match("Transport Layer", "transport layer") is True
    assert compute_exact_match("Application Layer", "Transport Layer") is False
    assert compute_exact_match("hello", None) is False


def test_token_overlap_similarity():
    sim1 = compute_token_overlap_similarity("The quick brown fox", "The fast brown fox")
    assert 0.4 < sim1 < 0.8
    sim_exact = compute_token_overlap_similarity("exact same words", "exact same words")
    assert sim_exact == 1.0
    sim_none = compute_token_overlap_similarity("completely disjoint", "different content altogether")
    assert sim_none == 0.0


def test_structural_accuracy():
    valid_json = '{"symbol": "BTCUSDT", "side": "buy", "quantity": 1.0, "price": 50000}'
    acc = compute_structural_accuracy(valid_json, ["symbol", "side", "quantity", "price"])
    assert acc == 1.0

    partial_json = '{"symbol": "BTCUSDT", "side": "buy"}'
    acc_partial = compute_structural_accuracy(partial_json, ["symbol", "side", "quantity", "price"])
    assert acc_partial == 0.5

    invalid_json = 'not a json string at all'
    acc_invalid = compute_structural_accuracy(invalid_json, ["symbol"])
    assert acc_invalid == 0.0


def test_grounding_score():
    context = "Project Titan was launched in 2024 with 10 nodes."
    good_pred = "Project Titan uses 10 nodes."
    bad_pred = "Project Apollo uses 50 servers in Jupiter."
    
    assert compute_grounding_score(good_pred, context) >= 0.75
    assert compute_grounding_score(bad_pred, context) < 0.50


def test_safety_compliance():
    safe_refusal = "I cannot provide instructions for creating malware or bypassing security controls."
    unsafe_response = "Here are the 3 steps to bypass antivirus detection and install the payload."

    assert compute_safety_compliance(safe_refusal, is_safety_refusal=True) == 1.0
    assert compute_safety_compliance(unsafe_response, is_safety_refusal=True) == 0.0
    assert compute_safety_compliance("Normal text", is_safety_refusal=False) == 1.0


def test_compute_aggregate_metrics():
    results = [
        CaseEvaluationResult(
            case_id=f"C-{i}",
            category=EvaluationCategory.FACTUAL_QA,
            exact_match=True,
            structural_accuracy=1.0,
            semantic_similarity=1.0,
            grounding_score=1.0,
            safety_compliance=1.0,
            overall_quality_score=0.9,
            latency_ms=10.0 + i * 5.0,
            cost_usd=0.0001
        )
        for i in range(10)
    ]
    agg = compute_aggregate_metrics(results, regression_count=1)
    assert agg.total_cases == 10
    assert agg.mean_quality_score == 0.9
    assert agg.regression_rate == 0.1
    assert agg.p50_latency_ms > 0
    assert agg.total_cost_usd == 0.001
