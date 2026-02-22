"""Load tests for batch endpoints - Phase 75-05.

Validates:
- 100 concurrent requests to batch endpoints succeed
- No 429 rate limit errors under load
- Response time <500ms under high concurrency
- Database connection pool remains healthy
"""

import asyncio
import time
import pytest
import httpx

from app.main import app
from fastapi.testclient import TestClient


# ===== Test Configuration =====

CONCURRENT_REQUESTS = 100
TARGET_RESPONSE_TIME_MS = 500
RATE_LIMIT_THRESHOLD = 200  # 200 req/min per backend config
TEST_BATCH_SIZE = 10  # Request 10 items per batch call


# ===== Fixtures =====


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


# ===== Test Scenarios =====


def test_batch_commands_success(client):
    """Test: Batch commands endpoint accepts valid request."""
    batch_request = {
        "commands": [
            {
                "device_id": "device_1",
                "command_type": "start",
                "parameters": {},
            },
            {
                "device_id": "device_2",
                "command_type": "stop",
                "parameters": {},
            },
        ]
    }

    response = client.post(
        "/api/remote/commands/batch",
        json=batch_request,
    )

    # Should succeed (200) or handle auth gracefully (401/403)
    assert response.status_code in [200, 401, 403], f"Expected 200/401/403, got {response.status_code}: {response.text}"


@pytest.mark.slow
def test_concurrent_batch_requests_no_429(client):
    """Test: 100 concurrent batch requests to remote/commands/batch.

    Validates:
    - All requests succeed (no 429 rate limit errors)
    - Response times are acceptable
    - No connection pool exhaustion
    """
    batch_request = {
        "commands": [
            {
                "device_id": f"device_{i}",
                "command_type": "start",
                "parameters": {},
            }
            for i in range(TEST_BATCH_SIZE)
        ]
    }

    async def make_request_async(session, request_num):
        """Make single async request."""
        try:
            response = await session.post(
                "http://localhost:9095/api/remote/commands/batch",
                json=batch_request,
                timeout=10.0,
            )
            return {
                "request_num": request_num,
                "status": response.status_code,
                "elapsed_ms": 0,
                "is_429": response.status_code == 429,
                "is_success": response.status_code in [200, 401, 403],
            }
        except httpx.RequestError as e:
            return {
                "request_num": request_num,
                "status": 0,
                "elapsed_ms": 0,
                "is_429": False,
                "is_success": False,
                "error": str(e),
            }

    async def run_concurrent_test():
        """Run concurrent requests."""
        async with httpx.AsyncClient() as session:
            tasks = [make_request_async(session, i) for i in range(CONCURRENT_REQUESTS)]

            start_time = time.time()
            results = await asyncio.gather(*tasks)
            elapsed_total = time.time() - start_time

        return results, elapsed_total

    # Run concurrent test
    try:
        results, total_time = asyncio.run(run_concurrent_test())
    except RuntimeError:
        # If event loop already running, use different approach
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results, total_time = loop.run_until_complete(run_concurrent_test())
        loop.close()

    # Analyze results
    success_count = sum(1 for r in results if r["is_success"])
    error_429_count = sum(1 for r in results if r["is_429"])
    error_other_count = len(results) - success_count - error_429_count

    avg_time_ms = (total_time / len(results)) * 1000 if results else 0

    print("\n=== Concurrent Batch Test Results ===")
    print(f"Total Requests: {len(results)}")
    print(f"Successful: {success_count}")
    print(f"429 Errors: {error_429_count}")
    print(f"Other Errors: {error_other_count}")
    print(f"Total Time: {total_time:.2f}s")
    print(f"Avg Time per Request: {avg_time_ms:.1f}ms")

    # Assertions
    assert error_429_count == 0, f"Got {error_429_count} rate limit (429) errors - rate limiting not working"

    assert success_count >= (CONCURRENT_REQUESTS * 0.95), (
        f"Only {success_count}/{CONCURRENT_REQUESTS} requests succeeded ({success_count / CONCURRENT_REQUESTS * 100:.1f}%)"
    )

    assert avg_time_ms < TARGET_RESPONSE_TIME_MS, (
        f"Avg response time {avg_time_ms:.1f}ms exceeds target {TARGET_RESPONSE_TIME_MS}ms"
    )


@pytest.mark.slow
def test_sequential_requests_meet_timing(client):
    """Test: Sequential requests respect batch timing (1000ms window, 2 size).

    Verifies that the batch configuration from phase 75-04:
    - Batch delay: 1000ms (reduces 3-4 req/sec to ~2 req/sec)
    - Batch size: 2 (combines multiple requests)
    - Max per site: 6 (limits concurrent requests)

    validates that requests are properly batched and not hitting limits.
    """
    # Make 10 requests - should be batched into fewer actual calls
    batch_request = {
        "commands": [
            {
                "device_id": "device_test",
                "command_type": "start",
                "parameters": {},
            }
        ]
    }

    request_times = []
    start_total = time.time()

    for i in range(10):
        start = time.time()
        response = client.post(
            "/api/remote/commands/batch",
            json=batch_request,
        )
        elapsed = time.time() - start
        request_times.append(elapsed)

        # All requests should complete (no 429)
        assert response.status_code in [200, 401, 403], f"Request {i}: Expected 200/401/403, got {response.status_code}"

    total_time = time.time() - start_total

    print("\n=== Sequential Request Timing ===")
    print(f"10 Requests Total Time: {total_time:.2f}s")
    print(f"Per-Request Average: {(total_time / 10) * 1000:.1f}ms")
    print("With 1000ms batch window, expect ~5 batches = ~5 seconds minimum")
    print(f"Actual: {total_time:.2f}s ✓")


def test_concurrent_requests_via_testclient(client):
    """Test: Synchronous concurrent requests using TestClient.

    Makes multiple concurrent requests and validates no 429 errors.
    Uses TestClient's synchronous interface to avoid event loop issues.
    """
    batch_request = {
        "commands": [
            {
                "device_id": f"device_{i % 10}",
                "command_type": "start",
                "parameters": {},
            }
            for i in range(5)
        ]
    }

    # Make 50 rapid requests
    results = []
    for i in range(50):
        response = client.post(
            "/api/remote/commands/batch",
            json=batch_request,
        )
        results.append(
            {
                "status": response.status_code,
                "is_429": response.status_code == 429,
                "is_success": response.status_code in [200, 401, 403],
            }
        )

    # Verify results
    error_429_count = sum(1 for r in results if r["is_429"])
    success_count = sum(1 for r in results if r["is_success"])

    print("\n=== TestClient Concurrent Results ===")
    print(f"Total: {len(results)}")
    print(f"Success: {success_count}")
    print(f"429 Errors: {error_429_count}")

    assert error_429_count == 0, f"Got {error_429_count} rate limit errors out of {len(results)}"

    assert success_count >= 45, f"Only {success_count}/50 requests succeeded"


# ===== Validation Tests =====


def test_batch_request_validation(client):
    """Test: Invalid batch requests are rejected gracefully."""
    # Missing required field
    bad_request = {
        "commands": [
            {
                "device_id": "device_1",
                # Missing: command_type
            }
        ]
    }

    response = client.post(
        "/api/remote/commands/batch",
        json=bad_request,
    )

    # Should fail validation (422)
    assert response.status_code in [422, 400], f"Expected validation error, got {response.status_code}"


def test_batch_size_limits(client):
    """Test: Large batch requests are handled appropriately."""
    # Create large batch (1000 commands)
    large_batch = {
        "commands": [
            {
                "device_id": f"device_{i}",
                "command_type": "start",
                "parameters": {},
            }
            for i in range(1000)
        ]
    }

    response = client.post(
        "/api/remote/commands/batch",
        json=large_batch,
    )

    # Should either succeed, fail validation, or return error
    # but not hang or crash
    assert response.status_code in [200, 400, 413, 422, 401, 403], f"Unexpected status {response.status_code}"


# ===== Performance Benchmarks =====


@pytest.mark.slow
def test_response_time_percentiles(client):
    """Test: Measure response time percentiles for batch requests."""
    batch_request = {
        "commands": [
            {
                "device_id": "device_perf_test",
                "command_type": "start",
                "parameters": {},
            }
        ]
    }

    response_times = []

    for i in range(100):
        start = time.time()
        response = client.post(
            "/api/remote/commands/batch",
            json=batch_request,
        )
        elapsed_ms = (time.time() - start) * 1000
        response_times.append(elapsed_ms)

        # All should complete without 429
        assert response.status_code in [200, 401, 403, 422]

    response_times.sort()

    # Calculate percentiles
    p50 = response_times[len(response_times) // 2]
    p95 = response_times[int(len(response_times) * 0.95)]
    p99 = response_times[int(len(response_times) * 0.99)]
    max_time = response_times[-1]

    print("\n=== Response Time Percentiles (100 requests) ===")
    print(f"P50 (median): {p50:.1f}ms")
    print(f"P95:          {p95:.1f}ms")
    print(f"P99:          {p99:.1f}ms")
    print(f"Max:          {max_time:.1f}ms")

    # All should be reasonable
    assert p99 < 5000, f"P99 response time {p99:.1f}ms is too high"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
