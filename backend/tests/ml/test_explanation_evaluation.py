"""Tests for Explanation Evaluation framework."""

from ml.explanations.evaluation import (
    ExplanationEvaluator,
    ExplanationMetrics,
    HumanEvaluationTemplate,
    format_evaluation_results,
)


class TestExplanationEvaluator:
    """Test cases for ExplanationEvaluator."""

    def test_evaluate_with_all_metrics(self):
        """Test evaluation with all metrics available."""
        evaluator = ExplanationEvaluator()

        predicted = """
The chiller efficiency is declining due to refrigerant leak.

Actions:
- Check refrigerant levels (URGENCY: HIGH, Time: 2h, Cost: R 1,500)
- Inspect for visible leaks (Time: 1h)
- Schedule professional repair if needed (Cost: R 5,000)
"""

        reference = """
Chiller showing efficiency drop indicating refrigerant issues.
Need to check refrigerant levels and repair any leaks found.
"""

        actions = [
            {
                "description": "Check refrigerant levels",
                "urgency": "HIGH",
                "estimated_time_hours": 2.0,
                "estimated_cost": 1500.0,
            }
        ]

        context_docs = [
            {"title": "Refrigerant Leak Detection", "content": "Check pressures and look for visible signs"}
        ]

        metrics = evaluator.evaluate_explanation(
            predicted_explanation=predicted,
            reference_explanation=reference,
            generated_actions=actions,
            context_documents=context_docs,
        )

        assert isinstance(metrics, ExplanationMetrics)
        # Should have calculated various scores
        assert metrics.actionability_score is not None
        assert metrics.factuality_score is not None
        assert metrics.completeness_score is not None
        assert metrics.conciseness_score is not None

    def test_evaluate_without_reference(self):
        """Test evaluation without reference explanation."""
        evaluator = ExplanationEvaluator()

        predicted = """
Normal operation, no issues detected.
"""

        metrics = evaluator.evaluate_explanation(predicted_explanation=predicted, reference_explanation=None)

        assert isinstance(metrics, ExplanationMetrics)
        # ROUGE/BLEU should be None without reference
        assert metrics.rouge_1 is None
        assert metrics.bleu_score is None
        # But other metrics should still be calculated
        assert metrics.completeness_score is not None

    def test_actionability_scoring(self):
        """Test actionability score calculation."""
        evaluator = ExplanationEvaluator()

        # Test with complete actions
        complete_actions = [
            {"description": "Complete action", "urgency": "HIGH", "estimated_time_hours": 2.0, "estimated_cost": 1000.0}
        ]

        score_complete = evaluator._calculate_actionability(complete_actions)
        assert score_complete == 1.0  # Perfect score

        # Test with partial actions
        partial_actions = [
            {
                "description": "Partial action",
                "urgency": "HIGH",
                # Missing time and cost
            }
        ]

        score_partial = evaluator._calculate_actionability(partial_actions)
        assert 0.3 < score_partial < 0.7  # Partial score

        # Test with no actions
        score_none = evaluator._calculate_actionability([])
        assert score_none == 0.0

    def test_factuality_scoring(self):
        """Test factuality score calculation."""
        evaluator = ExplanationEvaluator()

        explanation = "The chiller requires refrigerant leak detection"

        context_docs = [
            {
                "title": "Chiller Maintenance Guide",
                "content": "Refrigerant leak detection is important for chiller maintenance",
            },
            {"title": "HVAC Procedures", "content": "Regular inspection prevents major failures"},
        ]

        score = evaluator._calculate_factuality(explanation, context_docs)

        assert score > 0  # Should have some matches
        assert score <= 1.0

    def test_factuality_no_context(self):
        """Test factuality with no context documents."""
        evaluator = ExplanationEvaluator()

        score = evaluator._calculate_factuality("Some explanation", [])
        assert score == 0.0

    def test_completeness_scoring(self):
        """Test completeness score calculation."""
        evaluator = ExplanationEvaluator()

        # Test complete explanation
        complete = """
The system shows high pressure (OBSERVATION) due to refrigerant overcharge (INTERPRETATION).
This could lead to compressor damage (IMPLICATION). I recommend recovering refrigerant (RECOMMENDATION).
"""
        score_complete = evaluator._calculate_completeness(complete)
        assert score_complete > 0.8  # Should be highly complete

        # Test partial explanation
        partial = """
High pressure observed. Might be overcharge.
"""
        score_partial = evaluator._calculate_completeness(partial)
        assert score_partial < 0.6  # Missing some components

    def test_conciseness_scoring(self):
        """Test conciseness score calculation."""
        evaluator = ExplanationEvaluator()

        # Test ideal length
        ideal = "This is a properly sized explanation with moderate length."
        score_ideal = evaluator._calculate_conciseness(ideal)
        assert score_ideal > 0.8

        # Test too short
        short = "Too short."
        score_short = evaluator._calculate_conciseness(short)
        assert score_short < 0.6

        # Test too long
        long = (
            "This is a very long explanation that goes on and on with many unnecessary words "
            "and redundant information that makes it difficult to read and understand quickly. " * 10
        )
        score_long = evaluator._calculate_conciseness(long)
        assert score_long < 0.6

    def test_rouge_calculation(self):
        """Test ROUGE score calculation."""
        evaluator = ExplanationEvaluator()

        predicted = "The chiller shows a refrigerant leak"
        reference = "Refrigerant leak detected in chiller system"

        rouge_scores = evaluator._calculate_similarity(predicted, reference)

        assert "rouge_1" in rouge_scores
        assert rouge_scores["rouge_1"] is not None
        assert 0 <= rouge_scores["rouge_1"] <= 1.0


class TestHumanEvaluationTemplate:
    """Test cases for HumanEvaluationTemplate."""

    def test_evaluation_form_generation(self):
        """Test generation of human evaluation form."""
        form = HumanEvaluationTemplate.get_evaluation_form()

        assert "Equipment Information" in form
        assert "Evaluation Criteria" in form
        assert "Usefulness (1-5)" in form
        assert "Action Evaluation" in form
        assert "{equipment_id}" in form  # Has template variables
        assert "{explanation}" in form

    def test_comparison_template_generation(self):
        """Test generation of comparison template."""
        template = HumanEvaluationTemplate.get_comparison_template()

        assert "Explanation A" in template
        assert "Explanation B" in template
        assert "Which explanation is more useful?" in template
        assert "Overall preference" in template
        assert "{prediction_info}" in template  # Has template variables


class TestMetricFormatting:
    """Test cases for metric formatting."""

    def test_format_results_empty(self):
        """Test formatting empty results."""
        results = format_evaluation_results([])
        assert results == {}

    def test_format_results_with_data(self):
        """Test formatting evaluation results."""
        metrics_list = [
            ExplanationMetrics(
                actionability_score=0.8, factuality_score=0.7, completeness_score=0.9, conciseness_score=0.85
            ),
            ExplanationMetrics(
                actionability_score=0.7, factuality_score=0.75, completeness_score=0.8, conciseness_score=0.8
            ),
        ]

        results = format_evaluation_results(metrics_list)

        assert "actionability_score" in results
        assert "factuality_score" in results
        assert "completeness_score" in results
        assert "conciseness_score" in results

        # Check statistics
        for _metric_name, stats in results.items():
            assert "mean" in stats
            assert "std" in stats
            assert "min" in stats
            assert "max" in stats
            assert stats["mean"] > 0
            assert stats["std"] >= 0

    def test_format_results_mixed_none_values(self):
        """Test formatting with mixed None values."""
        metrics_list = [
            ExplanationMetrics(actionability_score=0.8, factuality_score=None),
            ExplanationMetrics(actionability_score=0.7, factuality_score=0.9),
            ExplanationMetrics(actionability_score=None, factuality_score=0.85),
        ]

        results = format_evaluation_results(metrics_list)

        # Should only include metrics with non-None values
        assert "actionability_score" in results
        assert "factuality_score" in results

        # Calculate expected stats
        action_stats = results["actionability_score"]
        assert action_stats["mean"] == 0.75  # (0.8 + 0.7) / 2
        assert action_stats["count"] == 2


class TestMetricsDataClass:
    """Test cases for ExplanationMetrics dataclass."""

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = ExplanationMetrics(actionability_score=0.8, factuality_score=0.7, usefulness_rating=4.5)

        result_dict = metrics.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["actionability_score"] == 0.8
        assert result_dict["factuality_score"] == 0.7
        assert result_dict["usefulness_rating"] == 4.5
        assert result_dict["bert_precision"] is None  # Should include None values
        assert "timestamp" in result_dict
        assert result_dict["evaluator_version"] == "1.0.0"

    def test_default_timestamp(self):
        """Test that timestamp is auto-generated."""
        metrics = ExplanationMetrics()

        assert metrics.timestamp is not None
        assert isinstance(metrics.timestamp, str)
        assert "T" in metrics.timestamp  # ISO format
