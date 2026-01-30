#!/usr/bin/env python3
"""
Test Hybrid AI Routing - Demonstrates Ollama vs Claude routing
"""

import asyncio
import sys
sys.path.insert(0, '/opt/bms-intelligence/backend')

from app.services.hybrid_ai_service import hybrid_ai_service


async def test_routing():
    """Test routing logic with sample queries."""

    test_queries = [
        # Tier 1: Ollama (simple lookups)
        "What does error code E14 mean?",
        "What's the status of AHU-L12-01?",
        "Who stocks Carrier compressors?",
        "List all equipment with health < 70%",

        # Tier 2: Claude (complex reasoning)
        "Why is the chiller not starting?",
        "Too hot at desk 25",
        "Diagnose this unusual pattern in chiller operation",
        "What should I do about the rising filter DP?",

        # Control actions (Claude)
        "Turn on the chiller",
        "Set zone temperature to 20°C"
    ]

    print("=" * 80)
    print("HYBRID AI ROUTING TEST")
    print("=" * 80)

    for query in test_queries:
        routing = hybrid_ai_service.classify_task(query)

        print(f"\nQuery: {query}")
        print("-" * 76)
        print(f"Provider: {routing['provider'].upper()}")
        print(f"Model:    {routing['model']}")
        print(f"Reason:   {routing['reason']}")
        print(f"Tier:     {routing['tier']}")
        print(f"Cost:     ${routing['estimated_cost']:.4f}")

        # Visual indicator
        if routing['provider'] == 'ollama':
            print(f"✅ FREE (Local Ollama)")
        else:
            print(f"💸 PAID (Cloud Claude)")

    print("\n" + "=" * 80)
    print("ROUTING SUMMARY")
    print("=" * 80)

    ollama_count = sum(1 for q in test_queries if hybrid_ai_service.classify_task(q)['provider'] == 'ollama')
    claude_count = len(test_queries) - ollama_count

    print(f"\nTotal queries: {len(test_queries)}")
    print(f"Ollama (local): {ollama_count} ({ollama_count/len(test_queries)*100:.0f}%) - FREE")
    print(f"Claude (cloud): {claude_count} ({claude_count/len(test_queries)*100:.0f}%) - PAID")

    # Cost calculation
    ollama_cost = 0
    claude_cost = claude_count * 0.0105
    total_cost = ollama_cost + claude_cost
    all_claude_cost = len(test_queries) * 0.0105
    savings = all_claude_cost - total_cost

    print(f"\nCost Analysis:")
    print(f"  All Claude: ${all_claude_cost:.4f}")
    print(f"  Hybrid:     ${total_cost:.4f}")
    print(f"  Savings:    ${savings:.4f} ({savings/all_claude_cost*100:.0f}%)")


if __name__ == "__main__":
    asyncio.run(test_routing())
