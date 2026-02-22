"""Query handler for routing classified intents to appropriate services.

Routes natural language queries through the intent classifier, gathers
relevant context from repositories and services, formats prompts, and
generates responses via Ollama (local LLM).
"""

import logging
from typing import Any, Dict, Optional

from app.services.ollama_client import OllamaClient
from app.services.rag_service import get_rag_service
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.alert_repository import AlertRepository
from ml.conversation.intent import IntentClassifier, Intent, ClassifiedQuery
from ml.conversation.prompts import (
    SYSTEM_PROMPT,
    INTENT_PROMPTS,
)

logger = logging.getLogger(__name__)


class QueryHandler:
    """Routes classified queries to services and generates responses."""

    def __init__(self):
        self.classifier = IntentClassifier()
        self.ollama = OllamaClient()
        self.equipment_repo = EquipmentRepository()
        self.alert_repo = AlertRepository()

    async def handle_query(self, query: str) -> Dict[str, Any]:
        """Process a natural language query end-to-end.

        1. Classify intent and extract entities
        2. Gather context from relevant services
        3. Format prompt with context
        4. Generate response via Ollama

        Args:
            query: Natural language user query

        Returns:
            Dict with response, intent, confidence, and metadata
        """
        # Step 1: Classify
        classified = self.classifier.classify(query)
        logger.info(
            "Classified query: intent=%s confidence=%.2f equipment=%s",
            classified.intent.value,
            classified.confidence,
            classified.equipment_ids,
        )

        # Step 2: Gather context and build prompt
        try:
            context = await self._gather_context(classified)
            prompt = self._build_prompt(classified, context)
        except Exception as e:
            logger.error("Failed to gather context: %s", e)
            context = {}
            prompt = self._build_fallback_prompt(classified)

        # Step 3: Generate response
        ollama_available = await self.ollama.is_available()
        if ollama_available:
            response_text = await self.ollama.generate(prompt, temperature=0.3)
            model_used = self.ollama.default_model
        else:
            response_text = self._generate_offline_response(classified, context)
            model_used = None

        return {
            "response": response_text,
            "intent": classified.intent.value,
            "confidence": classified.confidence,
            "equipment_ids": classified.equipment_ids,
            "equipment_type": classified.equipment_type,
            "time_range": classified.time_range,
            "model_used": model_used,
            "llm_available": ollama_available,
        }

    async def _gather_context(self, classified: ClassifiedQuery) -> Dict[str, Any]:
        """Gather relevant context based on intent and entities."""
        context: Dict[str, Any] = {}

        # Get equipment data if IDs are present
        equipment_id = classified.equipment_ids[0] if classified.equipment_ids else None
        if equipment_id:
            equipment = self.equipment_repo.get_by_id(equipment_id)
            if equipment:
                context["equipment"] = equipment
                # Get alerts for this equipment
                alerts = self.alert_repo.get_active_by_equipment(equipment_id)
                context["alerts"] = alerts or []

        # Get RAG context for domain knowledge
        rag_service = get_rag_service()
        if rag_service:
            rag_result = await rag_service.get_context(
                classified.original_query,
                equipment_type=classified.equipment_type,
            )
            context["rag_context"] = rag_result
        else:
            context["rag_context"] = ""

        # Intent-specific context gathering
        if classified.intent == Intent.WHY_PREDICTION:
            context.update(await self._get_prediction_context(equipment_id, classified))
        elif classified.intent == Intent.MAINTENANCE_DUE:
            context.update(await self._get_maintenance_context(equipment_id, classified))
        elif classified.intent == Intent.COMPARE_EQUIPMENT:
            context.update(self._get_comparison_context(classified))
        elif classified.intent == Intent.EXPLAIN_ANOMALY:
            context.update(self._get_anomaly_context(equipment_id, classified))

        return context

    async def _get_prediction_context(
        self,
        equipment_id: Optional[str],
        classified: ClassifiedQuery,
    ) -> Dict[str, Any]:
        """Gather prediction-specific context."""
        ctx: Dict[str, Any] = {}
        if not equipment_id:
            return ctx

        equipment = ctx.get("equipment") or self.equipment_repo.get_by_id(equipment_id)
        if equipment:
            ctx["prediction_data"] = (
                f"Health Score: {equipment.get('health_score', 'N/A')}%\n"
                f"Status: {equipment.get('status', 'N/A')}\n"
                f"Risk Level: {equipment.get('risk_level', 'N/A')}"
            )
        return ctx

    async def _get_maintenance_context(
        self,
        equipment_id: Optional[str],
        classified: ClassifiedQuery,
    ) -> Dict[str, Any]:
        """Gather maintenance-specific context."""
        ctx: Dict[str, Any] = {}
        if not equipment_id:
            return ctx

        equipment = self.equipment_repo.get_by_id(equipment_id)
        if equipment:
            ctx["maintenance_history"] = equipment.get("last_maintenance", "No maintenance history available")
            ctx["rul_days"] = equipment.get("rul_days", "Unknown")
        return ctx

    def _get_comparison_context(self, classified: ClassifiedQuery) -> Dict[str, Any]:
        """Gather context for equipment comparison."""
        ctx: Dict[str, Any] = {}
        if len(classified.equipment_ids) >= 2:
            eq_a = self.equipment_repo.get_by_id(classified.equipment_ids[0])
            eq_b = self.equipment_repo.get_by_id(classified.equipment_ids[1])
            if eq_a:
                ctx["equipment_a"] = eq_a
            if eq_b:
                ctx["equipment_b"] = eq_b
        return ctx

    def _get_anomaly_context(
        self,
        equipment_id: Optional[str],
        classified: ClassifiedQuery,
    ) -> Dict[str, Any]:
        """Gather anomaly-specific context."""
        ctx: Dict[str, Any] = {}
        if equipment_id:
            alerts = self.alert_repo.get_active_by_equipment(equipment_id)
            ctx["anomaly_alerts"] = alerts or []
        return ctx

    def _build_prompt(self, classified: ClassifiedQuery, context: Dict[str, Any]) -> str:
        """Build the appropriate prompt template with context."""
        template = INTENT_PROMPTS.get(classified.intent.value, INTENT_PROMPTS["general_query"])

        equipment = context.get("equipment", {})
        equipment_id = classified.equipment_ids[0] if classified.equipment_ids else "N/A"

        # Common template variables
        variables = {
            "system": SYSTEM_PROMPT,
            "equipment_id": equipment_id,
            "equipment_type": (classified.equipment_type or equipment.get("type", "unknown")),
            "health_score": equipment.get("health_score", "N/A"),
            "risk_level": equipment.get("risk_level", "unknown"),
            "status": equipment.get("status", "unknown"),
            "query": classified.original_query,
            "rag_context": context.get("rag_context", "No documentation available"),
            "context": context.get("rag_context", "No context available"),
        }

        # Intent-specific variables
        if classified.intent == Intent.WHY_PREDICTION:
            variables["prediction_data"] = context.get("prediction_data", "No prediction data available")
        elif classified.intent == Intent.MAINTENANCE_DUE:
            variables["maintenance_history"] = context.get("maintenance_history", "No maintenance history")
            variables["rul_days"] = context.get("rul_days", "Unknown")
            variables["last_service"] = equipment.get("last_maintenance", "Unknown")
            variables["sensor_readings"] = self._format_sensor_readings(equipment)
        elif classified.intent == Intent.EXPLAIN_ANOMALY:
            variables["anomaly_data"] = self._format_alerts(context.get("anomaly_alerts", []))
            variables["sensor_readings"] = self._format_sensor_readings(equipment)
        elif classified.intent == Intent.COMPARE_EQUIPMENT:
            eq_a = context.get("equipment_a", {})
            eq_b = context.get("equipment_b", {})
            variables["equipment_a_id"] = classified.equipment_ids[0] if len(classified.equipment_ids) > 0 else "N/A"
            variables["equipment_b_id"] = classified.equipment_ids[1] if len(classified.equipment_ids) > 1 else "N/A"
            variables["equipment_a_type"] = eq_a.get("type", "unknown")
            variables["equipment_b_type"] = eq_b.get("type", "unknown")
            variables["equipment_a_health"] = eq_a.get("health_score", "N/A")
            variables["equipment_b_health"] = eq_b.get("health_score", "N/A")
            variables["equipment_a_risk"] = eq_a.get("risk_level", "unknown")
            variables["equipment_b_risk"] = eq_b.get("risk_level", "unknown")
            variables["equipment_a_details"] = self._format_equipment_summary(eq_a)
            variables["equipment_b_details"] = self._format_equipment_summary(eq_b)
        elif classified.intent == Intent.SHOW_TRENDS:
            variables["time_range"] = classified.time_range or "7d"
            variables["trend_data"] = "Trend data not yet available via local query"
        elif classified.intent == Intent.EQUIPMENT_STATUS:
            variables["sensor_readings"] = self._format_sensor_readings(equipment)
            variables["recent_alerts"] = self._format_alerts(context.get("alerts", []))

        try:
            return template.format(**variables)
        except KeyError as e:
            logger.warning("Missing template variable %s, using fallback", e)
            return self._build_fallback_prompt(classified)

    def _build_fallback_prompt(self, classified: ClassifiedQuery) -> str:
        """Build a simple fallback prompt when context gathering fails."""
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"User question: {classified.original_query}\n\n"
            f"Please answer this question about building management "
            f"equipment to the best of your ability."
        )

    def _generate_offline_response(self, classified: ClassifiedQuery, context: Dict[str, Any]) -> str:
        """Generate a response when Ollama is not available."""
        equipment = context.get("equipment", {})
        equipment_id = classified.equipment_ids[0] if classified.equipment_ids else None

        parts = []
        if classified.intent == Intent.EQUIPMENT_STATUS and equipment:
            parts.append(
                f"**{equipment_id}** ({equipment.get('type', 'unknown')}): "
                f"Health {equipment.get('health_score', 'N/A')}%, "
                f"Status: {equipment.get('status', 'N/A')}"
            )
            alerts = context.get("alerts", [])
            if alerts:
                parts.append(f"\n{len(alerts)} active alert(s) for this equipment.")
        elif classified.intent == Intent.MAINTENANCE_DUE and equipment:
            rul = context.get("rul_days", "Unknown")
            parts.append(
                f"**{equipment_id}**: Estimated remaining useful life: "
                f"{rul} days. Health: {equipment.get('health_score', 'N/A')}%"
            )
        else:
            parts.append(
                f"[Local LLM offline] Query classified as "
                f"**{classified.intent.value}** "
                f"(confidence: {classified.confidence:.0%}). "
                f"Start Ollama for full natural language responses."
            )

        return "\n".join(parts)

    def _format_sensor_readings(self, equipment: Dict[str, Any]) -> str:
        """Format equipment sensor readings for prompt context."""
        if not equipment:
            return "No sensor readings available"
        readings = []
        for key in ("temperature", "pressure", "vibration", "power", "flow"):
            val = equipment.get(key)
            if val is not None:
                readings.append(f"- {key}: {val}")
        return "\n".join(readings) if readings else "No sensor readings available"

    def _format_alerts(self, alerts: list) -> str:
        """Format alerts for prompt context."""
        if not alerts:
            return "No active alerts"
        lines = []
        for alert in alerts[:5]:  # Limit to 5 most recent
            lines.append(
                f"- [{alert.get('severity', 'INFO')}] "
                f"{alert.get('message', alert.get('description', 'No description'))}"
            )
        return "\n".join(lines)

    def _format_equipment_summary(self, equipment: Dict[str, Any]) -> str:
        """Format equipment details for comparison prompt."""
        if not equipment:
            return "No data available"
        return (
            f"- Status: {equipment.get('status', 'N/A')}\n"
            f"- Last Maintenance: {equipment.get('last_maintenance', 'N/A')}"
        )


# Singleton
_query_handler: Optional[QueryHandler] = None


def get_query_handler() -> QueryHandler:
    """Get or create the singleton QueryHandler instance."""
    global _query_handler
    if _query_handler is None:
        _query_handler = QueryHandler()
    return _query_handler
