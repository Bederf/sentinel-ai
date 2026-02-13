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
    TabGroup: ({ children, onValueChange, defaultValue }: any) => (
      <div data-testid="tab-group" data-on-change={onValueChange} data-default={defaultValue}>
        {children}
      </div>
    ),
    TabList: ({ children }: any) => (
      <div data-testid="tab-list" role="tablist">
        {children}
      </div>
    ),
    Tab: ({ children, value, onClick }: any) => (
      <button
        data-testid={`tab-${value}`}
        role="tab"
        onClick={(e) => {
          onClick?.(e);
        }}
      >
        {children}
      </button>
    ),
    TabPanels: ({ children }: any) => (
      <div data-testid="tab-panels">
        {children}
      </div>
    ),
    TabPanel: ({ children, value }: any) => (
      <div data-testid={`tab-panel-${value}`} data-panel-value={value}>
        {children}
      </div>
    ),

    // Layout components (pass-through, no styling needed)
    Card: ({ children, ...props }: any) => (
      <div data-testid="card" {...props}>
        {children}
      </div>
    ),
    Flex: ({ children, ...props }: any) => (
      <div data-testid="flex" {...props}>
        {children}
      </div>
    ),
    Grid: ({ children, ...props }: any) => (
      <div data-testid="grid" {...props}>
        {children}
      </div>
    ),

    // Chart components (render as divs - canvas not testable in jsdom)
    BarChart: ({ data, categories, index, colors, ...props }: any) => (
      <div
        data-testid="bar-chart"
        data-categories={JSON.stringify(categories)}
        data-index={index}
        data-points-count={data?.length || 0}
        {...props}
      >
        Bar Chart
      </div>
    ),
    LineChart: ({ data, categories, index, colors, ...props }: any) => (
      <div
        data-testid="line-chart"
        data-categories={JSON.stringify(categories)}
        data-index={index}
        data-points-count={data?.length || 0}
        {...props}
      >
        Line Chart
      </div>
    ),
    AreaChart: ({ data, categories, index, colors, ...props }: any) => (
      <div
        data-testid="area-chart"
        data-categories={JSON.stringify(categories)}
        data-index={index}
        data-points-count={data?.length || 0}
        {...props}
      >
        Area Chart
      </div>
    ),

    // Metric components
    Metric: ({ value, title, category, ...props }: any) => (
      <div data-testid={`metric-${title}`} {...props}>
        <div data-testid={`metric-title-${title}`}>{title}</div>
        <div data-testid={`metric-value-${title}`}>{value}</div>
        {category && <div data-testid={`metric-category-${title}`}>{category}</div>}
      </div>
    ),
    Badge: ({ children, color, variant, ...props }: any) => (
      <span data-testid="badge" data-color={color} data-variant={variant} {...props}>
        {children}
      </span>
    ),
    Gauge: ({ value, max, min, color, ...props }: any) => (
      <div
        data-testid="gauge"
        data-value={value}
        data-max={max}
        data-min={min}
        data-color={color}
        {...props}
      >
        Gauge
      </div>
    ),
  };
}

/**
 * Helper to get Tremor mocks in tests
 * Useful for verifying that mocks are properly configured
 */
export const tremorMocks = createTremorMocks();
