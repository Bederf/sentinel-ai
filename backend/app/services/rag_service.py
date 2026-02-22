"""RAG (Retrieval-Augmented Generation) service combining vector search with LLM."""

from typing import Optional, Dict, Any
import logging

from app.services.vector_db import get_vector_db_service
from app.services.ollama_client import get_ollama_client

logger = logging.getLogger(__name__)


class RAGService:
    """RAG service for equipment documentation queries."""

    CONTEXT_TEMPLATE = """Based on the following relevant documentation:

{context}

---

User question: {query}

Please provide a helpful, accurate answer based on the documentation above. \
If the documentation doesn't contain relevant information, say so clearly."""

    EQUIPMENT_EXPLANATION_TEMPLATE = """You are a BMS (Building Management System) expert \
explaining equipment predictions to maintenance technicians.

**Equipment:** {equipment_type} - {equipment_id}
**Manufacturer:** {manufacturer}
**Model:** {model}

**ML Prediction Summary:**
- Failure Probability (30 days): {failure_prob_30d:.1f}%
- Predicted Failure Type: {predicted_failure}
- Anomaly Score: {anomaly_score:.4f}
- Risk Level: {risk_level}

**Top Contributing Factors:**
{contributing_factors}

**Relevant Technical Documentation:**
{rag_context}

---

Generate a clear, actionable explanation that includes:
1. What this prediction means in plain English
2. Why this prediction was made (key factors in simple terms)
3. Recommended immediate actions (prioritized)
4. Parts likely needed (if applicable)
5. Estimated labor time

Keep the language practical and technical but accessible to field technicians."""

    def __init__(self, supabase_client):
        self.vector_db = get_vector_db_service(supabase_client)
        self.ollama = get_ollama_client()
        self._supabase_client = supabase_client

    async def get_context(
        self, query: str, equipment_type: Optional[str] = None, n_results: int = 5, use_hybrid: bool = True
    ) -> str:
        """Retrieve relevant context for a query."""
        if use_hybrid:
            results = self.vector_db.hybrid_search(query=query, n_results=n_results, equipment_type=equipment_type)
        else:
            results = self.vector_db.search(query=query, n_results=n_results, equipment_type=equipment_type)

        if not results:
            return "No relevant documentation found."

        # Format context
        context_parts = []
        for r in results:
            source = f"[{r.get('document_title', 'Unknown')}]"
            content = r.get("content", "")
            score = r.get("similarity", r.get("hybrid_score", 0))
            context_parts.append(f"{source} (relevance: {score:.2f})\n{content}")

        return "\n\n---\n\n".join(context_parts)

    async def query(
        self, query: str, equipment_type: Optional[str] = None, use_hybrid: bool = True, use_local_llm: bool = True
    ) -> Dict[str, Any]:
        """Query the RAG system and generate response."""
        # Get relevant context
        context = await self.get_context(query, equipment_type, use_hybrid=use_hybrid)

        # Build prompt
        prompt = self.CONTEXT_TEMPLATE.format(context=context, query=query)

        # Generate response
        if use_local_llm:
            ollama_available = await self.ollama.is_available()
            if ollama_available:
                response = await self.ollama.generate(prompt)
            else:
                response = f"[Ollama not available] Context retrieved:\n\n{context}"
        else:
            # Could integrate with Claude here if needed
            response = f"[LLM disabled] Context retrieved:\n\n{context}"

        # Log query for analytics
        self._log_query(query, equipment_type, len(context.split()))

        return {
            "query": query,
            "response": response,
            "context_used": context,
            "equipment_type": equipment_type,
            "llm_used": "ollama" if use_local_llm else "none",
        }

    async def explain_prediction(self, equipment_id: str, prediction: Dict[str, Any]) -> Dict[str, Any]:
        """Generate natural language explanation for a prediction."""
        equipment_type = prediction.get("equipment_type", "unknown")

        # Get relevant documentation
        query = f"{prediction.get('predicted_failure', 'failure')} {equipment_type} maintenance troubleshooting"
        rag_context = await self.get_context(query, equipment_type, n_results=3)

        # Also search knowledge base
        knowledge = self.vector_db.search_knowledge(query=query, equipment_type=equipment_type, n_results=2)

        # Add knowledge to context
        if knowledge:
            knowledge_text = "\n\n**Related Knowledge Base Entries:**\n"
            for k in knowledge:
                knowledge_text += f"- {k.get('title')}: {k.get('description')}\n"
                if k.get("solution"):
                    knowledge_text += f"  Solution: {k.get('solution')}\n"
            rag_context += knowledge_text

        # Format contributing factors
        factors = prediction.get("contributing_factors", [])
        if factors:
            factors_text = "\n".join(
                [
                    f"- {f.get('factor', f.get('name', 'Unknown'))}: "
                    f"{f.get('importance', f.get('weight', 0)):.1%} importance"
                    for f in factors[:5]
                ]
            )
        else:
            factors_text = "No specific factors identified"

        # Build prompt
        prompt = self.EQUIPMENT_EXPLANATION_TEMPLATE.format(
            equipment_type=equipment_type,
            equipment_id=equipment_id,
            manufacturer=prediction.get("manufacturer", "Unknown"),
            model=prediction.get("model", "Unknown"),
            failure_prob_30d=prediction.get("failure_probability_30d", 0) * 100,
            predicted_failure=prediction.get("predicted_failure", "Unknown"),
            anomaly_score=prediction.get("anomaly_score", 0),
            risk_level=prediction.get("risk_level", "Unknown"),
            contributing_factors=factors_text,
            rag_context=rag_context,
        )

        # Check if Ollama is available
        ollama_available = await self.ollama.is_available()

        if ollama_available:
            # Generate explanation with lower temperature for more consistent output
            explanation = await self.ollama.generate(prompt, temperature=0.3)
        else:
            fail_prob = prediction.get("failure_probability_30d", 0) * 100
            pred_failure = prediction.get("predicted_failure", "Unknown")
            risk_lvl = prediction.get("risk_level", "Unknown")
            explanation = (
                f"[Ollama not available]\n\nBased on the prediction data:\n"
                f"- Failure probability: {fail_prob:.1f}%\n"
                f"- Predicted failure: {pred_failure}\n"
                f"- Risk level: {risk_lvl}\n\n"
                f"Please review the technical documentation for detailed guidance."
            )

        return {
            "equipment_id": equipment_id,
            "explanation": explanation,
            "prediction_summary": {
                "failure_probability": prediction.get("failure_probability_30d"),
                "predicted_failure": prediction.get("predicted_failure"),
                "risk_level": prediction.get("risk_level"),
            },
            "context_sources": rag_context[:500] + "..." if len(rag_context) > 500 else rag_context,
            "llm_available": ollama_available,
        }

    def _log_query(self, query: str, equipment_type: Optional[str], context_word_count: int):
        """Log RAG query for analytics (non-blocking)."""
        try:
            self._supabase_client.table("rag_queries").insert(
                {
                    "query_text": query,
                    "equipment_type": equipment_type,
                    "chunks_retrieved": context_word_count // 100,  # Approximate
                }
            ).execute()
        except Exception as e:
            logger.warning(f"Failed to log RAG query: {e}")


def get_rag_service(supabase_client) -> RAGService:
    """Factory function for RAGService."""
    return RAGService(supabase_client)
