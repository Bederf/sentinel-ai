/**
 * Test Results API Client
 *
 * Fetches test results from the backend API.
 */

import { authorizedFetch } from './client';
import type { TimelineEvent } from '@/components/cd/Timeline';

export interface TestRun {
  runId: string;
  timestamp: string;
  type: 'unit' | 'integration' | 'load' | 'performance';
  status: 'passed' | 'failed' | 'running';
  summary: {
    total: number;
    passed: number;
    failed: number;
    skipped: number;
    duration: string;
  };
  timeline: TimelineEvent[];
}

export interface TestResultsResponse {
  runs: TestRun[];
  totalRuns: number;
  lastUpdated: string;
}

/**
 * Fetch all test results
 */
export async function getTestResults(): Promise<TestResultsResponse> {
  const response = await authorizedFetch('/api/test-results');

  if (!response.ok) {
    throw new Error(`Failed to fetch test results: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch specific test run by ID
 */
export async function getTestRun(runId: string): Promise<TestRun> {
  const response = await authorizedFetch(`/api/test-results/${runId}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch test run: ${response.statusText}`);
  }

  return response.json();
}

/**
 * React hook for fetching test results
 */
import { useState, useEffect } from 'react';

export function useTestResults(autoRefreshMs?: number) {
  const [data, setData] = useState<TestResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const results = await getTestResults();
      setData(results);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();

    if (autoRefreshMs && autoRefreshMs > 0) {
      const interval = setInterval(fetchData, autoRefreshMs);
      return () => clearInterval(interval);
    }
  }, [autoRefreshMs]);

  return { data, loading, error, refetch: fetchData };
}

export default {
  getTestResults,
  getTestRun,
  useTestResults,
};
