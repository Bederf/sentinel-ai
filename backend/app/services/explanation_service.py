"""Explanation Service for generating natural language explanations of ML predictions.

This service combines ML predictions with RAG context to generate
actionable, human-readable explanations for maintenance technicians.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from app.services.ollama_client import get_ollama_client
from app.services.vector_db import get_vector_db_service
from ml.explanations.templates import get_equipment_specific_template, format_prediction_for_template
from ml.explanations.parser import ExplanationParser

logger = logging.getLogger(__name__)


@dataclass
class ExplanationResult:
    """Complete explanation result with parsed structure."""

    equipment_id: str
    equipment_type: str
    raw_explanation: str
    parsed: Dict[str, Any]
    prediction_summary: Dict[str, Any]
    context_sources: str
    llm_available: bool
    model_used: Optional[str] = None


class ExplanationService:
    """Service for generating ML prediction explanations.

    Combines comprehensive ML predictions with RAG-retrieved documentation
    to generate natural language explanations using a local LLM (Ollama).
    """

    def __init__(self, supabase_client):
        """Initialize the explanation service.

        Args:
            supabase_client: Supabase client for vector DB access
        """
        self.ollama = get_ollama_client()
        self.vector_db = get_vector_db_service(supabase_client)
        self._supabase_client = supabase_client

    async def explain_prediction(
        self, equipment_id: str, predictions: Dict[str, Any], equipment_info: Optional[Dict[str, Any]] = None
    ) -> ExplanationResult:
        """Generate a comprehensive explanation for equipment predictions.

        Args:
            equipment_id: Equipment identifier
            predictions: Comprehensive prediction results from all ML models
            equipment_info: Optional equipment metadata (manufacturer, model, etc.)

        Returns:
            ExplanationResult with raw and parsed explanation
        """
        equipment_type = predictions.get("equipment_type", "unknown")

        # Get relevant documentation via RAG
        rag_context = await self._get_rag_context(equipment_type, predictions)

        # Get equipment-specific template
        template = get_equipment_specific_template(equipment_type)

        # Format prediction data for template
        template_data = format_prediction_for_template(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            predictions=predictions.get("predictions", {}),
            equipment_info=equipment_info,
        )
        template_data["rag_context"] = rag_context

        # Build the complete prompt
        prompt = template.format(**template_data)

        # Generate explanation with LLM
        ollama_available = await self.ollama.is_available()
        model_used = None

        if ollama_available:
            raw_explanation = await self.ollama.generate(
                prompt,
                temperature=0.3,  # Lower temperature for more consistent output
            )
            model_used = self.ollama.model
        else:
            raw_explanation = self._generate_fallback_explanation(template_data, predictions)

        # Parse the explanation into structured format
        parsed = ExplanationParser.parse_explanation(raw_explanation)

        return ExplanationResult(
            equipment_id=equipment_id,
            equipment_type=equipment_type,
            raw_explanation=raw_explanation,
            parsed=parsed.to_dict(),
            prediction_summary={
                "failure_probability_30d": template_data.get("failure_prob_30d", 0) / 100,
                "predicted_failure": template_data.get("predicted_failure", "Unknown"),
                "risk_level": template_data.get("risk_level", "Unknown"),
                "rul_days": template_data.get("rul_days", "Unknown"),
            },
            context_sources=rag_context[:500] + "..." if len(rag_context) > 500 else rag_context,
            llm_available=ollama_available,
            model_used=model_used,
        )

    async def _get_rag_context(self, equipment_type: str, predictions: Dict[str, Any]) -> str:
        """Retrieve relevant documentation context via RAG.

        Args:
            equipment_type: Type of equipment
            predictions: Prediction results to inform search

        Returns:
            Formatted context string
        """
        # Prefer vector DB helper if available (used in tests/mocks).
        if hasattr(self.vector_db, "get_rag_context"):
            result = self.vector_db.get_rag_context(
                equipment_type=equipment_type,
                predictions=predictions,
            )
            if hasattr(result, "__await__"):
                result = await result
            if isinstance(result, str):
                return result

        # Build search query from prediction info
        failure_type = predictions.get("predictions", {}).get("failure_type", {}).get("predicted_failure", "failure")

        query = f"{failure_type} {equipment_type} maintenance troubleshooting"

        # Hybrid search for relevant documentation
        doc_results = self.vector_db.hybrid_search(query=query, n_results=3, equipment_type=equipment_type)

        # Also search knowledge base
        knowledge_results = self.vector_db.search_knowledge(
            query=query,
            equipment_type=equipment_type,
            n_results=3,
            similarity_threshold=0.2,  # Lower threshold for broader matches
        )

        # Format document context
        context_parts = []

        if not isinstance(doc_results, list):
            doc_results = []

        if doc_results:
            for r in doc_results:
                source = r.get("document_title", "Documentation")
                content = r.get("content", "")[:500]
                score = r.get("hybrid_score", r.get("similarity", 0))
                context_parts.append(f"[{source}] (relevance: {score:.2f})\n{content}")

        if not isinstance(knowledge_results, list):
            knowledge_results = []

        if knowledge_results:
            context_parts.append("\n**Knowledge Base Entries:**")
            for k in knowledge_results:
                title = k.get("title", "Unknown")
                desc = k.get("description", "")
                solution = k.get("solution", "")
                entry = f"- **{title}**: {desc}"
                if solution:
                    entry += f"\n  Solution: {solution}"
                context_parts.append(entry)

        if not context_parts:
            return "No relevant documentation found in knowledge base."

        return "\n\n".join(context_parts)

    def _generate_fallback_explanation(self, template_data: Dict[str, Any], predictions: Dict[str, Any]) -> str:
        """Generate a basic explanation when LLM is not available.

        Args:
            template_data: Formatted template data
            predictions: Raw predictions

        Returns:
            Fallback explanation text
        """
        risk_level = template_data.get("risk_level", "Unknown")
        failure_prob = template_data.get("failure_prob_30d", 0)
        predicted_failure = template_data.get("predicted_failure", "Unknown")
        rul_days = template_data.get("rul_days", "Unknown")

        # Get risk factors
        overall_risk = predictions.get("overall_risk", {})
        risk_factors = overall_risk.get("risk_factors", [])

        explanation = f"""### SUMMARY
This {template_data.get("equipment_type", "equipment")} ({template_data.get("equipment_id", "")}) has a {risk_level} risk level with {failure_prob:.1f}% failure probability in the next 30 days. The predicted failure type is {predicted_failure}.

### KEY_FACTORS
{chr(10).join("- " + f for f in risk_factors) if risk_factors else "- No specific factors identified"}

### RECOMMENDED_ACTIONS
- [HIGH] Schedule inspection within 7 days if risk is high or critical
- [MEDIUM] Review recent maintenance history
- [MEDIUM] Check sensor readings for abnormalities
- [LOW] Plan preventive maintenance before RUL expires ({rul_days} days)

### PARTS_NEEDED
- None anticipated (inspection required first)

### LABOR_ESTIMATE
1-2 hours for initial inspection

### ADDITIONAL_NOTES
[Ollama LLM not available] This is an automated fallback explanation. For detailed analysis, ensure Ollama service is running.
"""
        return explanation

    async def get_quick_summary(self, equipment_id: str, predictions: Dict[str, Any]) -> Dict[str, Any]:
        """Get a quick summary without full LLM generation.

        Args:
            equipment_id: Equipment identifier
            predictions: Comprehensive predictions

        Returns:
            Quick summary dict
        """
        overall_risk = predictions.get("overall_risk", {})
        failure_type = predictions.get("predictions", {}).get("failure_type", {})
        survival = predictions.get("predictions", {}).get("survival", {})

        return {
            "equipment_id": equipment_id,
            "risk_level": overall_risk.get("risk_level", "Unknown"),
            "risk_score": overall_risk.get("risk_score", 0),
            "predicted_failure": failure_type.get("predicted_failure", "Unknown"),
            "failure_confidence": failure_type.get("confidence", 0),
            "failure_probability_30d": survival.get("failure_probability", {}).get("30d", 0),
            "rul_estimate": survival.get("rul_estimate", {}).get("median", "Unknown"),
            "risk_factors": overall_risk.get("risk_factors", []),
            "requires_attention": overall_risk.get("risk_level") in ["high", "critical"],
        }


def get_explanation_service(supabase_client) -> ExplanationService:
    """Factory function for ExplanationService.

    Args:
        supabase_client: Supabase client for database access

    Returns:
        ExplanationService instance
    """
    return ExplanationService(supabase_client)
