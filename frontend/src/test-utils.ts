/**
 * Test utilities for SENTINEL BMS frontend
 * Re-exports common testing libraries with custom setup
 */

import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render as rtlRender, type RenderOptions } from '@testing-library/react';

export * from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';

/**
 * Custom render function that automatically wraps components with QueryClientProvider
 * This prevents "No QueryClient set" errors in tests
 */
export function render(
  ui: React.ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
      },
    },
  });

  function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  }

  return rtlRender(ui, { wrapper: Wrapper, ...options });
}
