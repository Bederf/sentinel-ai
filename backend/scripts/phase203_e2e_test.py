#!/usr/bin/env python3
"""
Phase 203 E2E Smoke Test
=========================
Tests the full recommendation pipeline: create → route → outcome written.

Usage:
    cd backend
    SITE_ID=site-002 PLANT_SITE_ID=S002 BUILDING_NAME="Sandton City Office Tower" \
        DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:55322/postgres" \
        REDIS_HOST=127.0.0.1 \
        python scripts/phase203_e2e_test.py
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage

from app.agents.recommendation_graph import get_recommendation_graph
from app.database.repositories import get_recommendation_repository


async def insert_fresh_recommendation(site_id: str, equipment_code: str) -> str:
    """Insert a fresh recommendation directly in DB."""
    from app.models.recommendation import ActionRiskLevel, Recommendation, RecommendationStatus

    repo = get_recommendation_repository()
    now = datetime.now(UTC)

    rec = Recommendation(
        site_id=site_id,
        timestamp=now,
        action_type="ai_optimization",
        risk_level=ActionRiskLevel.MEDIUM,
        target_equipment=equipment_code,
        action={"test": True},
        reason="E2E test recommendation",
        expected_impact={"cost_zar": 100, "energy_kwh": 50},
        confidence="medium",
        confidence_score=0.85,
        profile="cost",
        status=RecommendationStatus.PENDING,
        source="e2e_test",
        source_type="ml_model",
    )

    created = await repo.create(rec)
    print(f"  ✅ Created recommendation: {created.id}")
    return created.id


async def invoke_graph_and_check(site_id: str, _rec_id: str = "") -> dict:
    """Invoke recommendation graph for site and check if rec is processed."""
    agent = get_recommendation_graph()
    thread_id = f"phase203_e2e_{uuid.uuid4().hex[:8]}"

    result = await agent.ainvoke(
        {
            "messages": [HumanMessage(content="process")],
            "site_id": site_id,
            "channel": "system",
            "trigger": "e2e_test",
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    return result


async def check_parasite_decision(rec_id: str) -> dict | None:
    """Check if parasite_decision exists with populated outcome."""
    from app.database.repositories.parasite_decision_repository import ParasiteDecisionRepository

    repo = ParasiteDecisionRepository()

    # Get recent decisions and filter by recommendation_id
    decisions = await repo.get_decisions_by_site(site_id="S002", limit=100)

    # Find decision for our recommendation
    for d in decisions:
        if d.get("recommendation_id") == rec_id:
            return {
                "id": str(d["id"]),
                "recommendation_id": str(d["recommendation_id"]),
                "routing_source": d.get("routing_source"),
                "outcome": d.get("outcome"),
                "created_at": str(d.get("created_at")) if d.get("created_at") else None,
            }
    return None


async def run_e2e_test(site_id: str = "S002", equipment_code: str = "S002-CT-R-001") -> bool:
    """Run the full E2E test."""
    print("\n" + "=" * 60)
    print("PHASE 203 E2E SMOKE TEST")
    print("=" * 60)

    # Step 1: Create fresh recommendation
    print(f"\n[1/4] Creating fresh recommendation for {site_id}...")
    rec_id = await insert_fresh_recommendation(site_id, equipment_code)
    rec_id_short = rec_id[:8]

    # Step 2: Invoke graph (bypass APScheduler timing)
    print("\n[2/4] Invoking recommendation graph (bypassing APScheduler)...")
    result = await invoke_graph_and_check(site_id, rec_id)
    print(f"  Graph completed. Nodes visited: {result.get('nodes_visited', [])}")

    # Step 3: Check for parasite_decision
    print("\n[3/4] Checking for parasite_decision with populated outcome...")
    decision = await check_parasite_decision(rec_id)

    if not decision:
        print("  ❌ No parasite_decision found for recommendation")
        return False

    print(f"  ✅ Found decision: {decision['id'][:8]}")
    print(f"     routing_source: {decision['routing_source']}")
    print(f"     outcome: {decision['outcome']}")

    # Step 4: Evaluate
    print("\n[4/4] Evaluating results...")
    outcome = decision["outcome"]
    is_populated = outcome and outcome != {} and outcome != "[]"

    if is_populated:
        print("\n" + "=" * 60)
        print("✅ E2E TEST PASSED")
        print("=" * 60)
        print(f"  Recommendation: {rec_id_short}...")
        print(f"  Decision: {decision['id'][:8]}...")
        print(f"  Outcome: {outcome}")
        return True
    else:
        print("\n" + "=" * 60)
        print("❌ E2E TEST FAILED")
        print("=" * 60)
        print(f"  Recommendation: {rec_id_short}...")
        print(f"  Decision: {decision['id'][:8]}...")
        print(f"  Outcome: {outcome} (empty)")
        return False


async def main():
    site_id = "S002"
    equipment = "S002-CT-R-001"

    if len(sys.argv) > 1:
        site_id = sys.argv[1]
    if len(sys.argv) > 2:
        equipment = sys.argv[2]

    try:
        success = await run_e2e_test(site_id, equipment)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
