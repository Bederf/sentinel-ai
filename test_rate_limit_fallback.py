#!/usr/bin/env python3
"""Test script for rate limit fallback in BMS Intelligence hybrid AI service"""

import asyncio
import sys
sys.path.insert(0, '/opt/bms-intelligence/backend')

from app.services.hybrid_ai_service import hybrid_ai_service

async def test_rate_limit_fallback():
    """Test that rate limit fallback works correctly"""

    print("=" * 80)
    print("Testing BMS Intelligence Hybrid AI Rate Limit Fallback")
    print("=" * 80)

    test_cases = [
        {
            "name": "Simple Query (should use Ollama)",
            "message": "What does error code E14 mean?",
            "expected_provider": "ollama"
        },
        {
            "name": "Complex Query (should use Claude, may fallback)",
            "message": "Why is the chiller not starting?",
            "expected_provider": "claude"
        },
        {
            "name": "Status Check (should use Ollama)",
            "message": "What's the status of AHU-L12-01?",
            "expected_provider": "ollama"
        },
        {
            "name": "Diagnosis Query (should use Claude, may fallback)",
            "message": "Too hot at desk 25, what's wrong?",
            "expected_provider": "claude"
        }
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['name']}")
        print(f"   Query: {test['message']}")
        print(f"   Expected: {test['expected_provider']}")

        # Classify the task
        routing = hybrid_ai_service.classify_task(test['message'])
        print(f"   Routed to: {routing['provider']} ({routing['model']})")
        print(f"   Reason: {routing['reason']}")

        # Check rate limit status
        can_use_claude = hybrid_ai_service._should_use_claude()
        print(f"   Claude available: {can_use_claude}")

        if routing['provider'] == 'anthropic' and not can_use_claude:
            print("   → Would fallback to Ollama (rate limited)")
        else:
            print(f"   → Will use {routing['provider']}")

        # Test streaming (just get first chunk)
        print("   Testing stream...")
        try:
            chunks = []
            async for chunk in hybrid_ai_service.stream_response(test['message']):
                chunks.append(chunk)
                if len(chunks) >= 2:  # Just get a few chunks
                    break

            response_preview = ''.join(chunks)[:100]
            print(f"   ✓ Stream working: {response_preview}...")

        except Exception as e:
            print(f"   ✗ Stream error: {e}")

    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)

    # Test rate limit simulation
    print("\nSimulating rate limit scenario...")
    print("1. Claude returns RateLimitError")

    # Manually set rate limit status
    hybrid_ai_service.claude_rate_limited = True
    hybrid_ai_service.rate_limit_time = time.time()
    print("2. Rate limit status set (cooldown active)")

    # Try a complex query
    complex_query = "Why is the chiller not starting?"
    routing = hybrid_ai_service.classify_task(complex_query)
    print(f"3. Query '{complex_query}' classified as: {routing['provider']}")

    can_use_claude = hybrid_ai_service._should_use_claude()
    print(f"4. Claude available: {can_use_claude}")

    if routing['provider'] == 'anthropic' and not can_use_claude:
        print("5. ✓ Will fallback to Ollama (rate limited)")
    else:
        print("5. ✗ Fallback logic not working correctly")

    print("\nRate limit simulation complete!")

if __name__ == "__main__":
    asyncio.run(test_rate_limit_fallback())
