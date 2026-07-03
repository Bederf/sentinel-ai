"""RAG (Retrieval-Augmented Generation) service combining vector search with LLM."""

import logging
from typing import Any

from app.security.trust_levels import get_allowed_trust_levels, wrap_rag_chunk
from app.services.model_gateway import model_gateway
from app.services.vector_db import get_vector_db_service

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
        self._supabase_client = supabase_client

    async def get_context(
        self,
        query: str,
        equipment_type: str | None = None,
        n_results: int = 5,
        use_hybrid: bool = True,
        user_role: str | None = None,
        endpoint_type: str = "chat",
    ) -> str:
        """Retrieve relevant context for a query with trust-level filtering.

        Args:
            query: The search query.
            equipment_type: Optional equipment type filter.
            n_results: Max number of results.
            use_hybrid: Use hybrid search (keyword + semantic).
            user_role: User role for trust-level filtering (None = no filter).
            endpoint_type: Endpoint type for trust-level rules.

        Returns:
            Formatted context string with wrapped chunks.
        """
        if use_hybrid:
            results = await self.vector_db.hybrid_search(
                query=query, n_results=n_results, equipment_type=equipment_type, doc_class="site"
            )
        else:
            results = self.vector_db.search(
                query=query,
                n_results=n_results,
                equipment_type=equipment_type,
                doc_class="site",
            )

        if not results:
            return "No relevant documentation found."

        # Apply trust level filtering if user_role is provided
        allowed_levels: list[str] | None = None
        if user_role:
            allowed_levels = get_allowed_trust_levels(user_role, endpoint_type)

        # Format context with untrusted content wrappers
        context_parts = []
        for r in results:
            trust_level = r.get("trust_level", "STANDARD")

            # Filter by trust level if restrictions apply
            if allowed_levels and trust_level not in allowed_levels:
                continue

            content = r.get("content", "")
            doc_id = r.get("document_id", r.get("id", "unknown"))
            chunk_id = r.get("chunk_id", r.get("id", "unknown"))
            page = r.get("page", r.get("chunk_index", 0))
            source_type = r.get("source", r.get("document_type", "unknown"))

            # Wrap every chunk as untrusted content with citation metadata
            wrapped = wrap_rag_chunk(
                chunk_text=content,
                doc_id=doc_id,
                page=page,
                chunk_id=chunk_id,
                source_type=source_type,
                trust_level=trust_level,
            )
            context_parts.append(wrapped)

        if not context_parts:
            return "No documentation available at the required trust level."

        return "\n\n---\n\n".join(context_parts)

    async def query(
        self,
        query: str,
        equipment_type: str | None = None,
        use_hybrid: bool = True,
        use_local_llm: bool = True,
        user_role: str | None = None,
    ) -> dict[str, Any]:
        """Query the RAG system and generate response."""
        # Get relevant context (with trust-level filtering if user_role provided)
        context = await self.get_context(query, equipment_type, use_hybrid=use_hybrid, user_role=user_role)

        # Build prompt
        prompt = self.CONTEXT_TEMPLATE.format(context=context, query=query)

        # Generate response
        if use_local_llm:
            try:
                response = await model_gateway.call(
                    task_class="heavy",
                    messages=[{"role": "user", "content": prompt}],
                    source="rag_query",
                )
                llm_used = "model_gateway"
            except Exception as e:
                logger.warning("model_gateway unavailable for RAG query: %s", e)
                response = f"[LLM not available] Context retrieved:\n\n{context}"
                llm_used = "none"
        else:
            # LLM disabled by caller
            response = f"[LLM disabled] Context retrieved:\n\n{context}"
            llm_used = "none"

        # Log query for analytics
        self._log_query(query, equipment_type, len(context.split()))

        return {
            "query": query,
            "response": response,
            "context_used": context,
            "equipment_type": equipment_type,
            "llm_used": llm_used,
        }

    async def explain_prediction(self, equipment_id: str, prediction: dict[str, Any]) -> dict[str, Any]:
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

        # Generate explanation via model_gateway
        llm_available = False
        try:
            # Use lower temperature for consistent output; gateway handles routing
            explanation = await model_gateway.call(
                task_class="heavy",
                messages=[{"role": "user", "content": prompt}],
                source="rag_explain_prediction",
            )
            llm_available = True
        except Exception as e:
            logger.warning("model_gateway unavailable for explain_prediction: %s", e)
            fail_prob = prediction.get("failure_probability_30d", 0) * 100
            pred_failure = prediction.get("predicted_failure", "Unknown")
            risk_lvl = prediction.get("risk_level", "Unknown")
            explanation = (
                f"[LLM not available]\n\nBased on the prediction data:\n"
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
            "llm_available": llm_available,
        }

    def _log_query(self, query: str, equipment_type: str | None, context_word_count: int):
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
