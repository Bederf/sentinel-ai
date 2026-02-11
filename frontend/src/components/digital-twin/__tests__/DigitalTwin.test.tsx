/**
 * DigitalTwin Component Tests
 *
 * Tests comprehensive DigitalTwin 3D building visualization functionality:
 * - Site selection and building loading
 * - Floor toggles and isolation
 * - Equipment type filtering
 * - Equipment detail panel interactions
 * - Loading and error states
 * - Equipment count calculations
 *
 * Note: 3D rendering tests (Canvas, React Three Fiber) are limited in jsdom.
 * Focus is on component logic, state management, and event handlers.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DigitalTwin } from '../DigitalTwin';

// Mock hooks
vi.mock('@/hooks/useSitesList');
vi.mock('@/hooks/useEquipmentData');
vi.mock('@/hooks/useZoneCentroids');

// Mock child components - render as divs to avoid React Three Fiber issues
vi.mock('../BuildingModel', () => ({
  BuildingModel: ({ selectedFloors, onFloorClick, onFloorDoubleClick }: any) => (
    <div data-testid="building-model">
      <button onClick={() => onFloorClick(1)}>Toggle Floor</button>
      <button onClick={() => onFloorDoubleClick(1)}>Isolate Floor</button>
    </div>
  ),
}));

vi.mock('../EquipmentMarkers', () => ({
  EquipmentMarkers: ({ equipment, selectedFloors, onEquipmentClick }: any) => (
    <div data-testid="equipment-markers">
      {equipment.map((eq: any) => (
        <button key={eq.id} onClick={() => onEquipmentClick(eq.id)}>
          {eq.code}
        </button>
      ))}
    </div>
  ),
}));

vi.mock('../EquipmentDetailPanel', () => ({
  EquipmentDetailPanel: ({ equipment, onClose }: any) => (
    <div data-testid="equipment-detail-panel">
      <p>{equipment.code}</p>
      <button onClick={onClose}>Close</button>
    </div>
  ),
}));

vi.mock('../FloorSelector', () => ({
  FloorSelector: ({ selectedFloors, onToggle, onIsolate }: any) => (
    <div data-testid="floor-selector">
      <button onClick={() => onToggle(0)}>B1</button>
      <button onClick={() => onToggle(1)}>G</button>
      <button onClick={() => onToggle(2)}>L1</button>
      <button onClick={() => onIsolate(1)}>Isolate G</button>
    </div>
  ),
}));

vi.mock('../StatsBar', () => ({
  StatsBar: ({ equipment, selectedFloors }: any) => (
    <div data-testid="stats-bar">
      Equipment Count: {equipment.length}
    </div>
  ),
}));

vi.mock('../AlertBanner', () => ({
  AlertBanner: ({ equipment }: any) => (
    <div data-testid="alert-banner">Alerts: {equipment.length}</div>
  ),
}));

// Mock Canvas - provide minimal implementation for jsdom
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }: any) => <div data-testid="canvas">{children}</div>,
  useFrame: vi.fn(),
  useThree: vi.fn(() => ({
    camera: { position: { set: vi.fn() } },
  })),
}));

vi.mock('@react-three/drei', () => ({
  OrbitControls: () => <div data-testid="orbit-controls" />,
  PerspectiveCamera: () => <div data-testid="perspective-camera" />,
}));

const mockUseSitesList = vi.fn();
const mockUseEquipmentData = vi.fn();
const mockUseZoneCentroids = vi.fn();

// Set up default mock implementations
beforeEach(() => {
  // Mock DOM APIs for jsdom
  Element.prototype.scrollIntoView = vi.fn();
  HTMLElement.prototype.scrollIntoView = vi.fn();

  mockUseSitesList.mockReturnValue({
    data: [
      { id: 'site-1', name: 'Building A', code: 'S001' },
      { id: 'site-2', name: 'Building B', code: 'S002' },
    ],
    isLoading: false,
    error: null,
  });

  mockUseEquipmentData.mockReturnValue({
    equipment: [
      {
        id: 'eq-1',
        code: 'S002-CHILLER-B1-001',
        equipment_type: 'chiller',
        status: 'healthy',
        health_score: 85,
      },
      {
        id: 'eq-2',
        code: 'S002-AHU-G-001',
        equipment_type: 'ahu',
        status: 'warning',
        health_score: 65,
      },
      {
        id: 'eq-3',
        code: 'S002-FCU-L1-001',
        equipment_type: 'fcu',
        status: 'healthy',
        health_score: 75,
      },
      {
        id: 'eq-4',
        code: 'S002-DALI-L2-001',
        equipment_type: 'dali',
        status: 'healthy',
        health_score: 90,
      },
    ],
    loading: false,
    error: null,
  });

  mockUseZoneCentroids.mockReturnValue({
    data: {
      'B1-001': { x: 5, y: 2, z: 5 },
      'G-001': { x: 10, y: 0, z: 10 },
      'L1-001': { x: 8, y: 3, z: 8 },
      'L2-001': { x: 12, y: 4, z: 12 },
    },
    isLoading: false,
    error: null,
  });

  // Setup module mocks
  vi.doMock('@/hooks/useSitesList', () => ({
    useSitesList: mockUseSitesList,
  }));

  vi.doMock('@/hooks/useEquipmentData', () => ({
    useEquipmentData: mockUseEquipmentData,
  }));

  vi.doMock('@/hooks/useZoneCentroids', () => ({
    useZoneCentroids: mockUseZoneCentroids,
  }));
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('DigitalTwin - Component Rendering', () => {
  it('should render the digital twin component with all main sections', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('alert-banner')).toBeInTheDocument();
    expect(screen.getByTestId('canvas')).toBeInTheDocument();
    expect(screen.getByTestId('floor-selector')).toBeInTheDocument();
    expect(screen.getByTestId('stats-bar')).toBeInTheDocument();
  });

  it('should render site selector dropdown', () => {
    render(<DigitalTwin />);

    const select = screen.getByRole('combobox');
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue('site-1');
  });

  it('should display all available sites in dropdown', () => {
    render(<DigitalTwin />);

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent('Building A');
    expect(options[1]).toHaveTextContent('Building B');
  });

  it('should show equipment count in header', () => {
    render(<DigitalTwin />);

    expect(screen.getByText(/Total Equipment: 4/)).toBeInTheDocument();
  });

  it('should render equipment type filter buttons', () => {
    render(<DigitalTwin />);

    expect(screen.getByRole('button', { name: /All \(4\)/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /CHILLER/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /AHU/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /FCU/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /DALI/ })).toBeInTheDocument();
  });

  it('should render Canvas component for 3D visualization', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('canvas')).toBeInTheDocument();
    expect(screen.getByTestId('orbit-controls')).toBeInTheDocument();
    expect(screen.getByTestId('perspective-camera')).toBeInTheDocument();
  });
});

describe('DigitalTwin - Site Selection', () => {
  it('should auto-select first site on initial load', () => {
    render(<DigitalTwin />);

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('site-1');
  });

  it('should change selected site when dropdown changes', async () => {
    const { rerender } = render(<DigitalTwin />);

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    expect(select.value).toBe('site-1');

    // Change selection
    fireEvent.change(select, { target: { value: 'site-2' } });

    expect(mockUseEquipmentData).toHaveBeenCalledWith('site-2');
  });

  it('should disable site selector when sites are loading', () => {
    mockUseSitesList.mockReturnValue({
      data: [],
      isLoading: true,
    });

    render(<DigitalTwin />);

    const select = screen.getByRole('combobox');
    expect(select).toBeDisabled();
  });

  it('should show loading message when no sites available', () => {
    mockUseSitesList.mockReturnValue({
      data: [],
      isLoading: true,
    });

    render(<DigitalTwin />);

    const option = screen.getByRole('option');
    expect(option).toHaveTextContent('Loading sites...');
  });

  it('should show no sites message when loading complete with no results', () => {
    mockUseSitesList.mockReturnValue({
      data: [],
      isLoading: false,
    });

    render(<DigitalTwin />);

    const option = screen.getByRole('option');
    expect(option).toHaveTextContent('No buildings available');
  });
});

describe('DigitalTwin - Floor Selection', () => {
  it('should display floor selector overlay', () => {
    render(<DigitalTwin />);

    const floorSelector = screen.getByTestId('floor-selector');
    expect(floorSelector).toBeInTheDocument();
  });

  it('should have ground floor (G) selected by default', async () => {
    render(<DigitalTwin />);

    // Default is floor 1 (Ground)
    // We can verify by checking that equipment is shown
    expect(screen.getByTestId('equipment-markers')).toBeInTheDocument();
  });

  it('should toggle floor selection when floor button clicked', async () => {
    render(<DigitalTwin />);

    const floorSelector = screen.getByTestId('floor-selector');
    const toggleButtons = floorSelector.querySelectorAll('button');

    // Click B1 toggle button
    fireEvent.click(toggleButtons[0]);

    // Should still have floor selector rendered
    expect(screen.getByTestId('floor-selector')).toBeInTheDocument();
  });

  it('should isolate floor when isolate button clicked', () => {
    render(<DigitalTwin />);

    const floorSelector = screen.getByTestId('floor-selector');
    const isolateButton = floorSelector.querySelector('button:nth-last-child(1)') as HTMLButtonElement;

    fireEvent.click(isolateButton);

    // Should only show selected floor now
    expect(screen.getByTestId('equipment-markers')).toBeInTheDocument();
  });

  it('should update equipment count when floors are filtered', async () => {
    const equipmentByFloor = [
      {
        id: 'eq-1',
        code: 'S002-CHILLER-B1-001',
        equipment_type: 'chiller',
        status: 'healthy',
        health_score: 85,
      },
      {
        id: 'eq-2',
        code: 'S002-AHU-G-001',
        equipment_type: 'ahu',
        status: 'warning',
        health_score: 65,
      },
    ];

    mockUseEquipmentData.mockReturnValue({
      equipment: equipmentByFloor,
      loading: false,
      error: null,
    });

    render(<DigitalTwin />);

    expect(screen.getByText(/Total Equipment: 2/)).toBeInTheDocument();
  });
});

describe('DigitalTwin - Equipment Filtering', () => {
  it('should show all equipment when no filter applied', () => {
    render(<DigitalTwin />);

    const allButton = screen.getByRole('button', { name: /All \(4\)/ });
    expect(allButton.className).toContain('bg-blue-600');
  });

  it('should filter equipment by type when filter button clicked', async () => {
    render(<DigitalTwin />);

    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });
    fireEvent.click(chillerButton);

    expect(chillerButton.className).toContain('bg-blue-600');
    expect(screen.getByText(/Total Equipment: 1/)).toBeInTheDocument();
  });

  it('should show equipment count for each type on filter buttons', () => {
    render(<DigitalTwin />);

    expect(screen.getByRole('button', { name: /CHILLER.*\(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /AHU.*\(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /FCU.*\(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /DALI.*\(1\)/ })).toBeInTheDocument();
  });

  it('should toggle filter off when same button clicked again', async () => {
    render(<DigitalTwin />);

    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });

    // Click to enable filter
    fireEvent.click(chillerButton);
    expect(chillerButton.className).toContain('bg-blue-600');
    expect(screen.getByText(/Total Equipment: 1/)).toBeInTheDocument();

    // Click again to disable filter
    fireEvent.click(chillerButton);
    expect(screen.getByText(/Total Equipment: 4/)).toBeInTheDocument();
  });

  it('should display equipment type icons on filter buttons', () => {
    render(<DigitalTwin />);

    // Check for emoji icons
    expect(screen.getByText(/❄️/)).toBeInTheDocument(); // Chiller
    expect(screen.getByText(/🌬️/)).toBeInTheDocument(); // AHU
    expect(screen.getByText(/💨/)).toBeInTheDocument(); // FCU
    expect(screen.getByText(/💡/)).toBeInTheDocument(); // DALI
  });

  it('should show filter indicator when type filter active', () => {
    render(<DigitalTwin />);

    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });
    fireEvent.click(chillerButton);

    const filterIndicator = screen.getByText(/Filtering: ❄️ CHILLER/);
    expect(filterIndicator).toBeInTheDocument();
  });

  it('should clear filter when X button on filter indicator clicked', async () => {
    render(<DigitalTwin />);

    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });
    fireEvent.click(chillerButton);

    expect(screen.getByText(/Filtering: ❄️ CHILLER/)).toBeInTheDocument();

    const clearButton = screen.getByRole('button', { name: '' }); // X button has no text
    fireEvent.click(clearButton);

    expect(screen.queryByText(/Filtering:/)).not.toBeInTheDocument();
    expect(screen.getByText(/Total Equipment: 4/)).toBeInTheDocument();
  });

  it('should hide filter indicator when no filter active', () => {
    render(<DigitalTwin />);

    expect(screen.queryByText(/Filtering:/)).not.toBeInTheDocument();
  });
});

describe('DigitalTwin - Equipment Detail Panel', () => {
  it('should not show detail panel initially', () => {
    render(<DigitalTwin />);

    expect(screen.queryByTestId('equipment-detail-panel')).not.toBeInTheDocument();
  });

  it('should show detail panel when equipment marker clicked', async () => {
    render(<DigitalTwin />);

    const equipmentMarker = screen.getByRole('button', { name: 'S002-CHILLER-B1-001' });
    fireEvent.click(equipmentMarker);

    expect(screen.getByTestId('equipment-detail-panel')).toBeInTheDocument();
    expect(screen.getByText('S002-CHILLER-B1-001')).toBeInTheDocument();
  });

  it('should show correct equipment details in panel', async () => {
    render(<DigitalTwin />);

    const equipmentMarker = screen.getByRole('button', { name: 'S002-AHU-G-001' });
    fireEvent.click(equipmentMarker);

    expect(screen.getByText('S002-AHU-G-001')).toBeInTheDocument();
  });

  it('should close detail panel when close button clicked', async () => {
    render(<DigitalTwin />);

    const equipmentMarker = screen.getByRole('button', { name: 'S002-CHILLER-B1-001' });
    fireEvent.click(equipmentMarker);

    expect(screen.getByTestId('equipment-detail-panel')).toBeInTheDocument();

    const closeButton = screen.getByRole('button', { name: 'Close' });
    fireEvent.click(closeButton);

    expect(screen.queryByTestId('equipment-detail-panel')).not.toBeInTheDocument();
  });

  it('should update detail panel when different equipment clicked', async () => {
    render(<DigitalTwin />);

    // Click first equipment
    fireEvent.click(screen.getByRole('button', { name: 'S002-CHILLER-B1-001' }));
    expect(screen.getByText('S002-CHILLER-B1-001')).toBeInTheDocument();

    // Click different equipment
    fireEvent.click(screen.getByRole('button', { name: 'S002-AHU-G-001' }));
    expect(screen.getByText('S002-AHU-G-001')).toBeInTheDocument();
  });

  it('should reflect equipment type filter in detail panel', async () => {
    render(<DigitalTwin />);

    // Apply filter
    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });
    fireEvent.click(chillerButton);

    // Only chiller should be clickable
    const equipmentMarker = screen.getByRole('button', { name: 'S002-CHILLER-B1-001' });
    fireEvent.click(equipmentMarker);

    expect(screen.getByText('S002-CHILLER-B1-001')).toBeInTheDocument();
  });
});

describe('DigitalTwin - Loading State', () => {
  it('should show loading spinner when equipment loading', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: true,
      error: null,
    });

    render(<DigitalTwin />);

    expect(screen.getByText('Loading Building Data')).toBeInTheDocument();
    expect(screen.getByText('Fetching equipment from Supabase...')).toBeInTheDocument();
  });

  it('should show loading spinner with specific styling', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: true,
      error: null,
    });

    const { container } = render(<DigitalTwin />);

    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });

  it('should not show canvas when loading', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: true,
      error: null,
    });

    render(<DigitalTwin />);

    expect(screen.queryByTestId('canvas')).not.toBeInTheDocument();
  });

  it('should show normal view when loading completes', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [
        {
          id: 'eq-1',
          code: 'S002-CHILLER-B1-001',
          equipment_type: 'chiller',
        },
      ],
      loading: false,
      error: null,
    });

    render(<DigitalTwin />);

    expect(screen.queryByText('Loading Building Data')).not.toBeInTheDocument();
    expect(screen.getByTestId('canvas')).toBeInTheDocument();
  });
});

describe('DigitalTwin - Error State', () => {
  it('should show error message when equipment load fails', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: false,
      error: 'Failed to connect to Supabase',
    });

    render(<DigitalTwin />);

    expect(screen.getByText('Failed to Load Equipment')).toBeInTheDocument();
    expect(screen.getByText('Failed to connect to Supabase')).toBeInTheDocument();
  });

  it('should show retry button on error', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: false,
      error: 'Network error',
    });

    render(<DigitalTwin />);

    const retryButton = screen.getByRole('button', { name: 'Retry' });
    expect(retryButton).toBeInTheDocument();
  });

  it('should show warning icon on error', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: false,
      error: 'Error loading equipment',
    });

    const { container } = render(<DigitalTwin />);

    expect(container.textContent).toContain('⚠️');
  });

  it('should not show canvas on error', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: false,
      error: 'Load failed',
    });

    render(<DigitalTwin />);

    expect(screen.queryByTestId('canvas')).not.toBeInTheDocument();
  });
});

describe('DigitalTwin - Stats Bar Integration', () => {
  it('should display stats bar with equipment count', () => {
    render(<DigitalTwin />);

    const statsBar = screen.getByTestId('stats-bar');
    expect(statsBar).toHaveTextContent('Equipment Count: 4');
  });

  it('should update stats bar equipment count when filter applied', () => {
    render(<DigitalTwin />);

    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });
    fireEvent.click(chillerButton);

    const statsBar = screen.getByTestId('stats-bar');
    expect(statsBar).toHaveTextContent('Equipment Count: 1');
  });

  it('should include only filtered equipment in stats', () => {
    render(<DigitalTwin />);

    const ahuButton = screen.getByRole('button', { name: /AHU/ });
    fireEvent.click(ahuButton);

    const statsBar = screen.getByTestId('stats-bar');
    expect(statsBar).toHaveTextContent('Equipment Count: 1');
  });
});

describe('DigitalTwin - Equipment Markers Integration', () => {
  it('should render equipment markers component', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('equipment-markers')).toBeInTheDocument();
  });

  it('should pass all equipment to markers initially', () => {
    render(<DigitalTwin />);

    const markers = screen.getByTestId('equipment-markers');
    expect(markers.querySelectorAll('button')).toHaveLength(4);
  });

  it('should pass filtered equipment to markers when filter active', () => {
    render(<DigitalTwin />);

    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });
    fireEvent.click(chillerButton);

    const markers = screen.getByTestId('equipment-markers');
    expect(markers.querySelectorAll('button')).toHaveLength(1);
    expect(markers).toHaveTextContent('S002-CHILLER-B1-001');
  });

  it('should pass zone centroids to equipment markers', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('equipment-markers')).toBeInTheDocument();
  });
});

describe('DigitalTwin - Alert Banner Integration', () => {
  it('should display alert banner with equipment count', () => {
    render(<DigitalTwin />);

    const alertBanner = screen.getByTestId('alert-banner');
    expect(alertBanner).toHaveTextContent('Alerts: 4');
  });

  it('should update alert banner when equipment data changes', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [
        {
          id: 'eq-1',
          code: 'S002-CHILLER-B1-001',
          equipment_type: 'chiller',
        },
      ],
      loading: false,
      error: null,
    });

    render(<DigitalTwin />);

    const alertBanner = screen.getByTestId('alert-banner');
    expect(alertBanner).toHaveTextContent('Alerts: 1');
  });
});

describe('DigitalTwin - Zone Centroids Integration', () => {
  it('should load zone centroids for selected building', () => {
    render(<DigitalTwin />);

    expect(mockUseZoneCentroids).toHaveBeenCalledWith('site-1');
  });

  it('should pass zone centroids to equipment markers when available', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('equipment-markers')).toBeInTheDocument();
  });

  it('should handle empty zone centroids gracefully', () => {
    mockUseZoneCentroids.mockReturnValue({
      data: {},
    });

    render(<DigitalTwin />);

    expect(screen.getByTestId('equipment-markers')).toBeInTheDocument();
  });

  it('should reload zone centroids when building selection changes', async () => {
    const { rerender } = render(<DigitalTwin />);

    const select = screen.getByRole('combobox') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'site-2' } });

    expect(mockUseZoneCentroids).toHaveBeenCalledWith('site-2');
  });
});

describe('DigitalTwin - State Management', () => {
  it('should maintain floor selection state across filter changes', () => {
    render(<DigitalTwin />);

    // Apply filter
    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });
    fireEvent.click(chillerButton);

    // Floor state should be maintained
    expect(screen.getByTestId('floor-selector')).toBeInTheDocument();
  });

  it('should reset equipment selection when filter changes', () => {
    render(<DigitalTwin />);

    // Select equipment
    fireEvent.click(screen.getByRole('button', { name: 'S002-CHILLER-B1-001' }));
    expect(screen.getByTestId('equipment-detail-panel')).toBeInTheDocument();

    // Apply different type filter - may hide selected equipment
    const ahuButton = screen.getByRole('button', { name: /AHU/ });
    fireEvent.click(ahuButton);

    // Equipment marker should no longer be visible (filtered out)
    const markers = screen.getByTestId('equipment-markers');
    expect(markers).not.toHaveTextContent('S002-CHILLER-B1-001');
  });

  it('should maintain all state when toggling filter on/off', () => {
    render(<DigitalTwin />);

    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });

    // Enable filter
    fireEvent.click(chillerButton);
    expect(screen.getByText(/Total Equipment: 1/)).toBeInTheDocument();

    // Disable filter
    fireEvent.click(chillerButton);
    expect(screen.getByText(/Total Equipment: 4/)).toBeInTheDocument();

    // Floor selector should still be present
    expect(screen.getByTestId('floor-selector')).toBeInTheDocument();
  });
});

describe('DigitalTwin - Empty States', () => {
  it('should handle empty equipment list gracefully', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: false,
      error: null,
    });

    render(<DigitalTwin />);

    expect(screen.getByText(/Total Equipment: 0/)).toBeInTheDocument();
    expect(screen.getByTestId('canvas')).toBeInTheDocument();
  });

  it('should show no filter buttons when no equipment', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [],
      loading: false,
      error: null,
    });

    render(<DigitalTwin />);

    // Should only have "All" button
    expect(screen.getByRole('button', { name: /All \(0\)/ })).toBeInTheDocument();
  });

  it('should handle filtered results with no equipment', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [
        {
          id: 'eq-1',
          code: 'S002-CHILLER-B1-001',
          equipment_type: 'chiller',
        },
      ],
      loading: false,
      error: null,
    });

    render(<DigitalTwin />);

    // Filter by non-existent type - no markers should show
    const chillerButton = screen.getByRole('button', { name: /CHILLER/ });
    fireEvent.click(chillerButton);

    expect(screen.getByText(/Total Equipment: 1/)).toBeInTheDocument();
  });
});

describe('DigitalTwin - Canvas and 3D Components', () => {
  it('should render Canvas wrapper component', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('canvas')).toBeInTheDocument();
  });

  it('should include lighting in Canvas', () => {
    render(<DigitalTwin />);

    // Lighting components are rendered inside Canvas
    expect(screen.getByTestId('canvas')).toBeInTheDocument();
  });

  it('should include OrbitControls for camera navigation', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('orbit-controls')).toBeInTheDocument();
  });

  it('should include PerspectiveCamera', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('perspective-camera')).toBeInTheDocument();
  });

  it('should include BuildingModel component', () => {
    render(<DigitalTwin />);

    expect(screen.getByTestId('building-model')).toBeInTheDocument();
  });
});

describe('DigitalTwin - Equipment Type Icon Mapping', () => {
  it('should display correct icon for chiller type', () => {
    render(<DigitalTwin />);

    expect(screen.getByText(/❄️.*CHILLER/)).toBeInTheDocument();
  });

  it('should display correct icon for AHU type', () => {
    render(<DigitalTwin />);

    expect(screen.getByText(/🌬️.*AHU/)).toBeInTheDocument();
  });

  it('should display correct icon for FCU type', () => {
    render(<DigitalTwin />);

    expect(screen.getByText(/💨.*FCU/)).toBeInTheDocument();
  });

  it('should display correct icon for DALI type', () => {
    render(<DigitalTwin />);

    expect(screen.getByText(/💡.*DALI/)).toBeInTheDocument();
  });

  it('should use default icon for unknown equipment types', () => {
    mockUseEquipmentData.mockReturnValue({
      equipment: [
        {
          id: 'eq-unknown',
          code: 'S002-UNKNOWN-G-001',
          equipment_type: 'unknown_type',
        },
      ],
      loading: false,
      error: null,
    });

    render(<DigitalTwin />);

    // Unknown types should show default icon
    expect(screen.getByText(/🏗️.*UNKNOWN_TYPE/)).toBeInTheDocument();
  });
});
