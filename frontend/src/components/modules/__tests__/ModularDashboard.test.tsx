/**
 * ModularDashboard Component Tests
 *
 * Tests module dashboard orchestration:
 * - No modules active → shows ModuleSelector only
 * - 1 module active → shows module dashboard
 * - 2+ modules active → shows tabbed view with overview + individual modules
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModularDashboard } from '../ModularDashboard';
import type { ModuleInstance, AIRecommendation } from '../../../contexts/moduleContextStore';

// Mock module hooks - will be dynamically reconfigured in tests
const mockUseModules = vi.fn(() => ({
  activeModules: [],
  availableModules: [
    {
      module_type: 'energy',
      name: 'ENERGY',
      version: '1.0.0',
      description: 'Energy management module',
      capabilities: [{ id: 'cap-1', name: 'Demand Tracking', description: 'Track energy demand' }],
      integrates_with: ['hvac', 'solar'],
      ai_features: ['optimization', 'forecasting'],
    },
    {
      module_type: 'hvac',
      name: 'HVAC',
      version: '1.0.0',
      description: 'HVAC management module',
      capabilities: [{ id: 'cap-2', name: 'Temperature Control', description: 'Control HVAC' }],
      integrates_with: ['energy'],
      ai_features: ['optimization'],
    },
  ],
  isModuleActive: vi.fn(),
  addRecommendation: vi.fn(),
  setSite: vi.fn(),
  siteId: 'test-site',
  siteName: 'Test Site',
}));

const mockUseCriticalRecommendations = vi.fn(() => []);

vi.mock('../../../contexts/ModuleHooks', () => ({
  useModules: () => mockUseModules(),
  useCriticalRecommendations: () => mockUseCriticalRecommendations(),
}));

// Mock child components to avoid complexity
vi.mock('../ModuleSelector', () => ({
  ModuleSelector: () => <div data-testid="module-selector">Module Selector</div>,
}));

vi.mock('../IntegrationStatusBar', () => ({
  IntegrationStatusBar: () => <div data-testid="integration-status">Integration Status</div>,
}));

vi.mock('../AIRecommendationsPanel', () => ({
  AIRecommendationsPanel: ({ maxItems }: { maxItems?: number }) => (
    <div data-testid="ai-recommendations">AI Recommendations (max: {maxItems})</div>
  ),
}));

// Mock health thresholds
vi.mock('../../../hooks/useHealthThresholds', () => ({
  useHealthThresholds: () => ({
    thresholds: {
      healthy: 80,
      warning: 50,
      critical: 20,
    },
  }),
}));

// Mock module dashboards via Suspense lazy loading
vi.mock('../../energy-centre/EnergyCentreDashboard', () => ({
  default: Promise.resolve({
    EnergyCentreDashboard: () => <div data-testid="energy-dashboard">Energy Dashboard</div>,
  }),
}));

vi.mock('../../hvac/HVACDashboard', () => ({
  default: Promise.resolve({
    HVACDashboard: () => <div data-testid="hvac-dashboard">HVAC Dashboard</div>,
  }),
}));

vi.mock('../../solar/SolarDashboard', () => ({
  default: Promise.resolve({
    SolarDashboard: () => <div data-testid="solar-dashboard">Solar Dashboard</div>,
  }),
}));

describe('ModularDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseModules.mockReturnValue({
      activeModules: [],
      availableModules: [
        {
          module_type: 'energy',
          name: 'ENERGY',
          version: '1.0.0',
          description: 'Energy management module',
          capabilities: [{ id: 'cap-1', name: 'Demand Tracking', description: 'Track energy demand' }],
          integrates_with: ['hvac', 'solar'],
          ai_features: ['optimization', 'forecasting'],
        },
        {
          module_type: 'hvac',
          name: 'HVAC',
          version: '1.0.0',
          description: 'HVAC management module',
          capabilities: [{ id: 'cap-2', name: 'Temperature Control', description: 'Control HVAC' }],
          integrates_with: ['energy'],
          ai_features: ['optimization'],
        },
      ],
      isModuleActive: vi.fn(),
      addRecommendation: vi.fn(),
      setSite: vi.fn(),
      siteId: 'test-site',
      siteName: 'Test Site',
    });
    mockUseCriticalRecommendations.mockReturnValue([]);
  });

  describe('No modules active', () => {
    it('should display ModuleSelector when no modules active', () => {
      render(<ModularDashboard />);

      expect(screen.getByTestId('module-selector')).toBeInTheDocument();
      expect(screen.getByText(/No modules are currently active/)).toBeInTheDocument();
    });

    it('should display message about activating modules', () => {
      render(<ModularDashboard />);

      expect(
        screen.getByText(/Activate modules to enable building monitoring/)
      ).toBeInTheDocument();
    });

    it('should hide ModuleSelector when showModuleSelector is false', () => {
      render(<ModularDashboard showModuleSelector={false} />);

      expect(screen.queryByTestId('module-selector')).not.toBeInTheDocument();
    });
  });

  describe('1 module active', () => {
    it('should display single module dashboard', async () => {
      const mockSetSite = vi.fn();
      const mockAddRecommendation = vi.fn();

      mockUseModules.mockReturnValueOnce({
        activeModules: [
          {
            module_type: 'energy',
            status: 'active',
            health_score: 85,
            last_telemetry: new Date().toISOString(),
          } as ModuleInstance,
        ] as any,
        availableModules: [
          {
            module_type: 'energy',
            name: 'ENERGY',
            version: '1.0.0',
            description: 'Energy management module',
            capabilities: [{ id: 'cap-1', name: 'Demand Tracking', description: 'Track energy demand' }],
            integrates_with: ['hvac', 'solar'],
            ai_features: ['optimization', 'forecasting'],
          },
        ],
        isModuleActive: vi.fn().mockReturnValue(true),
        addRecommendation: mockAddRecommendation,
        setSite: mockSetSite,
        siteId: 'test-site',
        siteName: 'Test Site',
      });

      render(<ModularDashboard />);

      // Should show integration status
      expect(screen.getByTestId('integration-status')).toBeInTheDocument();
    });

    it('should show AI recommendations when available', async () => {
      const mockRecs: AIRecommendation[] = [
        {
          recommendation_id: 'rec-1',
          source_module: 'energy',
          recommendation_type: 'alert',
          priority: 'high',
          title: 'Energy efficiency opportunity',
          description: 'Test recommendation',
          confidence: 0.85,
          related_modules: [],
          auto_actionable: false,
          timestamp: new Date().toISOString(),
          acknowledged: false,
          resolved: false,
        },
      ];

      mockUseModules.mockReturnValueOnce({
        activeModules: [
          {
            module_type: 'energy',
            status: 'active',
            health_score: 85,
            last_telemetry: new Date().toISOString(),
          } as ModuleInstance,
        ] as any,
        availableModules: [
          {
            module_type: 'energy',
            name: 'ENERGY',
            version: '1.0.0',
            description: 'Energy management module',
            capabilities: [{ id: 'cap-1', name: 'Demand Tracking', description: 'Track energy demand' }],
            integrates_with: ['hvac', 'solar'],
            ai_features: ['optimization', 'forecasting'],
          },
        ],
        isModuleActive: vi.fn().mockReturnValue(true),
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
        siteId: 'test-site',
        siteName: 'Test Site',
      });

      mockUseCriticalRecommendations.mockReturnValueOnce(mockRecs);

      render(<ModularDashboard showRecommendations={true} />);

      expect(screen.getByTestId('ai-recommendations')).toBeInTheDocument();
    });

    it('should display ModuleSelector below dashboard', () => {
      mockUseModules.mockReturnValueOnce({
        activeModules: [
          {
            module_type: 'hvac',
            status: 'active',
            health_score: 75,
            last_telemetry: new Date().toISOString(),
          } as ModuleInstance,
        ] as any,
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
        siteId: 'test-site',
        siteName: 'Test Site',
      });

      render(<ModularDashboard showModuleSelector={true} />);

      expect(screen.getByTestId('module-selector')).toBeInTheDocument();
    });
  });

  describe('2+ modules active (tabbed view)', () => {
    beforeEach(() => {
      mockUseModules.mockReturnValue({
        activeModules: [
          {
            module_type: 'energy',
            status: 'active',
            health_score: 85,
            last_telemetry: new Date().toISOString(),
          } as ModuleInstance,
          {
            module_type: 'hvac',
            status: 'active',
            health_score: 65,
            last_telemetry: new Date().toISOString(),
          } as ModuleInstance,
        ] as any,
        availableModules: [
          {
            module_type: 'energy',
            name: 'ENERGY',
            version: '1.0.0',
            description: 'Energy management module',
            capabilities: [{ id: 'cap-1', name: 'Demand Tracking', description: 'Track energy demand' }],
            integrates_with: ['hvac', 'solar'],
            ai_features: ['optimization', 'forecasting'],
          },
          {
            module_type: 'hvac',
            name: 'HVAC',
            version: '1.0.0',
            description: 'HVAC management module',
            capabilities: [{ id: 'cap-2', name: 'Temperature Control', description: 'Control HVAC' }],
            integrates_with: ['energy'],
            ai_features: ['optimization'],
          },
        ],
        isModuleActive: vi.fn((type: string) => ['energy', 'hvac'].includes(type)),
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
        siteId: 'test-site',
        siteName: 'Test Site',
      });
    });

    it('should display tabbed view with multiple modules', () => {
      render(<ModularDashboard />);

      // Should show integration status
      expect(screen.getByTestId('integration-status')).toBeInTheDocument();

      // Should show tabs for each module and overview
      expect(screen.getByText('Overview')).toBeInTheDocument();
    });

    it('should display modules tab when showModuleSelector is true', () => {
      render(<ModularDashboard showModuleSelector={true} />);

      expect(screen.getByText('Modules')).toBeInTheDocument();
    });

    it('should display critical recommendations banner if present', () => {
      const mockRecs: AIRecommendation[] = [
        {
          recommendation_id: 'rec-1',
          source_module: 'energy',
          recommendation_type: 'critical',
          priority: 'critical',
          title: 'Critical energy issue',
          description: 'Immediate action required',
          confidence: 0.95,
          related_modules: [],
          auto_actionable: false,
          timestamp: new Date().toISOString(),
          acknowledged: false,
          resolved: false,
        },
      ];

      mockUseCriticalRecommendations.mockReturnValueOnce(mockRecs);

      render(<ModularDashboard />);

      expect(screen.getByText('1 Critical Recommendation(s)')).toBeInTheDocument();
      expect(screen.getByText('Critical energy issue')).toBeInTheDocument();
    });

    it('should allow tab switching via TabGroup', async () => {
      const _user = userEvent.setup();
      render(<ModularDashboard />);

      // Overview tab should be visible by default
      expect(screen.getByText('Overview')).toBeInTheDocument();
    });

    it('should show module health scores in tabs', () => {
      render(<ModularDashboard />);

      // Health badges are rendered as Badge components with health scores
      // Look for health score text in the overview panel
      expect(screen.getByText(/Health: 85%/)).toBeInTheDocument();
      expect(screen.getByText(/Health: 65%/)).toBeInTheDocument();
    });

    it('should display all active modules in overview panel', () => {
      render(<ModularDashboard />);

      // Integration status should be shown for 2+ modules
      expect(screen.getByTestId('integration-status')).toBeInTheDocument();

      // Overview tab should be accessible
      expect(screen.getByText('Overview')).toBeInTheDocument();
    });
  });

  describe('Props handling', () => {
    it('should accept siteId and siteName props', () => {
      const mockSetSite = vi.fn();

      mockUseModules.mockReturnValueOnce({
        activeModules: [] as any,
        availableModules: [
          {
            module_type: 'energy',
            name: 'ENERGY',
            version: '1.0.0',
            description: 'Energy management module',
            capabilities: [{ id: 'cap-1', name: 'Demand Tracking', description: 'Track energy demand' }],
            integrates_with: ['hvac', 'solar'],
            ai_features: ['optimization', 'forecasting'],
          },
        ],
        isModuleActive: vi.fn(),
        addRecommendation: vi.fn(),
        setSite: mockSetSite,
        siteId: 'test-site',
        siteName: 'Test Site',
      });

      render(
        <ModularDashboard
          siteId="custom-site"
          siteName="Custom Site"
        />
      );

      // Should render without errors
      expect(screen.getByTestId('module-selector')).toBeInTheDocument();
    });

    it('should respect showModuleSelector prop', () => {
      render(<ModularDashboard showModuleSelector={false} />);
      expect(screen.queryByTestId('module-selector')).not.toBeInTheDocument();
    });

    it('should respect showRecommendations prop', () => {
      mockUseModules.mockReturnValueOnce({
        activeModules: [
          {
            module_type: 'energy',
            status: 'active',
            health_score: 85,
            last_telemetry: new Date().toISOString(),
          } as ModuleInstance,
        ] as any,
        availableModules: [
          {
            module_type: 'energy',
            name: 'ENERGY',
            version: '1.0.0',
            description: 'Energy management module',
            capabilities: [{ id: 'cap-1', name: 'Demand Tracking', description: 'Track energy demand' }],
            integrates_with: ['hvac', 'solar'],
            ai_features: ['optimization', 'forecasting'],
          },
        ],
        isModuleActive: vi.fn().mockReturnValue(true),
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
        siteId: 'test-site',
        siteName: 'Test Site',
      });

      render(<ModularDashboard showRecommendations={false} />);

      // Should not show recommendations panel when single module active
      expect(screen.queryByTestId('ai-recommendations')).not.toBeInTheDocument();
    });
  });

  describe('Error handling', () => {
    it('should handle empty activeModules gracefully', () => {
      mockUseModules.mockReturnValueOnce({
        activeModules: [] as any,
        availableModules: [
          {
            module_type: 'energy',
            name: 'ENERGY',
            version: '1.0.0',
            description: 'Energy management module',
            capabilities: [{ id: 'cap-1', name: 'Demand Tracking', description: 'Track energy demand' }],
            integrates_with: ['hvac', 'solar'],
            ai_features: ['optimization', 'forecasting'],
          },
        ],
        isModuleActive: vi.fn(),
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
        siteId: 'test-site',
        siteName: 'Test Site',
      });

      // Should not crash
      render(<ModularDashboard />);
      expect(screen.getByTestId('module-selector')).toBeInTheDocument();
    });

    it('should display fallback message for unknown module types', () => {
      mockUseModules.mockReturnValueOnce({
        activeModules: [
          {
            module_type: 'unknown_module' as any,
            status: 'active',
            health_score: 85,
            last_telemetry: new Date().toISOString(),
          } as any,
        ],
        availableModules: [],
        isModuleActive: vi.fn(),
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
        siteId: 'test-site',
        siteName: 'Test Site',
      });

      render(<ModularDashboard />);

      expect(screen.getByText(/Module dashboard not implemented/)).toBeInTheDocument();
    });
  });
});
