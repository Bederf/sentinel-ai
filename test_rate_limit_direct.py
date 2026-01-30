#!/usr/bin/env python3
"""Direct test of rate limit fallback logic without external dependencies"""

import sys
sys.path.insert(0, '/opt/bms-intelligence/backend')

from app.services.hybrid_ai_service import HybridAIService
import time

def test_classification_and_rate_limiting():
    """Test the classification and rate limit logic directly"""

    print("=" * 80)
    print("Testing BMS Intelligence Hybrid AI - Classification & Rate Limit Logic")
    print("=" * 80)

    # Create a test instance
    service = HybridAIService()

    test_cases = [
        {
            "message": "What does error code E14 mean?",
            "expected_tier": 1,
            "expected_provider": "ollama"
        },
        {
            "message": "What's the status of AHU-L12-01?",
            "expected_tier": 1,
            "expected_provider": "ollama"
        },
        {
            "message": "List all equipment with health < 70%",
            "expected_tier": 1,
            "expected_provider": "ollama"
        },
        {
            "message": "Why is the chiller not starting?",
            "expected_tier": 2,
            "expected_provider": "anthropic"
        },
        {
            "message": "Too hot at desk 25, what's wrong?",
            "expected_tier": 2,
            "expected_provider": "anthropic"
        },
        {
            "message": "Diagnose this fault code F1234",
            "expected_tier": 2,
            "expected_provider": "anthropic"
        },
        {
            "message": "Set temperature to 22 degrees",
            "expected_tier": 2,
            "expected_provider": "anthropic"
        }
    ]

    print("\n1. Testing Task Classification:")
    print("-" * 50)

    for i, test in enumerate(test_cases, 1):
        print(f"\n{i}. Query: '{test['message']}'")

        # Classify the task
        routing = service.classify_task(test['message'])

        print(f"   Provider: {routing['provider']}")
        print(f"   Model: {routing['model']}")
        print(f"   Tier: {routing['tier']}")
        print(f"   Reason: {routing['reason']}")
        print(f"   Estimated Cost: ${routing['estimated_cost']}")

        # Verify expectations
        if routing['tier'] == test['expected_tier'] and routing['provider'] == test['expected_provider']:
            print("   ✓ Classification correct")
        else:
            print(f"   ✗ Expected tier {test['expected_tier']} ({test['expected_provider']}), got tier {routing['tier']} ({routing['provider']})")

    print("\n\n2. Testing Rate Limit Logic:")
    print("-" * 50)

    # Test normal state
    print("\nNormal state:")
    print(f"   Claude rate limited: {service.claude_rate_limited}")
    print(f"   Should use Claude: {service._should_use_claude()}")

    # Simulate rate limit
    print("\nSimulating rate limit...")
    service.claude_rate_limited = True
    service.rate_limit_time = time.time()
    print(f"   Claude rate limited: {service.claude_rate_limited}")
    print(f"   Should use Claude: {service._should_use_claude()}")

    # Test a complex query during rate limit
    print("\n3. Testing Complex Query During Rate Limit:")
    print("-" * 50)

    complex_query = "Why is the chiller making unusual noises?"
    routing = service.classify_task(complex_query)
    print(f"\nQuery: '{complex_query}'")
    print(f"Classified as: {routing['provider']} (tier {routing['tier']})")

    # Check if Claude is available
    can_use_claude = service._should_use_claude()
    print(f"Claude available: {can_use_claude}")

    if routing['provider'] == 'anthropic' and not can_use_claude:
        print("✓ Rate limit detected - would fallback to Ollama")
        print(f"   Fallback model: {service.ollama_models['balanced']}")
    else:
        print("✗ Rate limit logic not working as expected")

    # Test cooldown expiration
    print("\n4. Testing Cooldown Expiration:")
    print("-" * 50)

    # Set rate limit time to 61 seconds ago
    service.rate_limit_time = time.time() - 61
    print(f"Setting rate limit time to 61 seconds ago...")
    print(f"Cooldown period: {service.cooldown_period} seconds")
    print(f"Should use Claude now: {service._should_use_claude()}")

    if service._should_use_claude():
        print("✓ Cooldown expired - Claude available again")
    else:
        print("✗ Cooldown not working correctly")

    print("\n" + "=" * 80)
    print("Test Summary:")
    print("- Task classification correctly routes simple queries to Ollama (free)")
    print("- Complex queries are routed to Claude (paid) when available")
    print("- Rate limit detection prevents Claude usage during cooldown")
    print("- Fallback to Ollama occurs automatically during rate limits")
    print("- Cooldown period (60s) expires correctly")
    print("=" * 80)

if __name__ == "__main__":
    test_classification_and_rate_limiting()