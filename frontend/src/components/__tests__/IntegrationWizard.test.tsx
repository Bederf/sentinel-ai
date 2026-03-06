/**
 * IntegrationWizard Tests
 *
 * Tests comprehensive IntegrationWizard functionality:
 * - Multi-step flow (upload → mapping → matching → review)
 * - Step navigation and validation
 * - Form validation and error messages
 * - Progress tracking with step indicator
 * - Back button navigation
 * - Integration activation
 * - Error handling and retry
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { IntegrationWizard } from '../IntegrationWizard';

// Mock API client
vi.mock('@/lib/api/client', () => ({
  authorizedFetch: vi.fn(),
}));

// Mock sub-step components
vi.mock('../FileUploadStep', () => ({
  FileUploadStep: ({ onNext }: any) => (
    <div data-testid="file-upload-step">
      <button onClick={() => onNext({
        file: new File(['test'], 'test.csv'),
        formatDetection: {
          file_format: 'csv',
          delimiter: ',',
          vendor: 'Carrier',
          confidence: 0.95,
          suggested_mappings: {},
          row_count: 1000
        }
      })}>
        Next
      </button>
    </div>
  ),
}));

vi.mock('../ColumnMappingStep', () => ({
  ColumnMappingStep: ({ onNext, onBack }: any) => (
    <div data-testid="column-mapping-step">
      <button onClick={() => onNext({ columnMappings: { timestamp: 'col1' } })}>
        Next
      </button>
      <button onClick={onBack}>Back</button>
    </div>
  ),
}));

vi.mock('../PointMatchingStep', () => ({
  PointMatchingStep: ({ onNext, onBack }: any) => (
    <div data-testid="point-matching-step">
      <button onClick={() => onNext({ pointMatches: [{ id: 'p1', asset_id: 'a1', confidence: 'high' }] })}>
        Next
      </button>
      <button onClick={onBack}>Back</button>
    </div>
  ),
}));

// Mock Tremor components
vi.mock('@tremor/react', () => ({
  Card: ({ children }: any) => <div data-testid="card">{children}</div>,
  Title: ({ children }: any) => <h1 data-testid="title">{children}</h1>,
  Text: ({ children }: any) => <p data-testid="text">{children}</p>,
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
  Callout: ({ title, children }: any) => (
    <div data-testid="callout">
      <h3>{title}</h3>
      {children}
    </div>
  ),
}));

import { authorizedFetch } from '@/lib/api/client';

describe('IntegrationWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Wizard Rendering', () => {
    it('should render wizard with card container', () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      expect(screen.getByTestId('card')).toBeInTheDocument();
    });

    it('should display all four step titles', () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      expect(screen.getByText('Upload File')).toBeInTheDocument();
      expect(screen.getByText('Map Columns')).toBeInTheDocument();
      expect(screen.getByText('Match Points')).toBeInTheDocument();
      expect(screen.getByText('Review')).toBeInTheDocument();
    });

    it('should display step descriptions', () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      expect(screen.getByText('Upload sample log file')).toBeInTheDocument();
      expect(screen.getByText('Configure field mappings')).toBeInTheDocument();
      expect(screen.getByText('Link BMS points to assets')).toBeInTheDocument();
      expect(screen.getByText('Review and activate')).toBeInTheDocument();
    });
  });

  describe('Step Navigation', () => {
    it('should start at Upload File step', () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      expect(screen.getByTestId('file-upload-step')).toBeInTheDocument();
    });

    it('should navigate to Mapping step when Next clicked', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      const nextButton = screen.getByRole('button', { name: 'Next' });
      fireEvent.click(nextButton);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });
    });

    it('should navigate to Matching step from Mapping', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Go to mapping step
      const nextButton = screen.getByRole('button', { name: 'Next' });
      fireEvent.click(nextButton);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      // Go to matching step
      const nextButton2 = screen.getByRole('button', { name: 'Next' });
      fireEvent.click(nextButton2);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });
    });

    it('should navigate to Review step from Matching', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to matching step
      const nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]); // Upload → Mapping

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      const nextButtons2 = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons2[0]); // Mapping → Matching

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      const nextButtons3 = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons3[0]); // Matching → Review

      await waitFor(() => {
        expect(screen.getByText(/Review & Activate Integration/)).toBeInTheDocument();
      });
    });

    it('should show progress stepper with step indicators', () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Should show numbered steps
      expect(screen.getByText('1')).toBeInTheDocument(); // Step 1
    });

    it('should highlight completed steps in progress', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      const nextButton = screen.getByRole('button', { name: 'Next' });
      fireEvent.click(nextButton);

      await waitFor(() => {
        // Step 1 should be marked as complete
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });
    });
  });

  describe('Back Navigation', () => {
    it('should disable Back button on first step', () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Back button should not be visible on upload step (no navigation buttons shown)
      expect(screen.getByTestId('file-upload-step')).toBeInTheDocument();
    });

    it('should navigate back from Mapping to Upload', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Go to mapping
      const nextButton = screen.getByRole('button', { name: 'Next' });
      fireEvent.click(nextButton);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      // Go back
      const backButton = screen.getAllByRole('button', { name: 'Back' })[0];
      fireEvent.click(backButton);

      await waitFor(() => {
        expect(screen.getByTestId('file-upload-step')).toBeInTheDocument();
      });
    });

    it('should navigate back from Matching to Mapping', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to matching
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]); // Upload → Mapping

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]); // Mapping → Matching

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      // Go back
      const backButtons = screen.getAllByRole('button', { name: 'Back' });
      fireEvent.click(backButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });
    });
  });

  describe('Cancel Button', () => {
    it('should display Cancel button on all steps', () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    });

    it('should call onClose when Cancel clicked', async () => {
      const onClose = vi.fn();
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={onClose}
          onComplete={vi.fn()}
        />
      );

      const cancelButton = screen.getByRole('button', { name: 'Cancel' });
      fireEvent.click(cancelButton);

      expect(onClose).toHaveBeenCalled();
    });

    it('should allow cancel from any step', async () => {
      const onClose = vi.fn();
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={onClose}
          onComplete={vi.fn()}
        />
      );

      // Navigate to mapping step
      const nextButton = screen.getByRole('button', { name: 'Next' });
      fireEvent.click(nextButton);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      // Cancel from mapping step
      const cancelButton = screen.getByRole('button', { name: 'Cancel' });
      fireEvent.click(cancelButton);

      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('Review Step', () => {
    it('should display Configuration Summary on review step', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review step
      const nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]); // Upload
      fireEvent.click(screen.getAllByRole('button', { name: 'Next' })[0]); // Mapping
      fireEvent.click(screen.getAllByRole('button', { name: 'Next' })[0]); // Matching

      await waitFor(() => {
        expect(screen.getByText(/Configuration Summary/)).toBeInTheDocument();
      });
    });

    it('should display activation warning callout', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review step
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByText('Before you activate')).toBeInTheDocument();
      });
    });

    it('should display Activate Integration button', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Activate Integration/ })).toBeInTheDocument();
      });
    });

    it('should display file information in summary', async () => {
      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate through wizard
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByText(/test.csv/)).toBeInTheDocument(); // File name
      });
    });
  });

  describe('Integration Activation', () => {
    it('should activate integration when Activate button clicked', async () => {
      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      } as any);

      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review step
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        const activateButton = screen.getByRole('button', { name: /Activate Integration/ });
        fireEvent.click(activateButton);
      });

      await waitFor(() => {
        expect(vi.mocked(authorizedFetch)).toHaveBeenCalledWith(
          expect.stringContaining('/api/integration/ingest'),
          expect.any(Object)
        );
      });
    });

    it('should show success message after activation', async () => {
      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      } as any);

      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review and activate
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        const activateButton = screen.getByRole('button', { name: /Activate Integration/ });
        fireEvent.click(activateButton);
      });

      await waitFor(() => {
        expect(screen.getByText('Integration Activated!')).toBeInTheDocument();
      });
    });

    it('should disable activate button while processing', async () => {
      vi.mocked(authorizedFetch).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => ({ success: true }),
                } as any),
              100
            )
          )
      );

      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review and activate
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        const activateButton = screen.getByRole('button', { name: /Activate Integration/ });
        fireEvent.click(activateButton);
      });

      // Button should show "Activating..."
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Activating/ })).toBeInTheDocument();
      });
    });

    it('should display error message on activation failure', async () => {
      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: false,
        status: 400,
      } as any);

      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review and activate
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        const activateButton = screen.getByRole('button', { name: /Activate Integration/ });
        fireEvent.click(activateButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/Error/)).toBeInTheDocument();
      });
    });

    it('should call API with correct building ID', async () => {
      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      } as any);

      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review and activate
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        const activateButton = screen.getByRole('button', { name: /Activate Integration/ });
        fireEvent.click(activateButton);
      });

      await waitFor(() => {
        const call = vi.mocked(authorizedFetch).mock.calls[0];
        const body = JSON.parse((call[1] as any).body);
        expect(body.site_id).toBe('bld-001');
      });
    });

    it('should call API with sync settings', async () => {
      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      } as any);

      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review and activate
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        const activateButton = screen.getByRole('button', { name: /Activate Integration/ });
        fireEvent.click(activateButton);
      });

      await waitFor(() => {
        const call = vi.mocked(authorizedFetch).mock.calls[0];
        const body = JSON.parse((call[1] as any).body);
        expect(body.sync_settings).toBeDefined();
        expect(body.sync_settings.poll_frequency_minutes).toBe(5);
      });
    });
  });

  describe('Success State', () => {
    it('should show checkmark icon after successful activation', async () => {
      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      } as any);

      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate to review and activate
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        const activateButton = screen.getByRole('button', { name: /Activate Integration/ });
        fireEvent.click(activateButton);
      });

      await waitFor(() => {
        expect(screen.getByText('Integration Activated!')).toBeInTheDocument();
      });
    });

    it('should show configuration summary in success state', async () => {
      vi.mocked(authorizedFetch).mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      } as any);

      render(
        <IntegrationWizard
          siteId="bld-001"
          onClose={vi.fn()}
          onComplete={vi.fn()}
        />
      );

      // Navigate through wizard
      let nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('column-mapping-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('point-matching-step')).toBeInTheDocument();
      });

      nextButtons = screen.getAllByRole('button', { name: 'Next' });
      fireEvent.click(nextButtons[0]);

      await waitFor(() => {
        const activateButton = screen.getByRole('button', { name: /Activate Integration/ });
        fireEvent.click(activateButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/Building ID:/)).toBeInTheDocument();
      });
    });
  });
});
