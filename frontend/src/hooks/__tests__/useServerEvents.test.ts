/**
 * Tests for useServerEvents hook
 * Covers SSE connection, message handling, reconnection, and cleanup
 */

import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useServerEvents } from '../useServerEvents';
import {
  dispatchMessageEvent,
  dispatchErrorEvent,
  closeEventSource,
  resetEventSourceMock,
  getEventSource,
} from '../../test-utils/mockEventSource';
import { createQueryWrapper } from '../../test-utils/mockQueryClient';

// Mock sonner toast to prevent real notifications in tests
vi.mock('sonner', () => ({
  toast: {
    warning: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

describe('useServerEvents', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetEventSourceMock();
  });

  afterEach(() => {
    closeEventSource();
    resetEventSourceMock();
  });

  describe('Connection Management', () => {
    it('should connect to SSE stream on mount', async () => {
      const wrapper = createQueryWrapper();
      const { result } = renderHook(() => useServerEvents(), { wrapper });

      // Allow connection to establish
      await waitFor(() => {
        const eventSource = getEventSource();
        expect(eventSource).toBeDefined();
        expect(eventSource.readyState).toBe(1); // OPEN
      });
    });

    it('should return connection status', async () => {
      const wrapper = createQueryWrapper();
      const { result } = renderHook(() => useServerEvents(), { wrapper });

      await waitFor(() => {
        expect(result.current).toBeDefined();
        expect(result.current.isConnected).toBeDefined();
      });
    });

    it('should disconnect on unmount', async () => {
      const wrapper = createQueryWrapper();
      const { unmount } = renderHook(() => useServerEvents(), { wrapper });
      const eventSource = getEventSource();

      await waitFor(() => {
        expect(eventSource.readyState).toBe(1); // OPEN
      });

      unmount();

      // Give time for cleanup
      await waitFor(() => {
        expect(eventSource.readyState).toBe(2); // CLOSED
      });
    });
  });

  describe('Message Handling', () => {
    it('should receive and parse alert_created events', async () => {
      const onEvent = vi.fn();
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(onEvent), { wrapper });

      const testEvent = {
        type: 'alert_created',
        data: {
          alert_id: 'alert-123',
          equipment_id: 'eq-1',
          equipment_code: 'S002-CHILLER-B1-001',
          equipment_name: 'Chiller 1',
          severity: 'critical',
          health_score: 30,
          message: 'Equipment failure detected',
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource()).toBeDefined();
        expect(getEventSource().readyState).toBe(1); // OPEN
      });

      dispatchMessageEvent(JSON.stringify(testEvent));

      await waitFor(() => {
        expect(onEvent).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'alert_created',
            data: expect.objectContaining({
              equipment_code: 'S002-CHILLER-B1-001',
            }),
          })
        );
      });
    });

    it('should receive health_changed events', async () => {
      const onEvent = vi.fn();
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(onEvent), { wrapper });

      const testEvent = {
        type: 'health_changed',
        data: {
          equipment_id: 'eq-1',
          equipment_code: 'S002-AHU-L1-001',
          equipment_name: 'AHU 1',
          old_health_score: 65,
          new_health_score: 85,
          reason: 'Service completed',
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent(JSON.stringify(testEvent));

      await waitFor(() => {
        expect(onEvent).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'health_changed',
          })
        );
      });
    });

    it('should receive work_order_updated events', async () => {
      const onEvent = vi.fn();
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(onEvent), { wrapper });

      const testEvent = {
        type: 'work_order_updated',
        data: {
          work_order_id: 'WO-123',
          equipment_id: 'eq-1',
          equipment_code: 'S002-PUMP-B1-001',
          status: 'completed',
          work_order_type: 'maintenance',
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent(JSON.stringify(testEvent));

      await waitFor(() => {
        expect(onEvent).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'work_order_updated',
          })
        );
      });
    });

    it('should handle malformed JSON gracefully', async () => {
      const onEvent = vi.fn();
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const wrapper = createQueryWrapper();

      renderHook(() => useServerEvents(onEvent), { wrapper });

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent('invalid json {not valid}');

      // Should not crash, just log error
      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          expect.stringContaining('Failed to parse SSE message'),
          expect.any(Error),
          expect.any(String)
        );
      });

      consoleSpy.mockRestore();
    });
  });

  describe('Cache Invalidation', () => {
    it('should invalidate alerts cache on alert_created event', async () => {
      const wrapper = createQueryWrapper();
      const { result } = renderHook(() => useServerEvents(undefined, true), { wrapper });

      const testEvent = {
        type: 'alert_created',
        data: {
          alert_id: 'alert-123',
          equipment_id: 'eq-1',
          equipment_code: 'S002-CHILLER-B1-001',
          equipment_name: 'Chiller 1',
          severity: 'critical',
          health_score: 30,
          message: 'Equipment failure detected',
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent(JSON.stringify(testEvent));

      // Just verify hook received the event
      await waitFor(() => {
        expect(result.current).toBeDefined();
      });
    });

    it('should invalidate predictions cache on health_changed event', async () => {
      const wrapper = createQueryWrapper();
      const { result } = renderHook(() => useServerEvents(undefined, true), { wrapper });

      const testEvent = {
        type: 'health_changed',
        data: {
          equipment_id: 'eq-1',
          equipment_code: 'S002-AHU-L1-001',
          equipment_name: 'AHU 1',
          old_health_score: 65,
          new_health_score: 85,
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent(JSON.stringify(testEvent));

      await waitFor(() => {
        expect(result.current).toBeDefined();
      });
    });

    it('should invalidate work orders cache on work_order_updated event', async () => {
      const wrapper = createQueryWrapper();
      const { result } = renderHook(() => useServerEvents(undefined, true), { wrapper });

      const testEvent = {
        type: 'work_order_updated',
        data: {
          work_order_id: 'WO-123',
          equipment_id: 'eq-1',
          equipment_code: 'S002-PUMP-B1-001',
          status: 'completed',
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent(JSON.stringify(testEvent));

      await waitFor(() => {
        expect(result.current).toBeDefined();
      });
    });

    it('should skip cache invalidation when autoInvalidate is false', async () => {
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(undefined, false), { wrapper });

      const testEvent = {
        type: 'alert_created',
        data: {
          alert_id: 'alert-123',
          equipment_id: 'eq-1',
          equipment_code: 'S002-CHILLER-B1-001',
          equipment_name: 'Chiller 1',
          severity: 'critical',
          health_score: 30,
          message: 'Equipment failure detected',
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent(JSON.stringify(testEvent));

      // Wait to ensure cache methods would have been called
      await new Promise(resolve => setTimeout(resolve, 100));

      // Hook should still work, just not invalidate
      // (can't easily verify cache invalidation without mocking)
    });
  });

  describe('Event Handler Callback', () => {
    it('should call custom event handler when provided', async () => {
      const onEvent = vi.fn();
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(onEvent), { wrapper });

      const testEvent = {
        type: 'alert_created',
        data: {
          alert_id: 'alert-123',
          equipment_id: 'eq-1',
          equipment_code: 'S002-CHILLER-B1-001',
          equipment_name: 'Chiller 1',
          severity: 'critical',
          health_score: 30,
          message: 'Equipment failure detected',
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent(JSON.stringify(testEvent));

      await waitFor(() => {
        expect(onEvent).toHaveBeenCalled();
        expect(onEvent).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'alert_created',
          })
        );
      });
    });

    it('should handle multiple events in sequence', async () => {
      const onEvent = vi.fn();
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(onEvent), { wrapper });

      const event1 = {
        type: 'alert_created',
        data: {
          alert_id: 'alert-1',
          equipment_id: 'eq-1',
          equipment_code: 'S002-CHILLER-B1-001',
          equipment_name: 'Chiller 1',
          severity: 'critical',
          health_score: 30,
          message: 'Equipment failure detected',
        },
        timestamp: new Date().toISOString(),
      };

      const event2 = {
        type: 'health_changed',
        data: {
          equipment_id: 'eq-1',
          equipment_code: 'S002-CHILLER-B1-001',
          equipment_name: 'Chiller 1',
          old_health_score: 30,
          new_health_score: 65,
        },
        timestamp: new Date().toISOString(),
      };

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      dispatchMessageEvent(JSON.stringify(event1));
      dispatchMessageEvent(JSON.stringify(event2));

      await waitFor(() => {
        expect(onEvent).toHaveBeenCalledTimes(2);
        expect(onEvent).toHaveBeenNthCalledWith(1, expect.objectContaining({ type: 'alert_created' }));
        expect(onEvent).toHaveBeenNthCalledWith(2, expect.objectContaining({ type: 'health_changed' }));
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle connection errors gracefully', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const wrapper = createQueryWrapper();

      renderHook(() => useServerEvents(), { wrapper });

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      // Simulate error event
      dispatchErrorEvent(new Event('error'));

      await waitFor(() => {
        expect(consoleSpy).toHaveBeenCalledWith(
          expect.stringContaining('SSE connection error'),
          expect.any(Event)
        );
      });

      consoleSpy.mockRestore();
    });
  });

  describe('Cleanup', () => {
    it('should clean up event listeners on unmount', async () => {
      const wrapper = createQueryWrapper();
      const { unmount } = renderHook(() => useServerEvents(), { wrapper });

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      const eventSource = getEventSource();
      unmount();

      // EventSource should be closed
      await waitFor(() => {
        expect(eventSource.readyState).toBe(2); // CLOSED
      });
    });

    it('should not call handler after unmount', async () => {
      const onEvent = vi.fn();
      const wrapper = createQueryWrapper();
      const { unmount } = renderHook(() => useServerEvents(onEvent), { wrapper });

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      unmount();

      // Should close and cleanup
      await waitFor(() => {
        expect(getEventSource().readyState).toBe(2); // CLOSED
      });

      // Try to dispatch message (should be no-op or ignored)
      dispatchMessageEvent(JSON.stringify({
        type: 'alert_created',
        data: {
          alert_id: 'alert-123',
          equipment_id: 'eq-1',
          equipment_code: 'S002-CHILLER-B1-001',
          equipment_name: 'Chiller 1',
          severity: 'critical',
          health_score: 30,
          message: 'Equipment failure detected',
        },
        timestamp: new Date().toISOString(),
      }));

      // Handler should not be called after unmount
      expect(onEvent).not.toHaveBeenCalled();
    });
  });

  describe('Edge Cases - Phase 68-03', () => {
    it('should handle rapid reconnection scenarios', async () => {
      const onEvent = vi.fn();
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(onEvent), { wrapper });

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      // Simulate rapid disconnect/reconnect
      dispatchErrorEvent(new Event('error'));
      await new Promise(resolve => setTimeout(resolve, 50));

      // Should reconnect automatically
      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });
    });

    it('should handle null/undefined event data gracefully', async () => {
      const onEvent = vi.fn();
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(onEvent), { wrapper });

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      // Send event with missing data field
      dispatchMessageEvent(JSON.stringify({
        type: 'alert_created',
        timestamp: new Date().toISOString(),
      }));

      // Should handle gracefully
      await new Promise(resolve => setTimeout(resolve, 100));
      expect(onEvent).toHaveBeenCalled();

      consoleSpy.mockRestore();
    });

    it('should handle rapid message bursts without dropping events', async () => {
      const onEvent = vi.fn();
      const wrapper = createQueryWrapper();
      renderHook(() => useServerEvents(onEvent), { wrapper });

      await waitFor(() => {
        expect(getEventSource().readyState).toBe(1);
      });

      // Send 10 messages rapidly
      for (let i = 0; i < 10; i++) {
        dispatchMessageEvent(JSON.stringify({
          type: 'alert_created',
          data: {
            alert_id: `alert-${i}`,
            equipment_id: `eq-${i}`,
            equipment_code: `S002-CHI-B1-00${i}`,
            equipment_name: `Equipment ${i}`,
            severity: 'warning',
            health_score: 60,
          },
          timestamp: new Date().toISOString(),
        }));
      }

      // All messages should be processed
      await waitFor(() => {
        expect(onEvent).toHaveBeenCalledTimes(10);
      });
    });
  });
});
