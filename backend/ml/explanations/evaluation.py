"""Evaluation framework for ML explanations.

Provides metrics for assessing explanation quality:
- Semantic similarity (BERTScore, ROUGE, BLEU)
- Actionability metrics
- Human evaluation templates
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import numpy as np
from datetime import datetime

# Optional imports for advanced metrics
try:
    from bert_score import score as bert_score

    BERT_SCORE_AVAILABLE = True
except ImportError:
    BERT_SCORE_AVAILABLE = False

try:
    from rouge_score import rouge_scorer

    ROUGE_AVAILABLE = True
except ImportError:
    ROUGE_AVAILABLE = False

try:
    import nltk
    from nltk.translate.bleu_score import sentence_bleu

    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ExplanationMetrics:
    """Metrics for evaluating explanation quality."""

    # Semantic similarity metrics
    bert_precision: Optional[float] = None
    bert_recall: Optional[float] = None
    bert_f1: Optional[float] = None
    rouge_1: Optional[float] = None
    rouge_2: Optional[float] = None
    rouge_l: Optional[float] = None
    bleu_score: Optional[float] = None

    # Content metrics
    actionability_score: Optional[float] = None  # 0-1 based on extractable actions
    factuality_score: Optional[float] = None  # Based on RAG grounding
    completeness_score: Optional[float] = None  # Coverage of key aspects
    conciseness_score: Optional[float] = None  # Inverse of verbosity

    # Human evaluation metrics (when available)
    usefulness_rating: Optional[float] = None  # 1-5 scale
    clarity_rating: Optional[float] = None  # 1-5 scale
    trustworthiness_rating: Optional[float] = None  # 1-5 scale

    # Metadata
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    evaluator_version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class ExplanationEvaluator:
    """Evaluates ML explanations for quality and usefulness."""

    def __init__(self):
        """Initialize evaluator with optional metric calculators."""
        self.bert_scorer = None
        self.rouge_scorer = None

        if BERT_SCORE_AVAILABLE:
            try:
                # Initialize BERT scorer
                pass  # Will be used in evaluate_similarity
            except Exception as e:
                logger.warning(f"BERT scorer initialization failed: {e}")

        if ROUGE_AVAILABLE:
            try:
                self.rouge_scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
            except Exception as e:
                logger.warning(f"ROUGE scorer initialization failed: {e}")

    def evaluate_explanation(
        self,
        predicted_explanation: str,
        reference_explanation: Optional[str] = None,
        generated_actions: Optional[List[Dict]] = None,
        context_documents: Optional[List[Dict]] = None,
    ) -> ExplanationMetrics:
        """
        Evaluate a generated explanation against references.

        Args:
            predicted_explanation: The generated explanation text
            reference_explanation: Optional reference/gold standard explanation
            generated_actions: Optional list of extracted action items
            context_documents: Optional list of RAG context documents

        Returns:
            ExplanationMetrics object with evaluation scores
        """
        metrics = ExplanationMetrics()

        # Semantic similarity metrics (if reference provided)
        if reference_explanation:
            similarity_metrics = self._calculate_similarity(predicted_explanation, reference_explanation)
            metrics.bert_precision = similarity_metrics.get("bert_precision")
            metrics.bert_recall = similarity_metrics.get("bert_recall")
            metrics.bert_f1 = similarity_metrics.get("bert_f1")
            metrics.rouge_1 = similarity_metrics.get("rouge_1")
            metrics.rouge_2 = similarity_metrics.get("rouge_2")
            metrics.rouge_l = similarity_metrics.get("rouge_l")
            metrics.bleu_score = similarity_metrics.get("bleu_score")

        # Actionability score based on extracted actions
        if generated_actions:
            metrics.actionability_score = self._calculate_actionability(generated_actions)

        # Factuality score based on RAG grounding
        if context_documents:
            metrics.factuality_score = self._calculate_factuality(predicted_explanation, context_documents)

        # Intrinsic metrics
        metrics.completeness_score = self._calculate_completeness(predicted_explanation)
        metrics.conciseness_score = self._calculate_conciseness(predicted_explanation)

        return metrics

    def _calculate_similarity(self, predicted: str, reference: str) -> Dict[str, Optional[float]]:
        """Calculate semantic similarity between texts."""
        metrics = {}

        # ROUGE scores
        if self.rouge_scorer and ROUGE_AVAILABLE:
            try:
                rouge_scores = self.rouge_scorer.score(reference, predicted)
                metrics["rouge_1"] = rouge_scores["rouge1"].fmeasure
                metrics["rouge_2"] = rouge_scores["rouge2"].fmeasure
                metrics["rouge_l"] = rouge_scores["rougeL"].fmeasure
            except Exception as e:
                logger.warning(f"ROUGE calculation failed: {e}")
        else:
            # Lightweight ROUGE-1 fallback based on unigram F1 overlap
            ref_tokens = reference.lower().split()
            pred_tokens = predicted.lower().split()
            if ref_tokens and pred_tokens:
                ref_counts = {}
                for tok in ref_tokens:
                    ref_counts[tok] = ref_counts.get(tok, 0) + 1
                overlap = 0
                for tok in pred_tokens:
                    if ref_counts.get(tok, 0) > 0:
                        overlap += 1
                        ref_counts[tok] -= 1
                precision = overlap / len(pred_tokens)
                recall = overlap / len(ref_tokens)
                f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
                metrics["rouge_1"] = f1
                metrics["rouge_2"] = 0.0
                metrics["rouge_l"] = 0.0

        # BLEU score
        if NLTK_AVAILABLE:
            try:
                reference_tokens = reference.lower().split()
                predicted_tokens = predicted.lower().split()
                metrics["bleu_score"] = sentence_bleu([reference_tokens], predicted_tokens)
            except Exception as e:
                logger.warning(f"BLEU calculation failed: {e}")

        # BERTScore (computationally expensive, optional)
        if BERT_SCORE_AVAILABLE:
            try:
                # BERTScore requires batch processing, skip for single examples
                pass
            except Exception as e:
                logger.warning(f"BERTScore calculation failed: {e}")

        return metrics

    def _calculate_actionability(self, actions: List[Dict]) -> float:
        """
        Calculate actionability score (0-1).

        Based on presence of required action fields:
        - description
        - urgency/priority
        - estimated_time
        - estimated_cost
        """
        if not actions:
            return 0.0

        total_score = 0.0
        for action in actions:
            action_score = 0.0

            # Check for description
            if action.get("description"):
                action_score += 0.3

            # Check for urgency/priority
            if action.get("urgency") or action.get("priority"):
                action_score += 0.3

            # Check for time estimate
            if action.get("estimated_time_hours") is not None:
                action_score += 0.2

            # Check for cost estimate
            if action.get("estimated_cost") is not None:
                action_score += 0.2

            total_score += action_score

        # Average across all actions
        return total_score / len(actions)

    def _calculate_factuality(self, explanation: str, context_docs: List[Dict]) -> float:
        """
        Calculate factuality score based on RAG grounding.

        Checks if explanation content can be grounded in provided context.
        """
        if not context_docs:
            return 0.0

        explanation_lower = explanation.lower()
        total_matches = 0
        total_checks = 0

        # Extract key terms from context documents
        key_terms = []
        for doc in context_docs:
            # Add title words
            title = doc.get("title", "")
            key_terms.extend(title.lower().split())

            # Add key concepts from content (first few words)
            content = doc.get("content", "")
            if content:
                # Extract equipment-specific terms (simple approach)
                words = content.lower().split()
                # Filter out common words
                common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to"}
                key_terms.extend([w for w in words[:50] if w not in common_words])

        # Remove duplicates
        key_terms = list(set(key_terms))

        # Check how many key terms appear in explanation
        for term in key_terms:
            if len(term) > 3:  # Skip very short words
                total_checks += 1
                if term in explanation_lower:
                    total_matches += 1

        return total_matches / total_checks if total_checks > 0 else 0.0

    def _calculate_completeness(self, explanation: str) -> float:
        """Calculate completeness score based on content coverage."""
        if not explanation:
            return 0.0

        score = 0.0
        explanation_lower = explanation.lower()

        # Check for key explanation components
        completeness_checks = [
            ("observation", ["observed", "showing", "shows", "indicates"]),
            ("interpretation", ["because", "due to", "caused by", "suggests"]),
            ("implication", ["could lead to", "may result in", "impact"]),
            ("recommendation", ["recommend", "should", "advised to", "consider"]),
        ]

        for component, keywords in completeness_checks:
            if any(keyword in explanation_lower for keyword in keywords):
                score += 0.25

        return score

    def _calculate_conciseness(self, explanation: str) -> float:
        """Calculate conciseness score (inverse of verbosity)."""
        if not explanation:
            return 0.0

        words = explanation.split()
        sentences = explanation.split(".")

        # Ideal: 8-60 words, 1-3 sentences
        word_count = len(words)
        sentence_count = len([s for s in sentences if s.strip()])

        # Word count score (penalize too short or too long)
        if 8 <= word_count <= 60:
            word_score = 1.0
        elif word_count < 4:
            word_score = 0.3
        elif word_count < 8:
            word_score = 0.6
        elif word_count > 200:
            word_score = 0.3
        else:
            word_score = 0.7

        # Sentence count score
        if 1 <= sentence_count <= 3:
            sentence_score = 1.0
        elif sentence_count > 6:
            sentence_score = 0.5
        else:
            sentence_score = 0.8

        # Combine scores (weighted average)
        return 0.6 * word_score + 0.4 * sentence_score


class HumanEvaluationTemplate:
    """Templates for human evaluation of explanations."""

    @staticmethod
    def get_evaluation_form() -> str:
        """Get human evaluation form template."""
        return """
# ML Explanation Human Evaluation Form

## Equipment Information
- Equipment ID: {equipment_id}
- Equipment Type: {equipment_type}
- Prediction Type: {prediction_type}

## Generated Explanation
{explanation}

## Evaluation Criteria

### 1. Usefulness (1-5)
Does this explanation help you understand the prediction and decide on actions?
- 1: Not useful at all
- 3: Somewhat useful
- 5: Extremely useful

Rating: ___/5

### 2. Clarity (1-5)
Is the explanation clear and easy to understand?
- 1: Very confusing
- 3: Moderately clear
- 5: Very clear

Rating: ___/5

### 3. Trustworthiness (1-5)
Do you trust this explanation? Does it seem well-grounded?
- 1: Not trustworthy
- 3: Neutral
- 5: Very trustworthy

Rating: ___/5

### 4. Actionability (1-5)
Does the explanation provide actionable next steps?
- 1: Not actionable
- 3: Some actions suggested
- 5: Very actionable

Rating: ___/5

### 5. Completeness (1-5)
Does the explanation cover all important aspects?
- 1: Missing critical information
- 3: Covers basics
- 5: Comprehensive

Rating: ___/5

## Extracted Actions
{actions}

### Action Evaluation
- Are the actions appropriate? Yes / No
- Are time estimates reasonable? Yes / No
- Are cost estimates reasonable? Yes / No

## Additional Feedback
What would improve this explanation?

---
"""

    @staticmethod
    def get_comparison_template() -> str:
        """Get template for comparing multiple explanations."""
        return """
# ML Explanation Comparison

## Equipment: {equipment_id} ({equipment_type})

### Prediction
{prediction_info}

### Explanation A
{explanation_a}

### Explanation B
{explanation_b}

### Comparison Questions

1. Which explanation is more useful? (A / B / Equal)
2. Which explanation is clearer? (A / B / Equal)
3. Which explanation is more trustworthy? (A / B / Equal)
4. Which explanation is more actionable? (A / B / Equal)
5. Overall preference: (A / B / Equal)

### Reasoning
Why did you prefer one explanation over the other?

---
"""


def format_evaluation_results(results: List[ExplanationMetrics]) -> Dict[str, float]:
    """Format evaluation results as averages."""
    if not results:
        return {}

    all_metrics = {}
    for metric_name in vars(results[0]).keys():
        values = [getattr(r, metric_name) for r in results if getattr(r, metric_name) is not None]
        numeric_values = [v for v in values if isinstance(v, (int, float, np.floating))]
        if numeric_values:
            all_metrics[metric_name] = {
                "count": len(numeric_values),
                "mean": np.mean(numeric_values),
                "std": np.std(numeric_values),
                "min": np.min(numeric_values),
                "max": np.max(numeric_values),
            }

    return all_metrics
