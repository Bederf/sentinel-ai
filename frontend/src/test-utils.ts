/**
 * Test utilities for SENTINEL BMS frontend
 * Re-exports common testing libraries with custom setup
 */

import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render as rtlRender, type RenderOptions } from '@testing-library/react';
import type { ModuleContextValue } from './contexts/moduleContextStore';

export * from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  moduleContext?: ModuleContextValue;
}

/**
 * Custom render function that automatically wraps components with QueryClientProvider
 * Optionally wraps with ModuleProvider if moduleContext is provided
 * This prevents "No QueryClient set" and "Cannot read property of undefined" errors in tests
 */
export function render(
  ui: React.ReactElement,
  options?: CustomRenderOptions
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
      },
    },
  });

  const { moduleContext, ...rtlOptions } = options || {};

  function Wrapper({ children }: { children: React.ReactNode }) {
    let content = children;

    // Wrap with ModuleProvider if moduleContext is provided
    if (moduleContext) {
      const { ModuleProvider } = require('./contexts/ModuleContext');
      // Create a mock provider that injects the moduleContext
      content = React.createElement(
        { Provider: ModuleProvider },
        {
          initialSiteId: moduleContext.siteId,
          initialSiteName: moduleContext.siteName,
        },
        children
      );
    }

    return React.createElement(QueryClientProvider, { client: queryClient }, content);
  }

  return rtlRender(ui, { wrapper: Wrapper, ...rtlOptions });
}
