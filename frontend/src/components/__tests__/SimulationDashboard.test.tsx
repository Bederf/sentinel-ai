/**
 * SimulationDashboard Tests
 *
 * Tests the "Coming soon" placeholder component.
 * The full simulation UI was split into DataSourceTab, AIPerformanceTab,
 * and ModelHealthTab (now on other pages).
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SimulationDashboard } from '../SimulationDashboard';

describe('SimulationDashboard', () => {
  it('should render the simulation placeholder', () => {
    render(<SimulationDashboard />);

    expect(screen.getByText('Simulation')).toBeInTheDocument();
    expect(screen.getByText('What-if scenario modelling')).toBeInTheDocument();
  });

  it('should show coming soon message', () => {
    render(<SimulationDashboard />);

    expect(screen.getByText('Coming soon')).toBeInTheDocument();
    expect(screen.getByText('What-if Scenario Modelling')).toBeInTheDocument();
  });

  it('should render description text', () => {
    render(<SimulationDashboard />);

    expect(
      screen.getByText(/Run what-if scenarios to evaluate/),
    ).toBeInTheDocument();
  });
});
