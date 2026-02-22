"""
Performance tests configuration.

Provides benchmark fixture fallback if pytest-benchmark is not installed.
"""

import pytest

try:
    # Try to import from pytest-benchmark
    from pytest_benchmark.fixture import BenchmarkFixture

    HAS_BENCHMARK = True
except ImportError:
    HAS_BENCHMARK = False


@pytest.fixture
def benchmark():
    """Benchmark fixture that falls back to simple execution if pytest-benchmark not installed."""
    if HAS_BENCHMARK:
        pytest.skip("Use pytest-benchmark's fixture instead")

    # Simple fallback that just runs the function once
    class SimpleBenchmark:
        def __call__(self, func):
            return func()

    return SimpleBenchmark()
