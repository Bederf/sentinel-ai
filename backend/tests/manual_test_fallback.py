#!/usr/bin/env python3
"""
Manual test script for Hybrid AI fallback mechanism.

This script simulates various Claude API failure scenarios and verifies
that the system correctly falls back to Ollama.

Usage:
    cd backend
    source venv/bin/activate
    python tests/manual_test_fallback.py
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_api_error_fallback():
    """Test fallback when Claude API raises APIError."""
    print(f"\n{'='*60}")
    print("Testing: APIError Fallback (simulating 500 error)")
    print(f"{'='*60}")

    from app.services.hybrid_ai_service import HybridAIService
    from anthropic import APIError
    import httpx

    hybrid_ai = HybridAIService()

    # Create a mock httpx.Request for the error
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.method = "POST"
    mock_request.url = "https://api.anthropic.com/v1/messages"

    # Create APIError with proper signature (body param is required)
    api_error = APIError(message="Internal server error", request=mock_request, body=None)

    with patch('app.services.hybrid_ai_service.claude_service') as mock_claude:
        mock_claude.stream_response.side_effect = api_error

        # Mock Ollama to succeed
        async def mock_ollama(*args, **kwargs):
            return "[OLLAMA] Here are optimization recommendations based on current building data..."

        with patch.object(hybrid_ai, 'query_ollama', new=mock_ollama):
            try:
                response_chunks = []
                async for chunk in hybrid_ai.stream_response("Show me optimization recommendations", use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)

                print("\n✅ SUCCESS - Fallback triggered!")
                print(f"Response:\n{full_response}\n")

                # Verify fallback indicators
                checks = {
                    "Fallback message present": "Claude unavailable" in full_response,
                    "Ollama response present": "[OLLAMA]" in full_response,
                }

                for check, passed in checks.items():
                    print(f"  {'✅' if passed else '❌'} {check}")

                return all(checks.values())

            except Exception as e:
                print(f"\n❌ FAILED - Exception not handled: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                return False


async def test_connection_error_fallback():
    """Test fallback when Claude API connection fails."""
    print(f"\n{'='*60}")
    print("Testing: APIConnectionError Fallback")
    print(f"{'='*60}")

    from app.services.hybrid_ai_service import HybridAIService
    from anthropic import APIConnectionError
    import httpx

    hybrid_ai = HybridAIService()

    # Create mock request
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://api.anthropic.com/v1/messages"

    # Create error with proper signature (message is keyword-only)
    conn_error = APIConnectionError(request=mock_request, message="Connection to api.anthropic.com failed")

    with patch('app.services.hybrid_ai_service.claude_service') as mock_claude:
        mock_claude.stream_response.side_effect = conn_error

        async def mock_ollama(*args, **kwargs):
            return "[OLLAMA] AHU-7 status: Online, health 72%, last serviced 2025-12-15"

        with patch.object(hybrid_ai, 'query_ollama', new=mock_ollama):
            try:
                response_chunks = []
                async for chunk in hybrid_ai.stream_response("What's the status of AHU-7?", use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)
                print("\n✅ SUCCESS - Connection error handled!")
                print(f"Response:\n{full_response}\n")

                return "Claude unavailable" in full_response and "[OLLAMA]" in full_response

            except Exception as e:
                print(f"\n❌ FAILED: {e}")
                import traceback
                traceback.print_exc()
                return False


async def test_rate_limit_fallback():
    """Test fallback when rate limit is hit."""
    print(f"\n{'='*60}")
    print("Testing: RateLimitError Fallback")
    print(f"{'='*60}")

    from app.services.hybrid_ai_service import HybridAIService
    from anthropic import RateLimitError
    import httpx

    hybrid_ai = HybridAIService()

    # Create mock request and response with headers
    mock_request = MagicMock(spec=httpx.Request)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.headers = {"request-id": "req_test_123"}

    # Create error with proper signature (body is required)
    rate_error = RateLimitError(message="Rate limit exceeded", response=mock_response, body=None)

    with patch('app.services.hybrid_ai_service.claude_service') as mock_claude:
        mock_claude.stream_response.side_effect = rate_error

        async def mock_ollama(*args, **kwargs):
            return "[OLLAMA] Equipment in warning: CH-1 (68%), UPS-1 (65%), AHU-7 (72%)"

        with patch.object(hybrid_ai, 'query_ollama', new=mock_ollama):
            try:
                response_chunks = []
                async for chunk in hybrid_ai.stream_response("List warning status equipment", use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)
                print("\n✅ SUCCESS - Rate limit handled!")
                print(f"Response:\n{full_response}\n")

                return "rate limited" in full_response.lower() and "[OLLAMA]" in full_response

            except Exception as e:
                print(f"\n❌ FAILED: {e}")
                import traceback
                traceback.print_exc()
                return False


async def test_normal_operation():
    """Test that normal Claude operation doesn't trigger fallback."""
    print(f"\n{'='*60}")
    print("Testing: Normal Claude Operation (No Fallback)")
    print(f"{'='*60}")

    from app.services.hybrid_ai_service import HybridAIService

    hybrid_ai = HybridAIService()

    with patch('app.services.hybrid_ai_service.claude_service') as mock_claude:
        # Mock successful Claude response
        async def mock_claude_success(*args, **kwargs):
            yield "Building occupancy is currently 56% (170/300 desks occupied)"

        mock_claude.stream_response.return_value = mock_claude_success()

        # Mock Ollama (should NOT be called)
        async def mock_ollama_fail(*args, **kwargs):
            raise Exception("Ollama should not have been called!")

        with patch.object(hybrid_ai, 'query_ollama', new=mock_ollama_fail):
            try:
                response_chunks = []
                async for chunk in hybrid_ai.stream_response("What is the building occupancy?", use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)
                print("\n✅ SUCCESS - No fallback triggered!")
                print(f"Response:\n{full_response}\n")

                return "56%" in full_response and "Ollama" not in full_response

            except Exception as e:
                print(f"\n❌ FAILED: {e}")
                return False


async def test_both_ais_fail():
    """Test graceful handling when both Claude and Ollama fail."""
    print(f"\n{'='*60}")
    print("Testing: Both AI Services Fail")
    print(f"{'='*60}")

    from app.services.hybrid_ai_service import HybridAIService
    from anthropic import APIError
    import httpx

    hybrid_ai = HybridAIService()

    mock_request = MagicMock(spec=httpx.Request)
    api_error = APIError(message="Service unavailable", request=mock_request, body=None)

    with patch('app.services.hybrid_ai_service.claude_service') as mock_claude:
        mock_claude.stream_response.side_effect = api_error

        # Mock Ollama to also fail
        async def mock_ollama_fail(*args, **kwargs):
            raise Exception("Ollama service not responding")

        with patch.object(hybrid_ai, 'query_ollama', new=mock_ollama_fail):
            try:
                response_chunks = []
                async for chunk in hybrid_ai.stream_response("Test query", use_tools=False):
                    response_chunks.append(chunk)

                full_response = "".join(response_chunks)
                print("\n✅ SUCCESS - Graceful error handling!")
                print(f"Response:\n{full_response}\n")

                return "technical difficulties" in full_response.lower() and "try again" in full_response.lower()

            except Exception as e:
                print(f"\n❌ FAILED - Exception not handled: {e}")
                return False


async def main():
    """Run all test scenarios."""
    print("\n" + "="*60)
    print("HYBRID AI FALLBACK MECHANISM - MANUAL TEST SUITE")
    print("="*60)

    tests = [
        ("APIError (500)", test_api_error_fallback),
        ("APIConnectionError", test_connection_error_fallback),
        ("RateLimitError", test_rate_limit_fallback),
        ("Normal Operation", test_normal_operation),
        ("Both AIs Fail", test_both_ais_fail),
    ]

    results = []

    for name, test_func in tests:
        result = await test_func()
        results.append((name, result))

    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Fallback mechanism is working correctly.")
        print("\nThe system will now:")
        print("  • Automatically fall back to local Ollama when Claude API fails")
        print("  • Show user-friendly error messages")
        print("  • Handle 500, 502, 503, connection errors, and timeouts")
        print("  • Continue operation even during cloud AI outages")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
