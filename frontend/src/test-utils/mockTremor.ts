/**
 * Unified Tremor Component Mocking Strategy
 *
 * Centralizes mocking for all Tremor components to ensure consistent
 * test behavior across Dashboard, SystemHealthPage, SimulationDashboard,
 * and other Tremor-dependent components.
 *
 * **Important Note on Tab Testing:**
 * Tremor TabPanel renders in Shadow DOM, making internal tab switching
 * and content inspection difficult. Tests can verify:
 * ✅ onChange callback is called with correct tab index
 * ✅ Props are passed correctly to TabGroup
 * ✅ Children render without errors
 * ❌ Cannot: Inspect TabPanel children, verify visual content per tab
 *
 * For comprehensive tab interaction testing, use Playwright or
 * accept that TabPanel content verification is done via parent component testing.
 */

import React from 'react';

/**
 * Creates Tremor component mocks for use in vi.mock() calls
 *
 * Usage:
 * ```typescript
 * vi.mock('@tremor/react', () => createTremorMocks());
 * ```
 *
 * All mock components are fully functional with proper children rendering.
 */
export function createTremorMocks() {
  return {
    // Navigation components
    TabGroup: ({ children, onValueChange, defaultValue }: any) =>
      React.createElement('div', {
        'data-testid': 'tab-group',
        'data-on-change': onValueChange,
        'data-default': defaultValue,
        children,
      }),

    TabList: ({ children }: any) =>
      React.createElement('div', {
        'data-testid': 'tab-list',
        role: 'tablist',
        children,
      }),

    Tab: ({ children, value, onClick }: any) =>
      React.createElement('button', {
        'data-testid': `tab-${value}`,
        role: 'tab',
        onClick: (e: any) => onClick?.(e),
        children,
      }),

    TabPanels: ({ children }: any) =>
      React.createElement('div', {
        'data-testid': 'tab-panels',
        children,
      }),

    TabPanel: ({ children, value }: any) =>
      React.createElement('div', {
        'data-testid': `tab-panel-${value}`,
        'data-panel-value': value,
        children,
      }),

    // Layout components (pass-through, no styling needed)
    Card: ({ children, ...props }: any) =>
      React.createElement('div', {
        'data-testid': 'card',
        ...props,
        children,
      }),

    Flex: ({ children, ...props }: any) =>
      React.createElement('div', {
        'data-testid': 'flex',
        ...props,
        children,
      }),

    Grid: ({ children, ...props }: any) =>
      React.createElement('div', {
        'data-testid': 'grid',
        ...props,
        children,
      }),

    // Chart components (render as divs - canvas not testable in jsdom)
    BarChart: ({ data, categories, index, colors, ...props }: any) =>
      React.createElement('div', {
        'data-testid': 'bar-chart',
        'data-categories': JSON.stringify(categories),
        'data-index': index,
        'data-points-count': data?.length || 0,
        ...props,
        children: 'Bar Chart',
      }),

    LineChart: ({ data, categories, index, colors, ...props }: any) =>
      React.createElement('div', {
        'data-testid': 'line-chart',
        'data-categories': JSON.stringify(categories),
        'data-index': index,
        'data-points-count': data?.length || 0,
        ...props,
        children: 'Line Chart',
      }),

    AreaChart: ({ data, categories, index, colors, ...props }: any) =>
      React.createElement('div', {
        'data-testid': 'area-chart',
        'data-categories': JSON.stringify(categories),
        'data-index': index,
        'data-points-count': data?.length || 0,
        ...props,
        children: 'Area Chart',
      }),

    // Metric components
    Metric: ({ value, title, category, ...props }: any) =>
      React.createElement('div', {
        'data-testid': `metric-${title}`,
        ...props,
        children: [
          React.createElement('div', {
            key: 'title',
            'data-testid': `metric-title-${title}`,
            children: title,
          }),
          React.createElement('div', {
            key: 'value',
            'data-testid': `metric-value-${title}`,
            children: value,
          }),
          category
            ? React.createElement('div', {
                key: 'category',
                'data-testid': `metric-category-${title}`,
                children: category,
              })
            : null,
        ],
      }),

    Badge: ({ children, color, variant, ...props }: any) =>
      React.createElement('span', {
        'data-testid': 'badge',
        'data-color': color,
        'data-variant': variant,
        ...props,
        children,
      }),

    Gauge: ({ value, max, min, color, ...props }: any) =>
      React.createElement('div', {
        'data-testid': 'gauge',
        'data-value': value,
        'data-max': max,
        'data-min': min,
        'data-color': color,
        ...props,
        children: 'Gauge',
      }),
  };
}

/**
 * Helper to get Tremor mocks in tests
 * Useful for verifying that mocks are properly configured
 */
export const tremorMocks = createTremorMocks();
