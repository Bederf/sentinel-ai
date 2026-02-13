/**
 * Mock EventSource factory and helpers for SSE testing
 *
 * Provides controlled EventSource instances for testing real-time functionality
 * without real delays or network dependencies.
 */

/**
 * Get the currently active mock EventSource instance (if any)
 * Used for triggering events in tests
 */
export function getEventSource() {
  return (global as any).__getMockEventSourceInstance?.();
}

/**
 * Dispatch a message event to the current mock EventSource
 * @param data JSON string to send as message event
 */
export function dispatchMessageEvent(data: string) {
  const eventSource = getEventSource();
  if (eventSource) {
    eventSource.__dispatchMessage(data);
  }
}

/**
 * Dispatch an error event to the current mock EventSource
 * @param error Optional error event (defaults to generic error)
 */
export function dispatchErrorEvent(error?: Event) {
  const eventSource = getEventSource();
  if (eventSource) {
    eventSource.__dispatchError(error);
  }
}

/**
 * Close the current mock EventSource
 */
export function closeEventSource() {
  const eventSource = getEventSource();
  if (eventSource) {
    eventSource.close();
  }
}

/**
 * Reset the mock EventSource state
 * Call this in test cleanup to ensure isolation
 */
export function resetEventSourceMock() {
  // Reset is handled by vitest's cleanup
  closeEventSource();
}
