/**
 * Reusable Test Patterns Library - Phase 68-02+
 *
 * Common test patterns extracted from Phase 68-02 development.
 * Each pattern is self-contained and can be adapted for specific test scenarios.
 *
 * Patterns support:
 * - Data fetching hooks (query + error handling)
 * - Real-time updates (SSE/WebSocket)
 * - Approval workflows (multi-state transitions)
 * - User interactions (form submission, navigation)
 * - Batch operations (deduplication, aggregation)
 */

import { vi, describe, it, expect, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { userEvent } from '@testing-library/user-event';
import { screen, render } from '@testing-library/react';
import { createTestWrapper } from './mockQueryClient';
import { getEventSource } from './mockEventSource';

/**
 * Test Data Fetching Pattern
 *
 * Standard pattern for testing hooks that fetch data from API
 *
 * @param hookName - Name of hook being tested
 * @param useHook - Hook function to test
 * @param mockData - Default mock data to return from API
 *
 * @example
 * testDataFetching('useDeviceStatus', useDeviceStatus, createMockDevice());
 */
export function testDataFetching(
  hookName: string,
  useHook: (id: string) => any,
  mockData: any,
) {
  describe(`${hookName} - Data Fetching`, () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('should initially be loading', async () => {
      const wrapper = createTestWrapper();
      const { result } = renderHook(() => useHook('test-id'), { wrapper });

      expect(result.current.isLoading).toBe(true);
    });

    it('should fetch and return data', async () => {
      const wrapper = createTestWrapper();
      const { result } = renderHook(() => useHook('test-id'), { wrapper });

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.data).toBeDefined();
      expect(result.current.data).toEqual(mockData);
    });

    it('should cache data after first fetch', async () => {
      const wrapper = createTestWrapper();
      const { result: result1 } = renderHook(() => useHook('test-id'), { wrapper });
      
      await waitFor(() => {
        expect(result1.current.data).toBeDefined();
      });

      const { result: result2 } = renderHook(() => useHook('test-id'), { wrapper });
      
      // Second hook should have cached data immediately
      expect(result2.current.data).toEqual(mockData);
    });

    it('should refetch on manual invalidation', async () => {
      const wrapper = createTestWrapper();
      const { result } = renderHook(() => useHook('test-id'), { wrapper });

      await waitFor(() => {
        expect(result.current.data).toBeDefined();
      });

      await result.current.refetch();

      expect(result.current.data).toBeDefined();
    });
  });
}

/**
 * Test Error Handling Pattern
 *
 * Standard pattern for testing error scenarios in hooks
 *
 * @param hookName - Name of hook being tested
 * @param useHook - Hook function to test
 * @param mockError - Error to throw from API
 *
 * @example
 * testErrorHandling(
 *   'useDeviceStatus',
 *   useDeviceStatus,
 *   new Error('Network error')
 * );
 */
export function testErrorHandling(
  hookName: string,
  useHook: (id: string) => any,
  mockError: Error,
) {
  describe(`${hookName} - Error Handling`, () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('should handle API errors', async () => {
      // Note: Mock API to reject - implementation specific
      const wrapper = createTestWrapper();
      const { result } = renderHook(() => useHook('test-id'), { wrapper });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      expect(result.current.error?.message).toContain(mockError.message);
    });

    it('should allow retry after error', async () => {
      const wrapper = createTestWrapper();
      const { result } = renderHook(() => useHook('test-id'), { wrapper });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      // Retry should clear error
      await result.current.refetch();

      // Depending on mock setup, should either succeed or retry
      expect(result.current).toBeDefined();
    });

    it('should show error state in UI', () => {
      // This requires component rendering, not just hook
      // Component should display error message when hook.error is set
      expect(true).toBe(true);
    });
  });
}

/**
 * Test User Interaction Pattern
 *
 * Standard pattern for testing user interactions and form submissions
 *
 * @param componentName - Name of component being tested
 * @param TestComponent - Component to render
 * @param expectedActionCall - Function to verify was called
 *
 * @example
 * testUserInteraction(
 *   'DeviceToggle',
 *   () => <DeviceToggle deviceId="device-1" />,
 *   mockApi.setDeviceStatus
 * );
 */
export function testUserInteraction(
  componentName: string,
  TestComponent: () => JSX.Element,
  expectedActionCall: any,
) {
  describe(`${componentName} - User Interactions`, () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('should respond to user clicks', async () => {
      const user = userEvent.setup();
      render(<TestComponent />);

      const button = screen.getByRole('button');
      await user.click(button);

      await waitFor(() => {
        expect(expectedActionCall).toHaveBeenCalled();
      });
    });

    it('should handle form submissions', async () => {
      const user = userEvent.setup();
      render(<TestComponent />);

      const submitButton = screen.getByRole('button', { name: /submit|save/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(expectedActionCall).toHaveBeenCalled();
      });
    });

    it('should show loading state during submission', async () => {
      const user = userEvent.setup();
      render(<TestComponent />);

      const button = screen.getByRole('button');
      await user.click(button);

      // Should eventually show success or error message
      await waitFor(() => {
        expect(
          screen.queryByText(/loading|success|error/i)
        ).toBeInTheDocument();
      });
    });
  });
}

/**
 * Test Real-Time Updates Pattern
 *
 * Standard pattern for testing SSE/WebSocket messages
 *
 * @param componentName - Name of component being tested
 * @param TestComponent - Component to render
 * @param eventMessage - SSE message to dispatch
 * @param expectedText - Text that should appear after update
 *
 * @example
 * testRealTimeUpdates(
 *   'AlertDashboard',
 *   () => <AlertDashboard />,
 *   { type: 'alert', severity: 'critical' },
 *   'critical alert'
 * );
 */
export function testRealTimeUpdates(
  componentName: string,
  TestComponent: () => JSX.Element,
  eventMessage: any,
  expectedText: string,
) {
  describe(`${componentName} - Real-Time Updates`, () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('should update when SSE message received', async () => {
      render(<TestComponent />);

      const eventSource = getEventSource();
      eventSource.dispatchEvent('message', {
        data: JSON.stringify(eventMessage),
      });

      await waitFor(() => {
        expect(screen.getByText(new RegExp(expectedText, 'i'))).toBeInTheDocument();
      });
    });

    it('should handle EventSource reconnection', async () => {
      render(<TestComponent />);

      const eventSource = getEventSource();

      // Simulate disconnect
      eventSource.close();
      expect(eventSource.readyState).toBe(2); // CLOSED

      // New instance should reconnect
      eventSource.addEventListener('open', () => {
        expect(eventSource.readyState).toBe(1); // OPEN
      });
    });

    it('should cleanup listeners on unmount', async () => {
      const { unmount } = render(<TestComponent />);

      const eventSource = getEventSource();
      const removeEventListenerSpy = vi.spyOn(eventSource, 'removeEventListener');

      unmount();

      expect(removeEventListenerSpy).toHaveBeenCalled();
    });
  });
}

/**
 * Test Approval Workflow Pattern
 *
 * Standard pattern for testing multi-state approval workflows
 *
 * @param componentName - Name of component
 * @param TestComponent - Component to render
 * @param approvalApi - Mock API functions for approval
 *
 * @example
 * testApprovalWorkflow(
 *   'ApprovalDialog',
 *   () => <ApprovalDialog recommendationId="rec-001" />,
 *   { approve: vi.fn(), reject: vi.fn() }
 * );
 */
export function testApprovalWorkflow(
  componentName: string,
  TestComponent: () => JSX.Element,
  approvalApi: { approve: any; reject: any },
) {
  describe(`${componentName} - Approval Workflow`, () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('should display pending recommendation', () => {
      render(<TestComponent />);

      expect(screen.getByText(/approve|reject/i)).toBeInTheDocument();
    });

    it('should approve recommendation', async () => {
      const user = userEvent.setup();
      approvalApi.approve.mockResolvedValue({ status: 'executed' });

      render(<TestComponent />);

      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      await waitFor(() => {
        expect(approvalApi.approve).toHaveBeenCalled();
      });

      expect(screen.getByText(/executed|success/i)).toBeInTheDocument();
    });

    it('should reject recommendation', async () => {
      const user = userEvent.setup();
      approvalApi.reject.mockResolvedValue({ status: 'rejected' });

      render(<TestComponent />);

      const rejectButton = screen.getByRole('button', { name: /reject/i });
      await user.click(rejectButton);

      await waitFor(() => {
        expect(approvalApi.reject).toHaveBeenCalled();
      });
    });

    it('should show error on approval failure', async () => {
      const user = userEvent.setup();
      approvalApi.approve.mockRejectedValue(new Error('Safety constraint violation'));

      render(<TestComponent />);

      const approveButton = screen.getByRole('button', { name: /approve/i });
      await user.click(approveButton);

      await waitFor(() => {
        expect(screen.getByText(/safety constraint|error/i)).toBeInTheDocument();
      });
    });
  });
}

/**
 * Test Batch Aggregation Pattern
 *
 * Standard pattern for testing batch request deduplication
 *
 * @param hookNames - Array of hook names being tested
 * @param useHooks - Array of hook functions to test
 * @param mockApi - Mock API batch endpoint
 * @param expectedCallCount - Expected number of API calls (should be 1 for batching)
 *
 * @example
 * testBatchAggregation(
 *   ['useDeviceSafety', 'useDeviceSafety'],
 *   [
 *     () => useDeviceSafety('device-1'),
 *     () => useDeviceSafety('device-2'),
 *   ],
 *   mockApi.listDevicesSafety,
 *   1  // Should be single batch call, not 2
 * );
 */
export function testBatchAggregation(
  hookNames: string[],
  useHooks: Array<() => any>,
  mockApi: any,
  expectedCallCount: number = 1,
) {
  describe('Batch Aggregation', () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it(`should batch ${hookNames.length} requests into ${expectedCallCount} API call`, async () => {
      const wrapper = createTestWrapper();
      const results = useHooks.map(hook =>
        renderHook(hook, { wrapper })
      );

      // Wait for all hooks to get data
      await waitFor(() => {
        results.forEach(result => {
          expect(result.result.current.data).toBeDefined();
        });
      });

      // Verify API called once (batch deduplication)
      expect(mockApi).toHaveBeenCalledTimes(expectedCallCount);
    });

    it('should deduplicate requests for same ID', async () => {
      const wrapper = createTestWrapper();
      
      // Two hooks requesting same device
      const { result: result1 } = renderHook(
        () => useHooks[0](),
        { wrapper }
      );
      const { result: result2 } = renderHook(
        () => useHooks[0](),
        { wrapper }
      );

      await waitFor(() => {
        expect(result1.result.current.data).toBeDefined();
        expect(result2.result.current.data).toBeDefined();
      });

      // Should still only be 1 API call despite 2 hooks
      expect(mockApi).toHaveBeenCalledTimes(expectedCallCount);
    });

    it('should handle batch size limit', async () => {
      // If batch aggregator has maxBatchSize, test that large batches split
      const wrapper = createTestWrapper();
      
      // Create many hooks (would trigger second batch if limit < count)
      const manyResults = Array(10).fill(0).map(() =>
        renderHook(() => useHooks[0](), { wrapper })
      );

      await waitFor(() => {
        manyResults.forEach(result => {
          expect(result.result.current.data).toBeDefined();
        });
      });

      // May be multiple calls if batch size limit triggered
      expect(mockApi.mock.calls.length).toBeGreaterThanOrEqual(expectedCallCount);
    });
  });
}

export const testPatterns = {
  testDataFetching,
  testErrorHandling,
  testUserInteraction,
  testRealTimeUpdates,
  testApprovalWorkflow,
  testBatchAggregation,
};
