"""Hybrid Knowledge Layer Query Service.

Merges three data sources into one context payload for AI agents:
1. Brick graph (equipment relationships, location, points)
2. Document RAG (maintenance reports, contracts, SOPs)
3. Telemetry + ML (live sensor values, LSTM forecasts, anomaly scores)

This is the single entrypoint agents use to answer operational questions like:
"The generator alarmed — who is the vendor and what did the last inspection find?"

See: docs/02-architecture/hybrid-knowledge-layer.md
"""

from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context payload
# ---------------------------------------------------------------------------
@dataclass
class HybridContext:
    """Merged context from Brick + RAG + Telemetry for AI reasoning."""

    # Identity
    equipment_id: str | None = None
    equipment_type: str | None = None
    equipment_label: str | None = None
    site_id: str | None = None

    # Brick graph context
    location_path: list[dict[str, str]] = field(default_factory=list)
    points: list[dict[str, Any]] = field(default_factory=list)
    manufacturer: str | None = None
    model: str | None = None
    protocol: str | None = None
    vendor: dict[str, Any] | None = None
    contract: dict[str, Any] | None = None

    # Document RAG context
    documents: list[dict[str, Any]] = field(default_factory=list)

    # Telemetry + ML context
    telemetry: dict[str, Any] = field(default_factory=dict)
    ml_context: dict[str, Any] = field(default_factory=dict)

    # Decision Memory context (Phase 145)
    decision_memory: str | None = None

    # Active operational events (Phase 145)
    active_events: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    sources_used: list[str] = field(default_factory=list)
    retrieval_telemetry: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "equipment_id": self.equipment_id,
            "equipment_type": self.equipment_type,
            "equipment_label": self.equipment_label,
            "site_id": self.site_id,
            "location_path": self.location_path,
            "points": self.points,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "protocol": self.protocol,
            "vendor": self.vendor,
            "contract": self.contract,
            "documents": self.documents,
            "telemetry": self.telemetry,
            "ml_context": self.ml_context,
            "decision_memory": self.decision_memory,
            "active_events": self.active_events,
            "sources_used": self.sources_used,
            "retrievalTelemetry": self.retrieval_telemetry,
        }

    def format_for_prompt(self) -> str:
        """Format context as a readable text block for injection into AI prompts."""
        sections = []

        # Equipment identity
        if self.equipment_id:
            header = f"Equipment: {self.equipment_id}"
            if self.equipment_type:
                header += f" ({self.equipment_type})"
            sections.append(header)

        if self.manufacturer or self.model:
            specs = []
            if self.manufacturer:
                specs.append(f"Manufacturer: {self.manufacturer}")
            if self.model:
                specs.append(f"Model: {self.model}")
            sections.append(", ".join(specs))

        # Location
        if self.location_path:
            loc_str = " > ".join(loc.get("label", "?") for loc in self.location_path)
            sections.append(f"Location: {loc_str}")

        # Vendor / Contract
        if self.vendor:
            vendor_name = self.vendor.get("name", "Unknown")
            sections.append(f"Vendor: {vendor_name}")
        if self.contract:
            sla = self.contract.get("sla_response_hours")
            if sla:
                sections.append(f"SLA: {sla}h response time")

        # Points summary
        if self.points:
            sections.append(f"\nMonitoring Points ({len(self.points)}):")
            for pt in self.points[:10]:  # Cap at 10 for prompt size
                label = pt.get("label", "?")
                brick_class = pt.get("brick_class", "")
                unit = pt.get("unit", "")
                writable = "writable" if pt.get("writable") else "read-only"
                sections.append(f"  - {label}: {brick_class} [{unit}] ({writable})")

        # Telemetry
        if self.telemetry:
            sections.append("\nRecent Telemetry:")
            operating_data = self.telemetry.get("operating_data", {})
            for key, val in list(operating_data.items())[:8]:
                if isinstance(val, dict):
                    v = val.get("value", "?")
                    ts = val.get("timestamp", "")
                    sections.append(f"  - {key}: {v} (at {ts})")
                else:
                    sections.append(f"  - {key}: {val}")

        # ML context
        if self.ml_context:
            anomalies = self.ml_context.get("anomaly_alerts", [])
            faults = self.ml_context.get("fault_classifications", [])
            trends = self.ml_context.get("health_trends", [])

            if anomalies:
                sections.append("\nAnomaly Alerts:")
                for a in anomalies:
                    sections.append(
                        f"  - {a.get('equipment_id')}: score {a.get('anomaly_score')} ({a.get('severity')})"
                    )

            if faults:
                sections.append("\nFault Classifications:")
                for f in faults:
                    sections.append(f"  - {f.get('equipment_id')}: {f.get('fault_type')} (prob {f.get('probability')})")

            if trends:
                sections.append("\nDegrading Equipment:")
                for t in trends:
                    eq = t.get("equipment_id")
                    hs = t.get("health_score")
                    slope = t.get("trend_7d_slope")
                    sections.append(f"  - {eq}: health {hs}, 7d slope {slope}")

        # Active operational events
        if self.active_events:
            sections.append(f"\nActive Operational Events ({len(self.active_events)}):")
            for evt in self.active_events[:5]:
                evt_type = evt.get("event_type", "unknown")
                severity = evt.get("severity", "unknown")
                desc = evt.get("description", "")
                duration = evt.get("duration_minutes")
                dur_str = f", {duration:.0f} min" if duration else ""
                sections.append(f"  - [{severity}] {evt_type}: {desc}{dur_str}")

        # Decision memory (historical patterns and prior cases)
        if self.decision_memory:
            sections.append(f"\n{self.decision_memory}")

        # Documents
        if self.documents:
            sections.append(f"\nRelated Documents ({len(self.documents)}):")
            for doc in self.documents[:5]:  # Cap at 5
                doc_type = doc.get("type", "document")
                title = doc.get("title", doc.get("source", "untitled"))
                excerpt = doc.get("excerpt", "")[:200]
                sections.append(f"  [{doc_type}] {title}")
                if excerpt:
                    sections.append(f"    {excerpt}")

        return "\n".join(sections)


# ---------------------------------------------------------------------------
# Hybrid Query Service
# ---------------------------------------------------------------------------
class HybridQueryService:
    """Assembles context from Brick + RAG + Telemetry for AI agents."""

    def __init__(self, site_id: str = "site-002") -> None:
        self.site_id = site_id

    async def query(
        self,
        *,
        equipment_id: str | None = None,
        bacnet_ref: str | None = None,
        question: str | None = None,
        include_documents: bool = True,
        include_telemetry: bool = True,
        include_ml: bool = True,
        include_points: bool = True,
        include_decision_memory: bool = True,
        include_active_events: bool = True,
    ) -> HybridContext:
        """Assemble hybrid context for an equipment item.

        Resolves equipment from bacnet_ref if equipment_id not provided.
        Then gathers Brick graph context, document RAG results, and telemetry.

        Args:
            equipment_id: Equipment code (e.g., "S002-CHILLER-B1-001")
            bacnet_ref: BACnet point reference to resolve to equipment
            question: Natural language question for RAG search
            include_documents: Whether to search RAG for related docs
            include_telemetry: Whether to include operating data
            include_ml: Whether to include ML model outputs
            include_points: Whether to include Brick point details
        """
        ctx = HybridContext(site_id=self.site_id)

        # Step 1: Resolve equipment identity
        equipment_id = await self._resolve_equipment(ctx, equipment_id=equipment_id, bacnet_ref=bacnet_ref)
        if not equipment_id:
            return ctx

        ctx.equipment_id = equipment_id

        # Step 2: Brick graph context
        await self._gather_brick_context(ctx, equipment_id, include_points)

        # Step 3: Document RAG (if enabled)
        if include_documents:
            await self._gather_document_context(ctx, equipment_id, question)

        # Step 4: Telemetry + ML (if enabled)
        if include_telemetry:
            await self._gather_telemetry(ctx, equipment_id)

        if include_ml:
            await self._gather_ml_context(ctx, equipment_id)

        # Step 5: Active operational events (Phase 145)
        if include_active_events:
            await self._gather_active_events(ctx, equipment_id)

        # Step 6: Decision memory (Phase 145)
        # Only include verified, high-confidence outcomes — never overrides
        # live telemetry or safety policy, only informs reasoning.
        if include_decision_memory:
            await self._gather_decision_memory(ctx, equipment_id)

        return ctx

    # -------------------------------------------------------------------
    # Step 1: Equipment resolution
    # -------------------------------------------------------------------
    async def _resolve_equipment(
        self,
        ctx: HybridContext,
        *,
        equipment_id: str | None,
        bacnet_ref: str | None,
    ) -> str | None:
        """Resolve to equipment_id, using Brick if we only have a bacnet_ref."""
        if equipment_id:
            return equipment_id

        if not bacnet_ref:
            return None

        try:
            from app.services.brick_service import get_brick_service

            brick_svc = get_brick_service(self.site_id)
            if brick_svc:
                resolved_id = brick_svc.resolve_equipment_id(bacnet_ref=bacnet_ref)
                if resolved_id:
                    ctx.sources_used.append("brick_resolution")
                    return resolved_id
        except Exception as e:
            logger.debug("Brick resolution failed for bacnet_ref=%s: %s", bacnet_ref, e)

        return None

    # -------------------------------------------------------------------
    # Step 2: Brick graph context
    # -------------------------------------------------------------------
    async def _gather_brick_context(
        self,
        ctx: HybridContext,
        equipment_id: str,
        include_points: bool,
    ) -> None:
        """Pull equipment context from the Brick graph."""
        try:
            from app.services.brick_service import get_brick_service

            brick_svc = get_brick_service(self.site_id)
            if not brick_svc:
                return

            brick_ctx = brick_svc.get_context(equipment_id, include_points=include_points)
            if not brick_ctx:
                return

            ctx.equipment_type = brick_ctx.equipment_type
            ctx.equipment_label = brick_ctx.label
            ctx.manufacturer = brick_ctx.manufacturer
            ctx.model = brick_ctx.model
            ctx.protocol = brick_ctx.protocol
            ctx.location_path = [{"iri": iri, "label": label} for iri, label in brick_ctx.location_path]
            ctx.points = [p.to_dict() for p in brick_ctx.points]
            ctx.vendor = brick_ctx.vendor
            ctx.contract = brick_ctx.contract
            ctx.sources_used.append("brick_graph")

        except ImportError:
            logger.debug("BrickService not available (rdflib not installed)")
        except Exception as e:
            logger.warning("Brick context gather failed for %s: %s", equipment_id, e)

    # -------------------------------------------------------------------
    # Step 3: Document RAG
    # -------------------------------------------------------------------
    async def _gather_document_context(
        self,
        ctx: HybridContext,
        equipment_id: str,
        question: str | None,
    ) -> None:
        """Search RAG for documents related to this equipment."""
        try:
            # TODO: Verify interface of concept_document_search service
            from app.services.concept_document_search import get_concept_document_search_service

            search_svc = get_concept_document_search_service()
            if not search_svc:
                return

            # Build search query
            search_query = question or equipment_id
            if ctx.equipment_type:
                search_query = f"{ctx.equipment_type} {search_query}"

            trace_id = str(uuid4())
            retrieval_path = "canonical_doc_rag"
            top_k_requested = 5
            used_fallback: str | None = None
            fallback_reason: str | None = None
            started_at = time.perf_counter()
            search_response = search_svc.search(
                query=search_query,
                site_id=self.site_id,
                top_k=top_k_requested,
            )
            if inspect.isawaitable(search_response):
                search_response = await search_response

            # Canonical service may return either a payload dict with "results"
            # or a list of hit dicts depending on integration point.
            if isinstance(search_response, dict):
                results = search_response.get("results") or []
            elif isinstance(search_response, list):
                results = search_response
            else:
                results = []
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            hit_count = len(results or [])

            telemetry: dict[str, Any] = {
                "trace_id": trace_id,
                "retrieval_path": retrieval_path,
                "query_time_ms": duration_ms,
                "top_k_requested": top_k_requested,
                "hit_count": hit_count,
                "used_fallback": used_fallback,
            }
            if fallback_reason:
                telemetry["fallback_reason"] = fallback_reason
            ctx.retrieval_telemetry = telemetry
            self._record_retrieval_telemetry(ctx.retrieval_telemetry)

            logger.info(
                "Canonical retrieval telemetry trace_id=%s path=%s duration_ms=%s hit_count=%s fallback=%s",
                trace_id,
                retrieval_path,
                duration_ms,
                hit_count,
                used_fallback or "none",
            )

            if results:
                ctx.documents = [
                    {
                        "title": r.get("title", r.get("source", "")),
                        "type": r.get("document_type", "document"),
                        "excerpt": r.get("content", r.get("text", ""))[:300],
                        "score": r.get("similarity", r.get("score", 0)),
                        "source": r.get("source", ""),
                    }
                    for r in results
                ]
                ctx.sources_used.append("document_rag")

        except ImportError:
            logger.debug("Concept document search service not available")
        except Exception as e:
            logger.debug("Document search failed for %s: %s", equipment_id, e)

    @staticmethod
    def _record_retrieval_telemetry(telemetry: dict[str, Any] | None) -> None:
        """Best-effort metric emission for canonical retrieval telemetry."""
        if not telemetry:
            return

        try:
            from app.services.governance_metrics_collector import governance_metrics

            governance_metrics.record_retrieval_telemetry(
                retrieval_path=telemetry.get("retrieval_path"),
                duration_ms=telemetry.get("query_time_ms"),
                hit_count=telemetry.get("hit_count"),
                used_fallback=telemetry.get("used_fallback"),
            )
        except Exception:
            logger.debug("Failed to emit retrieval telemetry metrics", exc_info=True)

    # -------------------------------------------------------------------
    # Step 4a: Telemetry (operating data from equipment)
    # -------------------------------------------------------------------
    async def _gather_telemetry(
        self,
        ctx: HybridContext,
        equipment_id: str,
    ) -> None:
        """Pull current operating data for the equipment."""
        try:
            from app.database.repositories.equipment_repository import get_equipment_repository

            repo = get_equipment_repository()
            equipment = await repo.get_by_code(equipment_id)
            if equipment and equipment.get("operating_data"):
                ctx.telemetry = {
                    "operating_data": equipment["operating_data"],
                    "health_score": equipment.get("health_score"),
                    "status": equipment.get("status"),
                }
                ctx.sources_used.append("telemetry")

        except Exception as e:
            logger.debug("Telemetry gather failed for %s: %s", equipment_id, e)

    # -------------------------------------------------------------------
    # Step 4b: ML context (filtered to this equipment)
    # -------------------------------------------------------------------
    async def _gather_ml_context(
        self,
        ctx: HybridContext,
        equipment_id: str,
    ) -> None:
        """Pull ML model outputs filtered to this equipment.

        Rather than calling the full _gather_ml_context() from ai_optimizer
        (which processes ALL equipment), we pull per-equipment ML data.
        """
        ml: dict[str, Any] = {}

        # Anomaly score
        try:
            from app.services.ml_inference import get_anomaly_service

            anomaly_svc = get_anomaly_service()
            eq_type = (ctx.equipment_type or "unknown").lower()
            result = anomaly_svc.check_equipment(equipment_id, eq_type)
            if result and (result.get("anomaly_score", 0) > 0.3 or result.get("is_anomaly")):
                ml["anomaly_alerts"] = [
                    {
                        "equipment_id": equipment_id,
                        "anomaly_score": round(result.get("anomaly_score", 0), 3),
                        "severity": result.get("severity", "unknown"),
                        "is_anomaly": result.get("is_anomaly", False),
                    }
                ]
        except Exception:
            pass

        # Fault classification
        try:
            from app.services.classification_service import get_classification_service

            cls_svc = get_classification_service()
            risk = cls_svc.get_failure_risk(equipment_id)
            if risk and risk.get("confidence", 0) > 0.4:
                ml["fault_classifications"] = [
                    {
                        "equipment_id": equipment_id,
                        "fault_type": risk.get("predicted_fault_type", ""),
                        "probability": round(risk.get("confidence", 0), 3),
                    }
                ]
        except Exception:
            pass

        # Health trend
        try:
            from app.services.health_feature_provider import HealthFeatureProvider

            provider = HealthFeatureProvider()
            payload = await provider.get_health_features(equipment_id)
            if payload and payload.health_trend_7d_slope is not None:
                ml["health_trends"] = [
                    {
                        "equipment_id": equipment_id,
                        "health_score": payload.health_score_current,
                        "trend_7d_slope": round(payload.health_trend_7d_slope, 3),
                    }
                ]
        except Exception:
            pass

        if ml:
            ctx.ml_context = ml
            ctx.sources_used.append("ml_models")

    # -------------------------------------------------------------------
    # Step 5: Active operational events (Phase 145)
    # -------------------------------------------------------------------
    async def _gather_active_events(
        self,
        ctx: HybridContext,
        equipment_id: str,
    ) -> None:
        """Pull active operational events for this equipment from EventIntelligence."""
        try:
            from app.services.event_intelligence_service import get_event_intelligence_service

            svc = get_event_intelligence_service()
            events = await svc.get_active_events(
                site_id=self.site_id,
                equipment_id=equipment_id,
            )
            if events:
                ctx.active_events = [
                    {
                        "event_id": e.event_id,
                        "event_type": e.event_type.value,
                        "severity": e.severity.value,
                        "description": e.description,
                        "duration_minutes": e.duration_minutes,
                        "trend": e.trend,
                    }
                    for e in events[:5]  # Cap to avoid prompt bloat
                ]
                ctx.sources_used.append("event_intelligence")
        except Exception as e:
            logger.debug("Active events gather failed for %s: %s", equipment_id, e)

    # -------------------------------------------------------------------
    # Step 6: Decision memory (Phase 145)
    # -------------------------------------------------------------------
    async def _gather_decision_memory(
        self,
        ctx: HybridContext,
        equipment_id: str,
    ) -> None:
        """Pull decision memory patterns and recent similar decisions.

        Only includes verified outcomes with >=50% success rate.
        Never overrides live telemetry or safety policy.
        """
        try:
            from app.services.decision_memory_service import get_decision_memory_service

            svc = get_decision_memory_service()
            eq_type = ctx.equipment_type or self._extract_equipment_type(equipment_id)

            # Get learned patterns for this equipment type
            patterns = []
            for event_type in [
                "temperature_deviation",
                "energy_spike",
                "sensor_failure",
                "comfort_violation",
                "pressure_anomaly",
                "pattern_anomaly",
            ]:
                pattern = await svc.get_recommended_action(event_type, eq_type)
                if pattern and pattern.success_rate >= 0.5:
                    patterns.append(pattern)

            # Get recent similar decisions (only resolved/verified)
            similar = await svc.find_similar_decisions(
                event_type="",  # any event type
                equipment_type=eq_type,
                equipment_id=equipment_id,
                limit=5,
            )

            text = svc.format_for_prompt(
                patterns=patterns if patterns else None,
                records=similar if similar else None,
            )
            if text:
                ctx.decision_memory = text
                ctx.sources_used.append("decision_memory")

        except Exception as e:
            logger.debug("Decision memory gather failed for %s: %s", equipment_id, e)

    @staticmethod
    def _extract_equipment_type(equipment_id: str) -> str:
        """Extract equipment type from code. S002-CHILLER-B1-001 -> CHILLER"""
        parts = equipment_id.split("-")
        return parts[1].upper() if len(parts) >= 2 else "UNKNOWN"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_instances: dict[str, HybridQueryService] = {}


def get_hybrid_query_service(site_id: str = "site-002") -> HybridQueryService:
    """Get or create HybridQueryService for a site."""
    if site_id not in _instances:
        _instances[site_id] = HybridQueryService(site_id=site_id)
    return _instances[site_id]
