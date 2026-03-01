"""
SENTINEL Dashboard Generator Event Subscriber — Phase 141-02.

Connects the event bus to the auto-dashboard generator. When sites are
onboarded or equipment is discovered, dashboards are automatically generated
with tailored cards, monitoring rules, and module suggestions.

Handlers:
1. auto_generate_dashboard  — system.site_onboarded -> generate full dashboard
2. handle_equipment_change  — system.equipment_discovered -> regenerate dashboard

Register at startup:
    from app.services.dashboard_gen_subscriber import register_dashboard_gen_subscribers
    register_dashboard_gen_subscribers()
"""

import logging

from app.services.event_bus import Importance, SentinelEvent, get_event_bus

logger = logging.getLogger("sentinel.dashboard_gen_events")


def register_dashboard_gen_subscribers() -> None:
    """Register dashboard generator subscribers on the event bus.

    Call at startup AFTER register_default_subscribers().
    Registers two handlers:
    - auto_generate_dashboard: triggered by system.site_onboarded
    - handle_equipment_change: triggered by system.equipment_discovered
    """
    bus = get_event_bus()

    # ------------------------------------------------------------------
    # 1. Auto Generate Dashboard — triggered when a site is onboarded
    # ------------------------------------------------------------------

    @bus.on("system.site_onboarded")
    async def auto_generate_dashboard(event: SentinelEvent) -> None:
        """Generate a full dashboard when a new site is onboarded.

        Extracts site_id and equipment_list from event payload, calls the
        dashboard generator, and emits chained events for the results.
        """
        site_id = event.payload.get("site_id") or event.site_id
        if not site_id:
            logger.warning("site_onboarded event missing site_id — skipping dashboard generation")
            return

        equipment_list = event.payload.get("equipment_list")

        logger.info(
            "Generating dashboard for onboarded site %s (equipment_count=%s)",
            site_id,
            len(equipment_list) if equipment_list else "auto-load",
        )

        try:
            from app.services.dashboard_generator import get_dashboard_generator

            generator = get_dashboard_generator()
            result = generator.generate_for_site(site_id, equipment_list=equipment_list)

            cards_generated = len(result.get("dashboard_cards", []))
            rules_generated = len(result.get("monitoring_rules", []))
            module_suggestions = result.get("module_suggestions", [])

            logger.info(
                "Dashboard generated for %s: %d cards, %d rules, %d module suggestions",
                site_id,
                cards_generated,
                rules_generated,
                len(module_suggestions),
            )

            # Emit dashboard_generated chain event
            await bus.emit(
                event.chain(
                    event_type="system.dashboard_generated",
                    source="dashboard_gen_subscriber",
                    payload={
                        "site_id": site_id,
                        "cards_generated": cards_generated,
                        "rules_generated": rules_generated,
                        "module_suggestions_count": len(module_suggestions),
                    },
                    importance=Importance.MEDIUM,
                )
            )

            # Emit module_suggested for each suggestion (LOW importance)
            for suggestion in module_suggestions:
                await bus.emit(
                    event.chain(
                        event_type="system.module_suggested",
                        source="dashboard_gen_subscriber",
                        payload={
                            "site_id": site_id,
                            "module": suggestion.get("module"),
                            "reason": suggestion.get("reason"),
                            "savings_hint": suggestion.get("savings_hint"),
                            "triggered_by": suggestion.get("triggered_by"),
                            "equipment_count": suggestion.get("equipment_count"),
                        },
                        importance=Importance.LOW,
                    )
                )

        except Exception as e:
            logger.error("Dashboard generation failed for %s: %s", site_id, e)

    # ------------------------------------------------------------------
    # 2. Handle Equipment Change — regenerate dashboard on discovery
    # ------------------------------------------------------------------

    @bus.on("system.equipment_discovered")
    async def handle_equipment_change(event: SentinelEvent) -> None:
        """Regenerate dashboard when new equipment is discovered at a site.

        Extracts site_id from the event and triggers a full dashboard
        regeneration to incorporate the new equipment.
        """
        site_id = event.payload.get("site_id") or event.site_id
        if not site_id:
            logger.warning("equipment_discovered event missing site_id — skipping")
            return

        logger.info(
            "Equipment change detected for %s — regenerating dashboard",
            site_id,
        )

        try:
            from app.services.dashboard_generator import get_dashboard_generator

            generator = get_dashboard_generator()
            result = generator.generate_for_site(site_id)

            logger.info(
                "Dashboard regenerated for %s: %d cards, %d rules",
                site_id,
                len(result.get("dashboard_cards", [])),
                len(result.get("monitoring_rules", [])),
            )
        except Exception as e:
            logger.error("Dashboard regeneration failed for %s: %s", site_id, e)

    # ------------------------------------------------------------------
    # Registration complete
    # ------------------------------------------------------------------
    logger.info("Dashboard generator event subscribers registered")
