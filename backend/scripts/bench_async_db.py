#!/usr/bin/env python3
"""
Benchmark: async vs sync Supabase client under concurrent load.

Measures whether the async client actually overlaps concurrent queries,
and quantifies wall-time improvement vs the sync client.

Usage:
    venv/bin/python scripts/bench_async_db.py               # quick smoke test
    venv/bin/python scripts/bench_async_db.py --sweep       # full sweep (30s+)
"""

import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("SENTINEL_EXECUTION_MODE", "api")
os.environ.setdefault("SENTINEL_ROUTING_PROFILE", "api_prod")

from app.config.settings import settings
from app.database.supabase_client import get_supabase_client
from supabase import create_async_client


PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"


def elapsed(start: float) -> str:
    return f"{(time.perf_counter() - start) * 1000:.1f}ms"


def print_result(name: str, ok: bool, detail: str = ""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))


class SyncBench:
    """Sync Supabase client benchmarks."""

    def __init__(self):
        self.client = get_supabase_client()

    def run_query(self, table: str, limit: int = 5):
        start = time.perf_counter()
        result = self.client.table(table).select("*").limit(limit).execute()
        duration = time.perf_counter() - start
        return result, duration

    def run_serial(self, queries: list[tuple[str, int]]):
        times = []
        for table, limit in queries:
            _, dur = self.run_query(table, limit)
            times.append(dur)
        return times

    def run_concurrent(self, queries: list[tuple[str, int]]):
        """Simulate concurrent sync requests (sequential, because sync)."""
        return self.run_serial(queries)


class AsyncBench:
    """Async Supabase client benchmarks."""

    def __init__(self):
        self.client = None

    async def ensure_client(self):
        if self.client is None:
            self.client = await create_async_client(settings.supabase_url, settings.supabase_service_role_key)

    async def run_query(self, table: str, limit: int = 5):
        await self.ensure_client()
        start = time.perf_counter()
        result = await self.client.table(table).select("*").limit(limit).execute()
        duration = time.perf_counter() - start
        return result, duration

    async def run_serial(self, queries: list[tuple[str, int]]):
        times = []
        for table, limit in queries:
            _, dur = await self.run_query(table, limit)
            times.append(dur)
        return times

    async def run_concurrent(self, queries: list[tuple[str, int]]):
        tasks = [self.run_query(table, limit) for table, limit in queries]
        results = await asyncio.gather(*tasks)
        times = [r[1] for r in results]
        return times

    async def close(self):
        if self.client:
            await self.client.postgrest.aclose()


QUERIES_ALARM_STORM = [
    ("alerts", 20),
    ("alerts", 20),
    ("equipment", 10),
    ("sites", 5),
    ("work_orders", 10),
    ("recommendations", 10),
    ("equipment", 5),
    ("alerts", 20),
    ("equipment", 10),
    ("sites", 5),
]


async def run_smoke(async_b: AsyncBench):
    """Quick sanity check — 1 query each."""
    print(f"\n{BOLD}Smoke Test{RESET}")
    print("-" * 60)

    sync_b = SyncBench()
    _, dur_sync = sync_b.run_query("sites", 1)
    print_result("sync query", dur_sync < 5000, f"{dur_sync * 1000:.0f}ms")

    _, dur_async = await async_b.run_query("sites", 1)
    print_result("async query", dur_async < 5000, f"{dur_async * 1000:.0f}ms")
    print()


async def run_concurrency(async_b: AsyncBench, count: int):
    """Run N queries concurrently, measure serial vs concurrent wall time."""
    print(f"{BOLD}Concurrency Test ({count} parallel queries){RESET}")
    print("-" * 60)

    tables = [("sites", 20)] * count

    sync_b = SyncBench()
    start = time.perf_counter()
    sync_times = sync_b.run_concurrent(tables)
    sync_wall = time.perf_counter() - start
    sync_total = sum(sync_times)
    print_result("sync serial (sequential)", True, f"wall={sync_wall * 1000:.0f}ms  sum={sync_total * 1000:.0f}ms")

    start = time.perf_counter()
    await async_b.run_serial(tables)
    async_serial_wall = time.perf_counter() - start

    start = time.perf_counter()
    async_concurrent_times = await async_b.run_concurrent(tables)
    async_concurrent_wall = time.perf_counter() - start
    async_concurrent_total = sum(async_concurrent_times)
    overlap_ratio = async_concurrent_total / max(async_concurrent_wall, 0.001)

    print_result("async serial (sequential)", True, f"wall={async_serial_wall * 1000:.0f}ms")

    print_result(
        "async concurrent (gathered)",
        overlap_ratio > 1.5,
        f"wall={async_concurrent_wall * 1000:.0f}ms  overlap={overlap_ratio:.1f}x",
    )

    speedup = sync_wall / max(async_concurrent_wall, 0.001)
    print_result("speedup vs sync", speedup > 1.0, f"{speedup:.1f}x faster")
    print()


async def run_alarm_storm(async_b: AsyncBench):
    """Simulate an alarm storm: rapid queries hitting different tables."""
    print(f"{BOLD}Alarm Storm Simulation ({len(QUERIES_ALARM_STORM)} mixed queries){RESET}")
    print("-" * 60)

    sync_b = SyncBench()
    start = time.perf_counter()
    sync_b.run_concurrent(QUERIES_ALARM_STORM)
    sync_wall = time.perf_counter() - start

    start = time.perf_counter()
    async_times = await async_b.run_concurrent(QUERIES_ALARM_STORM)
    async_wall = time.perf_counter() - start

    async_total = sum(async_times)
    overlap = async_total / max(async_wall, 0.001)
    speedup = sync_wall / max(async_wall, 0.001)

    print_result("sync (sequential)", True, f"wall={sync_wall * 1000:.0f}ms")
    print_result(
        "async (gathered)",
        overlap > 1.5,
        f"wall={async_wall * 1000:.0f}ms  overlap={overlap:.1f}x  speedup={speedup:.1f}x",
    )
    print()


async def main():
    parser = argparse.ArgumentParser(description="Benchmark async vs sync Supabase client")
    parser.add_argument("--sweep", action="store_true", help="Run full benchmark sweep")
    args = parser.parse_args()

    print(f"{BOLD}═" * 40)
    print(f" Async DB Benchmark — supabase-py {settings.supabase_url or '(no URL)'}")
    print(f"{BOLD}═" * 40)

    async_b = AsyncBench()

    await run_smoke(async_b)

    if args.sweep:
        for count in [5, 10, 20, 50]:
            await run_concurrency(async_b, count)
    else:
        await run_concurrency(async_b, 5)

    await run_alarm_storm(async_b)
    await async_b.close()

    print(
        f"\n{BOLD}Done.{RESET} If async wall time is significantly lower than sync,\n"
        f"the async client is successfully overlapping queries.\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
