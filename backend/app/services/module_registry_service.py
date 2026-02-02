"""
Module Registry Service - Manages Bolt-on Module System

Handles:
- Module activation/deactivation per site
- Cross-module integration
- Unified AI recommendations from all active modules
- Telemetry aggregation
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import asdict
import uuid

from app.models.module_registry import (
    ModuleType, ModuleStatus, ModuleDefinition, ModuleInstance,
    CrossModuleLink, AIRecommendation, ModuleIntegrationEvent,
    SiteModuleConfig, RecommendationType, RecommendationPriority,
    MODULE_DEFINITIONS, INTEGRATION_DEFINITIONS
)
from app.services.health_threshold_service import get_health_thresholds

logger = logging.getLogger(__name__)


class ModuleRegistryService:
    """
    Central service for managing bolt-on modules.

    Modules can operate standalone but integrate when multiple are activated.
    """

    def __init__(self):
        """Initialize module registry."""
        self.data_dir = Path(__file__).parent.parent / "data" / "modules"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._site_configs: Dict[str, SiteModuleConfig] = {}
        self._recommendations: Dict[str, List[AIRecommendation]] = {}  # By site
        self._load_configs()

    def _load_configs(self) -> None:
        """Load site module configurations from disk."""
        config_file = self.data_dir / "site_modules.json"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    data = json.load(f)
                for site_id, config in data.items():
                    self._site_configs[site_id] = self._parse_site_config(config)
                logger.info(f"Loaded module configs for {len(self._site_configs)} sites")
            except Exception as e:
                logger.error(f"Error loading module configs: {e}")

    def _save_configs(self) -> None:
        """Save site module configurations to disk."""
        config_file = self.data_dir / "site_modules.json"
        try:
            data = {}
            for site_id, config in self._site_configs.items():
                data[site_id] = self._serialize_site_config(config)
            with open(config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving module configs: {e}")

    def _parse_site_config(self, data: Dict) -> SiteModuleConfig:
        """Parse site config from JSON."""
        return SiteModuleConfig(
            site_id=data["site_id"],
            site_name=data["site_name"],
            active_modules=[
                ModuleInstance(
                    instance_id=m["instance_id"],
                    site_id=m["site_id"],
                    module_type=ModuleType(m["module_type"]),
                    status=ModuleStatus(m["status"]),
                    activated_at=m["activated_at"],
                    config=m.get("config", {}),
                    health_score=m.get("health_score", 100.0),
                    last_telemetry=m.get("last_telemetry"),
                    error_message=m.get("error_message")
                )
                for m in data.get("active_modules", [])
            ],
            cross_module_links=[
                CrossModuleLink(
                    link_id=l["link_id"],
                    source_module=ModuleType(l["source_module"]),
                    target_module=ModuleType(l["target_module"]),
                    integration_type=l["integration_type"],
                    enabled=l.get("enabled", True),
                    config=l.get("config", {})
                )
                for l in data.get("cross_module_links", [])
            ],
            ai_enabled=data.get("ai_enabled", True),
            auto_integration=data.get("auto_integration", True)
        )

    def _serialize_site_config(self, config: SiteModuleConfig) -> Dict:
        """Serialize site config to JSON."""
        return {
            "site_id": config.site_id,
            "site_name": config.site_name,
            "active_modules": [
                {
                    "instance_id": m.instance_id,
                    "site_id": m.site_id,
                    "module_type": m.module_type.value,
                    "status": m.status.value,
                    "activated_at": m.activated_at,
                    "config": m.config,
                    "health_score": m.health_score,
                    "last_telemetry": m.last_telemetry,
                    "error_message": m.error_message
                }
                for m in config.active_modules
            ],
            "cross_module_links": [
                {
                    "link_id": l.link_id,
                    "source_module": l.source_module.value,
                    "target_module": l.target_module.value,
                    "integration_type": l.integration_type,
                    "enabled": l.enabled,
                    "config": l.config
                }
                for l in config.cross_module_links
            ],
            "ai_enabled": config.ai_enabled,
            "auto_integration": config.auto_integration
        }

    # ==================== Module Management ====================

    def get_available_modules(self) -> List[ModuleDefinition]:
        """Get all available module definitions."""
        return list(MODULE_DEFINITIONS.values())

    def get_module_definition(self, module_type: ModuleType) -> Optional[ModuleDefinition]:
        """Get definition for a specific module type."""
        return MODULE_DEFINITIONS.get(module_type)

    def get_site_config(self, site_id: str) -> Optional[SiteModuleConfig]:
        """Get module configuration for a site."""
        return self._site_configs.get(site_id)

    def get_active_modules(self, site_id: str) -> List[ModuleInstance]:
        """Get all active modules for a site."""
        config = self._site_configs.get(site_id)
        if not config:
            return []
        return [m for m in config.active_modules if m.status == ModuleStatus.ACTIVE]

    def is_module_active(self, site_id: str, module_type: ModuleType) -> bool:
        """Check if a specific module is active for a site."""
        modules = self.get_active_modules(site_id)
        return any(m.module_type == module_type for m in modules)

    def activate_module(
        self,
        site_id: str,
        site_name: str,
        module_type: ModuleType,
        config: Optional[Dict[str, Any]] = None
    ) -> ModuleInstance:
        """
        Activate a module for a site.

        Creates cross-module links automatically if auto_integration is enabled.
        """
        # Get or create site config
        if site_id not in self._site_configs:
            self._site_configs[site_id] = SiteModuleConfig(
                site_id=site_id,
                site_name=site_name
            )

        site_config = self._site_configs[site_id]

        # Check if module already active
        existing = next(
            (m for m in site_config.active_modules if m.module_type == module_type),
            None
        )
        if existing:
            existing.status = ModuleStatus.ACTIVE
            existing.error_message = None
            self._save_configs()
            return existing

        # Create new module instance
        instance = ModuleInstance(
            instance_id=f"{site_id}-{module_type.value}-{uuid.uuid4().hex[:8]}",
            site_id=site_id,
            module_type=module_type,
            status=ModuleStatus.ACTIVE,
            activated_at=datetime.utcnow().isoformat(),
            config=config or {}
        )

        site_config.active_modules.append(instance)

        # Auto-create cross-module links
        if site_config.auto_integration:
            self._create_integration_links(site_id, module_type)

        self._save_configs()
        logger.info(f"Activated module {module_type.value} for site {site_id}")

        return instance

    def deactivate_module(self, site_id: str, module_type: ModuleType) -> bool:
        """Deactivate a module for a site."""
        config = self._site_configs.get(site_id)
        if not config:
            return False

        for module in config.active_modules:
            if module.module_type == module_type:
                module.status = ModuleStatus.INACTIVE

                # Disable related cross-module links
                for link in config.cross_module_links:
                    if link.source_module == module_type or link.target_module == module_type:
                        link.enabled = False

                self._save_configs()
                logger.info(f"Deactivated module {module_type.value} for site {site_id}")
                return True

        return False

    def _create_integration_links(self, site_id: str, new_module: ModuleType) -> None:
        """Create cross-module integration links when a new module is activated."""
        config = self._site_configs.get(site_id)
        if not config:
            return

        module_def = MODULE_DEFINITIONS.get(new_module)
        if not module_def:
            return

        # Get other active modules that can integrate
        active_types = {m.module_type for m in config.active_modules if m.status == ModuleStatus.ACTIVE}

        for integration_id, integration_def in INTEGRATION_DEFINITIONS.items():
            source = integration_def["source"]
            target = integration_def["target"]

            # Check if this integration applies to the new module and another active module
            if (source == new_module and target in active_types) or \
               (target == new_module and source in active_types):

                # Check if link already exists
                existing = any(
                    l.integration_type == integration_id
                    for l in config.cross_module_links
                )
                if not existing:
                    link = CrossModuleLink(
                        link_id=f"{site_id}-{integration_id}",
                        source_module=source,
                        target_module=target,
                        integration_type=integration_id,
                        enabled=True
                    )
                    config.cross_module_links.append(link)
                    logger.info(f"Created integration link: {integration_id} for site {site_id}")

    # ==================== AI Recommendations ====================

    def add_recommendation(self, site_id: str, recommendation: AIRecommendation) -> None:
        """Add an AI recommendation for a site."""
        if site_id not in self._recommendations:
            self._recommendations[site_id] = []

        self._recommendations[site_id].append(recommendation)

        # Keep only last 100 recommendations
        if len(self._recommendations[site_id]) > 100:
            self._recommendations[site_id] = self._recommendations[site_id][-100:]

        # Check for cross-module actions
        self._process_cross_module_recommendation(site_id, recommendation)

    def get_recommendations(
        self,
        site_id: str,
        module_filter: Optional[List[ModuleType]] = None,
        priority_filter: Optional[List[RecommendationPriority]] = None,
        include_resolved: bool = False,
        limit: int = 50
    ) -> List[AIRecommendation]:
        """Get AI recommendations for a site with optional filters."""
        recs = self._recommendations.get(site_id, [])

        # Filter by module
        if module_filter:
            recs = [r for r in recs if r.source_module in module_filter]

        # Filter by priority
        if priority_filter:
            recs = [r for r in recs if r.priority in priority_filter]

        # Filter resolved
        if not include_resolved:
            recs = [r for r in recs if not r.resolved]

        # Sort by priority and timestamp
        priority_order = {
            RecommendationPriority.CRITICAL: 0,
            RecommendationPriority.HIGH: 1,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 3
        }
        recs.sort(key=lambda r: (priority_order.get(r.priority, 99), r.timestamp), reverse=True)

        return recs[:limit]

    def acknowledge_recommendation(self, site_id: str, recommendation_id: str) -> bool:
        """Mark a recommendation as acknowledged."""
        recs = self._recommendations.get(site_id, [])
        for rec in recs:
            if rec.recommendation_id == recommendation_id:
                rec.acknowledged = True
                return True
        return False

    def resolve_recommendation(self, site_id: str, recommendation_id: str) -> bool:
        """Mark a recommendation as resolved."""
        recs = self._recommendations.get(site_id, [])
        for rec in recs:
            if rec.recommendation_id == recommendation_id:
                rec.resolved = True
                return True
        return False

    def _process_cross_module_recommendation(
        self,
        site_id: str,
        recommendation: AIRecommendation
    ) -> None:
        """Process recommendation for cross-module actions."""
        if recommendation.recommendation_type != RecommendationType.CROSS_SYSTEM:
            return

        config = self._site_configs.get(site_id)
        if not config:
            return

        # Check if related modules are active and linked
        for related_module in recommendation.related_modules:
            if not self.is_module_active(site_id, related_module):
                continue

            # Find enabled link between source and related module
            link = next(
                (l for l in config.cross_module_links
                 if l.enabled and
                 ((l.source_module == recommendation.source_module and l.target_module == related_module) or
                  (l.source_module == related_module and l.target_module == recommendation.source_module))),
                None
            )

            if link and recommendation.auto_actionable:
                # Log the cross-module event
                event = ModuleIntegrationEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:8]}",
                    timestamp=datetime.utcnow().isoformat(),
                    source_module=recommendation.source_module,
                    target_modules=[related_module],
                    event_type="action_request",
                    payload={
                        "recommendation_id": recommendation.recommendation_id,
                        "action": recommendation.suggested_action
                    }
                )
                logger.info(f"Cross-module event: {event.event_id} - {recommendation.source_module} -> {related_module}")

    # ==================== Telemetry Integration ====================

    def get_unified_telemetry(self, site_id: str) -> Dict[str, Any]:
        """
        Get unified telemetry from all active modules.

        This provides a single view of all building telemetry for AI analysis.
        """
        config = self._site_configs.get(site_id)
        if not config:
            return {}

        telemetry = {
            "site_id": site_id,
            "timestamp": datetime.utcnow().isoformat(),
            "modules": {},
            "cross_module_status": {}
        }

        active_modules = self.get_active_modules(site_id)

        for module in active_modules:
            module_def = MODULE_DEFINITIONS.get(module.module_type)
            if module_def:
                telemetry["modules"][module.module_type.value] = {
                    "status": module.status.value,
                    "health_score": module.health_score,
                    "last_telemetry": module.last_telemetry,
                    "capabilities": [c.capability_id for c in module_def.capabilities],
                    "ai_features": module_def.ai_features
                }

        # Add cross-module integration status
        for link in config.cross_module_links:
            if link.enabled:
                telemetry["cross_module_status"][link.integration_type] = {
                    "source": link.source_module.value,
                    "target": link.target_module.value,
                    "enabled": link.enabled
                }

        return telemetry

    def update_module_health(
        self,
        site_id: str,
        module_type: ModuleType,
        health_score: float,
        telemetry_timestamp: Optional[str] = None
    ) -> None:
        """Update health score and telemetry timestamp for a module."""
        config = self._site_configs.get(site_id)
        if not config:
            return

        for module in config.active_modules:
            if module.module_type == module_type:
                module.health_score = health_score
                module.last_telemetry = telemetry_timestamp or datetime.utcnow().isoformat()

                # Generate health recommendation if needed (using configured thresholds)
                thresholds = get_health_thresholds()
                if health_score < thresholds["warning"]:
                    self.add_recommendation(
                        site_id,
                        AIRecommendation(
                            recommendation_id=f"health-{module_type.value}-{uuid.uuid4().hex[:8]}",
                            timestamp=datetime.utcnow().isoformat(),
                            source_module=module_type,
                            recommendation_type=RecommendationType.MAINTENANCE,
                            priority=RecommendationPriority.HIGH if health_score < thresholds["critical"] else RecommendationPriority.MEDIUM,
                            title=f"{module_type.value.upper()} Module Health Warning",
                            description=f"Module health at {health_score:.0f}%. Investigation recommended.",
                            confidence=0.9,
                            telemetry_context={"health_score": health_score}
                        )
                    )
                break

        self._save_configs()

    # ==================== Integration Summary ====================

    def get_integration_summary(self, site_id: str) -> Dict[str, Any]:
        """Get summary of module integration status."""
        config = self._site_configs.get(site_id)
        if not config:
            return {"error": "Site not configured"}

        active_modules = self.get_active_modules(site_id)
        active_types = [m.module_type for m in active_modules]

        # Calculate potential integrations
        potential_integrations = []
        active_integrations = []

        for integration_id, integration_def in INTEGRATION_DEFINITIONS.items():
            source = integration_def["source"]
            target = integration_def["target"]

            link = next(
                (l for l in config.cross_module_links if l.integration_type == integration_id),
                None
            )

            if source in active_types and target in active_types:
                if link and link.enabled:
                    active_integrations.append({
                        "id": integration_id,
                        "name": integration_def["name"],
                        "description": integration_def["description"],
                        "source": source.value,
                        "target": target.value
                    })
            elif source in active_types or target in active_types:
                missing = target if source in active_types else source
                potential_integrations.append({
                    "id": integration_id,
                    "name": integration_def["name"],
                    "requires_module": missing.value
                })

        return {
            "site_id": site_id,
            "site_name": config.site_name,
            "active_modules": [
                {
                    "type": m.module_type.value,
                    "name": MODULE_DEFINITIONS[m.module_type].name,
                    "health": m.health_score,
                    "status": m.status.value
                }
                for m in active_modules
            ],
            "active_integrations": active_integrations,
            "potential_integrations": potential_integrations,
            "ai_enabled": config.ai_enabled,
            "pending_recommendations": len([
                r for r in self._recommendations.get(site_id, [])
                if not r.resolved and not r.acknowledged
            ])
        }


# Singleton instance
module_registry = ModuleRegistryService()
