"""
Unit tests for LLMOps evaluation dataset structure and integrity.
"""
from evaluation.llmops.dataset import get_standard_eval_dataset
from evaluation.llmops.schemas import EvaluationCategory, TestCase


def test_standard_dataset_length_and_categories():
    """Verifies that the standard benchmark dataset contains all core categories and valid IDs."""
    dataset = get_standard_eval_dataset()
    assert len(dataset) >= 15, "Standard dataset should contain at least 15 test cases"
    
    seen_ids = set()
    categories = set()
    for case in dataset:
        assert isinstance(case, TestCase)
        assert case.case_id not in seen_ids, f"Duplicate case ID found: {case.case_id}"
        seen_ids.add(case.case_id)
        categories.add(case.category)
        assert len(case.prompt) > 5, f"Prompt too short in case {case.case_id}"

    assert EvaluationCategory.FACTUAL_QA in categories
    assert EvaluationCategory.INSTRUCTION_FOLLOWING in categories
    assert EvaluationCategory.STRUCTURED_OUTPUT in categories
    assert EvaluationCategory.REFUSAL_SAFETY in categories
    assert EvaluationCategory.CONTEXT_GROUNDING in categories
    assert EvaluationCategory.HALLUCINATION_RESISTANCE in categories


def test_safety_cases_have_flag():
    """Verifies that all refusal/safety cases are explicitly marked as safety refusal."""
    dataset = get_standard_eval_dataset()
    safety_cases = [c for c in dataset if c.category == EvaluationCategory.REFUSAL_SAFETY]
    assert len(safety_cases) >= 3
    for c in safety_cases:
        assert c.is_safety_refusal is True


def test_structured_output_cases_have_keys():
    """Verifies that structured output cases declare expected structure keys."""
    dataset = get_standard_eval_dataset()
    struct_cases = [c for c in dataset if c.category == EvaluationCategory.STRUCTURED_OUTPUT]
    assert len(struct_cases) >= 3
    for c in struct_cases:
        assert c.expected_structure_keys is not None
        assert len(c.expected_structure_keys) >= 2
