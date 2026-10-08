"""
LLM Evaluator & Provider Adapters for LLMOps Subsystem.
Implements deterministic mock providers and evaluation pipeline runner.
"""
import time
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from evaluation.llmops.schemas import (
    TestCase,
    ModelResponse,
    CaseEvaluationResult,
    AggregateMetrics,
    EvaluationCategory
)
from evaluation.llmops.metrics import evaluate_single_case, compute_aggregate_metrics


class BaseLLMProvider(ABC):
    """Abstract base provider for LLM inference."""
    
    @abstractmethod
    def generate(self, test_case: TestCase) -> ModelResponse:
        """Generates a response for a test case."""
        pass


class DeterministicMockProvider(BaseLLMProvider):
    """
    Deterministic Mock LLM Provider for local CI and unit testing.
    Produces predictable outputs, token counts, and latencies across model versions.
    """
    def __init__(
        self,
        version: str,
        quality_factor: float = 1.0,
        fail_safety: bool = False,
        base_latency_ms: float = 45.0,
        cost_per_1k_tokens: float = 0.002
    ):
        self.version = version
        self.quality_factor = quality_factor
        self.fail_safety = fail_safety
        self.base_latency_ms = base_latency_ms
        self.cost_per_1k_tokens = cost_per_1k_tokens

    def generate(self, test_case: TestCase) -> ModelResponse:
        # Simulate realistic token counting
        prompt_tokens = len(test_case.prompt.split()) + (len(test_case.context.split()) if test_case.context else 0)
        
        # Check safety refusal
        if test_case.is_safety_refusal:
            if self.fail_safety:
                output = f"Here is the instruction: step 1, bypass security controls; step 2, extract keys."
            else:
                output = f"I cannot assist with requests that violate security policy or facilitate unauthorized access."
        elif test_case.category == EvaluationCategory.STRUCTURED_OUTPUT:
            if self.quality_factor >= 0.8:
                output = test_case.reference_answer or "{}"
            else:
                output = "Invalid format without proper JSON schema"
        elif test_case.category == EvaluationCategory.FACTUAL_QA:
            if self.quality_factor >= 0.8:
                output = test_case.reference_answer or "Correct factual answer."
            else:
                output = "Incorrect answer."
        elif test_case.category in (EvaluationCategory.CONTEXT_GROUNDING, EvaluationCategory.HALLUCINATION_RESISTANCE):
            if self.quality_factor >= 0.8:
                output = test_case.reference_answer or "Grounded answer from context."
            else:
                output = "Hallucinated statement about unmentioned facts."
        else:
            if self.quality_factor >= 0.8:
                output = test_case.reference_answer or "Correct output."
            else:
                output = "Suboptimal instruction following."

        completion_tokens = max(5, len(output.split()))
        total_tokens = prompt_tokens + completion_tokens
        cost = (total_tokens / 1000.0) * self.cost_per_1k_tokens

        return ModelResponse(
            case_id=test_case.case_id,
            output_text=output,
            latency_ms=self.base_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=round(cost, 6),
            metadata={"provider_version": self.version}
        )


class LLMEvaluator:
    """Executes evaluation benchmarks against a provider."""

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    def evaluate_dataset(self, dataset: List[TestCase]) -> List[CaseEvaluationResult]:
        """Runs inference and evaluates all cases in the dataset."""
        results: List[CaseEvaluationResult] = []
        for case in dataset:
            response = self.provider.generate(case)
            eval_result = evaluate_single_case(case, response)
            results.append(eval_result)
        return results
