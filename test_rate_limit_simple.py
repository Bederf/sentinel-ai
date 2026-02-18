#!/usr/bin/env python3
"""Simplified test script for rate limit fallback in BMS Intelligence hybrid AI service"""

import asyncio
import sys
import time
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
            "name": "Complex Query (should attempt Claude, fallback to Ollama)",
            "message": "Why is the chiller not starting?",
            "expected_provider": "anthropic"
        },
        {
            "name": "Status Check (should use Ollama)",
            "message": "What's the status of AHU-L12-01?",
            "expected_provider": "ollama"
        },
        {
            "name": "Diagnosis Query (should attempt Claude, fallback to Ollama)",
            "message": "Too hot at desk 25, what's wrong?",
            "expected_provider": "anthropic"
        }
    ]

    # Test normal routing first
    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. {test['name']}")
        print(f"   Query: {test['message']}")
        print(f"   Expected: {test['expected_provider']}")

        # Classify the task
        routing = hybrid_ai_service.classify_task(test['message'])
        print(f"   Routed to: {routing['provider']} ({routing['model']})")
        print(f"   Reason: {routing['reason']}")

        # Check rate limit status (without API key, Claude won't be available)
        can_use_claude = hybrid_ai_service._should_use_claude()
        print(f"   Claude available: {can_use_claude}")

        if routing['provider'] == 'anthropic' and not can_use_claude:
            print("   → Would fallback to Ollama (rate limited or no API key)")
        else:
            print(f"   → Will use {routing['provider']}")

        # Test Ollama directly
        print("   Testing Ollama response...")
        try:
            if routing['provider'] == 'ollama' or not can_use_claude:
                response = await hybrid_ai_service.query_ollama(
                    test['message'],
                    model=routing['model'],
                    escalate_on_fail=False
                )
                print(f"   ✓ Ollama response: {response[:100]}...")
            else:
                print("   → Skipping (would use Claude)")

        except Exception as e:
            print(f"   ✗ Ollama error: {e}")

    print("\n" + "=" * 80)
    print("Now testing rate limit simulation...")
    print("=" * 80)

    # Simulate rate limit scenario
    print("\n1. Simulating Claude rate limit...")

    # Manually set rate limit status
    hybrid_ai_service.claude_rate_limited = True
    hybrid_ai_service.rate_limit_time = time.time()
    print("2. Rate limit status set (cooldown active)")

    # Try a complex query that would normally use Claude
    complex_query = "Why is the chiller not starting?"
    routing = hybrid_ai_service.classify_task(complex_query)
    print(f"3. Query '{complex_query}' classified as: {routing['provider']}")

    can_use_claude = hybrid_ai_service._should_use_claude()
    print(f"4. Claude available: {can_use_claude}")

    if routing['provider'] == 'anthropic' and not can_use_claude:
        print("5. ✓ Rate limit detected - will fallback to Ollama")

        # Test the fallback
        print("\n6. Testing Ollama fallback...")
        try:
            response = await hybrid_ai_service.query_ollama(
                complex_query,
                model=hybrid_ai_service.ollama_models["balanced"],
                escalate_on_fail=False
            )
            print(f"   ✓ Fallback successful: {response[:100]}...")
        except Exception as e:
            print(f"   ✗ Fallback error: {e}")
    else:
        print("5. ✗ Fallback logic not working correctly")

    print("\n" + "=" * 80)
    print("Testing stream_response with rate limit...")
    print("=" * 80)

    # Test streaming response with rate limit
    async for chunk in hybrid_ai_service.stream_response("Why is the chiller making noise?"):
        print(f"Stream chunk: {chunk[:50]}...")
        break  # Just show first chunk

    print("\nTest complete!")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_rate_limit_fallback())
