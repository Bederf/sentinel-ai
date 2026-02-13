/**
 * ModuleSelector Component Tests
 *
 * Tests module selection and activation:
 * - Display list of available modules
 * - Toggle switches for module activation/deactivation
 * - API calls to activate/deactivate modules
 * - Visual feedback for module states
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ModuleSelector } from '../ModuleSelector';
import type { ModuleDefinition } from '../../../contexts/moduleRegistry';

// Mock module hooks - will be dynamically reconfigured in tests
const mockUseModules = vi.fn(() => ({
  activeModules: [],
  availableModules: [
    { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
    { module_type: 'energy', name: 'Energy', description: 'Energy management', integrates_with: [] },
    { module_type: 'security', name: 'Security', description: 'Security', integrates_with: [] },
    { module_type: 'lighting', name: 'Lighting', description: 'Lighting control', integrates_with: [] },
  ],
  siteId: 'test-site',
  activateModule: vi.fn(),
  deactivateModule: vi.fn(),
  isModuleActive: () => false,
  addRecommendation: vi.fn(),
  setSite: vi.fn(),
}));

vi.mock('../../../contexts/ModuleHooks', () => ({
  useModules: () => mockUseModules(),
}));

describe('ModuleSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseModules.mockReturnValue({
      activeModules: [],
      availableModules: [
        { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
        { module_type: 'energy', name: 'Energy', description: 'Energy management', integrates_with: [] },
        { module_type: 'security', name: 'Security', description: 'Security', integrates_with: [] },
        { module_type: 'lighting', name: 'Lighting', description: 'Lighting control', integrates_with: [] },
      ] as ModuleDefinition[],
      siteId: 'test-site',
      activateModule: vi.fn(),
      deactivateModule: vi.fn(),
      isModuleActive: () => false,
      addRecommendation: vi.fn(),
      setSite: vi.fn(),
    });
  });

  describe('Module list display', () => {
    it('should display available modules', () => {
      render(<ModuleSelector />);

      expect(screen.getByText('HVAC')).toBeInTheDocument();
      expect(screen.getByText('Energy')).toBeInTheDocument();
      expect(screen.getByText('Security')).toBeInTheDocument();
      expect(screen.getByText('Lighting')).toBeInTheDocument();
    });

    it('should display module descriptions', () => {
      render(<ModuleSelector />);

      expect(screen.getByText('HVAC control')).toBeInTheDocument();
      expect(screen.getByText('Energy management')).toBeInTheDocument();
      expect(screen.getByText('Security')).toBeInTheDocument();
    });

    it('should display toggle switches for each module', () => {
      render(<ModuleSelector />);

      const switches = screen.getAllByRole('checkbox');
      expect(switches.length).toBeGreaterThanOrEqual(4);
    });

    it('should handle empty module list gracefully', () => {
      mockUseModules.mockReturnValueOnce({
        activeModules: [],
        availableModules: [] as ModuleDefinition[],
        siteId: 'test-site',
        activateModule: vi.fn(),
        deactivateModule: vi.fn(),
        isModuleActive: () => false,
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
      });

      render(<ModuleSelector />);

      // Should not crash
      expect(screen.getByText('Available Modules')).toBeInTheDocument();
    });
  });

  describe('Module activation', () => {
    it('should call activateModule when toggling module on', async () => {
      const user = userEvent.setup();
      const mockActivate = vi.fn().mockResolvedValue(undefined);

      mockUseModules.mockReturnValueOnce({
        activeModules: [],
        availableModules: [
          { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
        ] as ModuleDefinition[],
        siteId: 'test-site',
        activateModule: mockActivate,
        deactivateModule: vi.fn(),
        isModuleActive: () => false,
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
      });

      render(<ModuleSelector />);

      const hvacSwitch = screen.getByRole('checkbox', { name: /hvac/i });
      await user.click(hvacSwitch);

      expect(mockActivate).toHaveBeenCalledWith('hvac', expect.any(Object));
    });

    it('should call deactivateModule when toggling module off', async () => {
      const user = userEvent.setup();
      const mockDeactivate = vi.fn().mockResolvedValue(undefined);

      mockUseModules.mockReturnValueOnce({
        activeModules: [
          {
            module_type: 'hvac',
            status: 'active',
            health_score: 85,
            last_telemetry: new Date().toISOString(),
          },
        ] as any,
        availableModules: [
          { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
        ] as ModuleDefinition[],
        siteId: 'test-site',
        activateModule: vi.fn(),
        deactivateModule: mockDeactivate,
        isModuleActive: (type: string) => type === 'hvac',
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
      });

      render(<ModuleSelector />);

      const hvacSwitch = screen.getByRole('checkbox', { name: /hvac/i });
      await user.click(hvacSwitch);

      expect(mockDeactivate).toHaveBeenCalledWith('hvac');
    });

    it('should handle activation errors gracefully', async () => {
      const user = userEvent.setup();
      const mockActivate = vi.fn().mockRejectedValue(new Error('Network error'));

      mockUseModules.mockReturnValueOnce({
        activeModules: [],
        availableModules: [
          { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
        ] as ModuleDefinition[],
        siteId: 'test-site',
        activateModule: mockActivate,
        deactivateModule: vi.fn(),
        isModuleActive: () => false,
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
      });

      render(<ModuleSelector />);

      const hvacSwitch = screen.getByRole('checkbox', { name: /hvac/i });

      // Should not crash when activation fails
      await user.click(hvacSwitch);

      expect(mockActivate).toHaveBeenCalled();
    });
  });

  describe('Visual feedback', () => {
    it('should show module status as active/inactive', () => {
      mockUseModules.mockReturnValueOnce({
        activeModules: [
          {
            module_type: 'hvac',
            status: 'active',
            health_score: 85,
            last_telemetry: new Date().toISOString(),
          },
        ] as any,
        availableModules: [
          { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
          { module_type: 'energy', name: 'Energy', description: 'Energy management', integrates_with: [] },
        ] as ModuleDefinition[],
        siteId: 'test-site',
        activateModule: vi.fn(),
        deactivateModule: vi.fn(),
        isModuleActive: (type: string) => type === 'hvac',
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
      });

      render(<ModuleSelector />);

      // HVAC should show as checked/active
      const hvacSwitch = screen.getByRole('checkbox', { name: /hvac/i });
      expect(hvacSwitch).toBeChecked();

      // Energy should show as unchecked/inactive
      const energySwitch = screen.getByRole('checkbox', { name: /energy/i });
      expect(energySwitch).not.toBeChecked();
    });

    it('should display health scores for active modules', () => {
      mockUseModules.mockReturnValueOnce({
        activeModules: [
          {
            module_type: 'hvac',
            status: 'active',
            health_score: 75,
            last_telemetry: new Date().toISOString(),
          },
        ] as any,
        availableModules: [
          { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
        ] as ModuleDefinition[],
        siteId: 'test-site',
        activateModule: vi.fn(),
        deactivateModule: vi.fn(),
        isModuleActive: (type: string) => type === 'hvac',
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
      });

      render(<ModuleSelector />);

      expect(screen.getByText(/75/)).toBeInTheDocument();
    });
  });

  describe('Multiple module operations', () => {
    it('should allow toggling multiple modules independently', async () => {
      const user = userEvent.setup();
      const mockActivate = vi.fn().mockResolvedValue(undefined);

      mockUseModules.mockReturnValueOnce({
        activeModules: [],
        availableModules: [
          { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
          { module_type: 'energy', name: 'Energy', description: 'Energy management', integrates_with: [] },
        ] as ModuleDefinition[],
        siteId: 'test-site',
        activateModule: mockActivate,
        deactivateModule: vi.fn(),
        isModuleActive: () => false,
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
      });

      render(<ModuleSelector />);

      const hvacSwitch = screen.getByRole('checkbox', { name: /hvac/i });
      const energySwitch = screen.getByRole('checkbox', { name: /energy/i });

      await user.click(hvacSwitch);
      await user.click(energySwitch);

      expect(mockActivate).toHaveBeenCalledTimes(2);
      expect(mockActivate).toHaveBeenNthCalledWith(1, 'hvac', expect.any(Object));
      expect(mockActivate).toHaveBeenNthCalledWith(2, 'energy', expect.any(Object));
    });
  });

  describe('Context integration', () => {
    it('should handle missing siteId gracefully', () => {
      mockUseModules.mockReturnValueOnce({
        activeModules: [],
        availableModules: [
          { module_type: 'hvac', name: 'HVAC', description: 'HVAC control', integrates_with: [] },
        ] as ModuleDefinition[],
        siteId: null as any,
        activateModule: vi.fn(),
        deactivateModule: vi.fn(),
        isModuleActive: () => false,
        addRecommendation: vi.fn(),
        setSite: vi.fn(),
      });

      // Should not crash
      render(<ModuleSelector />);

      expect(screen.getByText('HVAC')).toBeInTheDocument();
    });
  });
});
