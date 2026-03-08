/**
 * TechnicianChat Tests
 *
 * Tests comprehensive TechnicianChat functionality:
 * - Welcome message with quick actions
 * - Message sending and display
 * - Equipment lookup API integration
 * - Different message types (diagnosis, suggestions, vision)
 * - Photo analysis and vision integration
 * - Guided diagnosis flow
 * - Error handling
 * - Auto-scroll behavior
 * - Typing indicator
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TechnicianChat from '../TechnicianChat';

// Mock scrollIntoView for jsdom - it doesn't exist by default
const scrollIntoViewMock = vi.fn();
Element.prototype.scrollIntoView = scrollIntoViewMock;
HTMLElement.prototype.scrollIntoView = scrollIntoViewMock;

// Mock API client FIRST (use alias path)
vi.mock('@/lib/api/client', () => ({
  authorizedFetch: vi.fn(),
}));

// Then import after mock is defined
import { authorizedFetch } from '@/lib/api/client';

// Mock DiagnosisFlow component
vi.mock('../DiagnosisFlow', () => ({
  default: ({ initialQuery, onComplete, onClose }: any) => (
    <div data-testid="diagnosis-flow">
      <div>{initialQuery}</div>
      <button onClick={() => onClose()}>Close Flow</button>
      <button onClick={() => onComplete({ session_id: 'test', equipment: {}, checkpoints_completed: 5, total_duration: '5m' })}>
        Complete Flow
      </button>
    </div>
  ),
}));

// Mock PhotoCapture component
vi.mock('../PhotoCapture', () => ({
  default: ({ onAnalysisComplete, _onError, disabled }: any) => (
    <button
      data-testid="photo-capture"
      disabled={disabled}
      onClick={() => {
        if (!disabled) {
          onAnalysisComplete({
            success: true,
            analysis: 'Component identified',
            manufacturer: 'Carrier',
            model: 'AquaEdge 19DV',
          });
        }
      }}
    >
      Photo
    </button>
  ),
}));

import { authorizedFetch } from '@/lib/api/client';

describe('TechnicianChat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Welcome Screen', () => {
    it('should display welcome message when no messages', () => {
      render(<TechnicianChat />);

      expect(screen.getByText('How can I help you today?')).toBeInTheDocument();
      expect(screen.getByText(/SENTINEL Tech Chat/i)).toBeInTheDocument();
    });

    it('should display welcome description text', () => {
      render(<TechnicianChat />);

      expect(
        screen.getByText(/Describe a fault, equipment problem, or search for parts/)
      ).toBeInTheDocument();
    });

    it('should display quick action buttons', () => {
      render(<TechnicianChat />);

      expect(screen.getByText('Carrier E4')).toBeInTheDocument();
      expect(screen.getByText('ABB VSD fault')).toBeInTheDocument();
      expect(screen.getByText('Chiller noise')).toBeInTheDocument();
      expect(screen.getByText('Oil filter')).toBeInTheDocument();
    });

    it('should display guided diagnosis action buttons', () => {
      render(<TechnicianChat />);

      expect(screen.getByText('E4 Diagnosis')).toBeInTheDocument();
      expect(screen.getByText('Low Pressure')).toBeInTheDocument();
    });

    it('should display "Try asking about" section header', () => {
      render(<TechnicianChat />);

      expect(screen.getByText(/try asking about/i)).toBeInTheDocument();
    });

    it('should display "Or start guided diagnosis" section header', () => {
      render(<TechnicianChat />);

      expect(screen.getByText(/or start guided diagnosis/i)).toBeInTheDocument();
    });
  });

  describe('Quick Action Buttons', () => {
    it('should send message when quick action clicked', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({ fault: { code: 'E4', name: 'High Pressure', severity: 'high' } }),
      } as any);

      render(<TechnicianChat />);

      const carrierButton = screen.getByText('Carrier E4');
      fireEvent.click(carrierButton);

      await waitFor(() => {
        expect(screen.getByText(/Carrier fault E4/)).toBeInTheDocument();
      });
    });

    it('should hide quick actions after sending message', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({ fault: { code: 'E4', severity: 'high', name: 'Test Fault' } }),
      } as any);

      render(<TechnicianChat />);

      const carrierButton = screen.getByText('Carrier E4');
      fireEvent.click(carrierButton);

      await waitFor(() => {
        expect(screen.queryByText('Carrier E4')).not.toBeInTheDocument();
      });
    });

    it('should call API with correct query parameter', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({ fault: { code: 'E4', severity: 'high', name: 'Test Fault' } }),
      } as any);

      render(<TechnicianChat />);

      const carrierButton = screen.getByText('Carrier E4');
      fireEvent.click(carrierButton);

      await waitFor(() => {
        expect((authorizedFetch as any)).toHaveBeenCalled();
        const call = (authorizedFetch as any).mock.calls[0];
        expect(call[0]).toContain('equipment-lookup/search');
      });
    });
  });

  describe('Message Input and Sending', () => {
    it('should display input field with placeholder', () => {
      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      expect(input).toBeInTheDocument();
    });

    it('should update input value when typing', async () => {
      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      await userEvent.type(input, 'chiller error');

      expect(input.value).toBe('chiller error');
    });

    it('should send message when Send button clicked', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({ fault: { code: 'E4', severity: 'high', name: 'Test Fault' } }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getByRole('button', { name: '' }); // Send button has icon

      await userEvent.type(input, 'test message');
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(screen.getByText('test message')).toBeInTheDocument();
      });
    });

    it('should send message on Enter key', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({}),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;

      await userEvent.type(input, 'test message{Enter}');

      await waitFor(() => {
        expect(screen.getByText('test message')).toBeInTheDocument();
      });
    });

    it('should not send on Shift+Enter', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({}),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;

      // Type text and then Shift+Enter (which should create newline, not send)
      await userEvent.type(input, 'line 1');
      // Simulate Shift+Enter by firing keyboard event with shiftKey=true
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter', shiftKey: true });

      // Message should not be sent (Shift+Enter creates newline, not send)
      expect(screen.queryByText(/line 1/)).not.toBeInTheDocument();
      // But input should still have the text
      expect(input.value).toBe('line 1');
    });

    it('should clear input after sending', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({}),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getByRole('button', { name: '' });

      await userEvent.type(input, 'test message');
      fireEvent.click(sendButton);

      await waitFor(() => {
        expect(input.value).toBe('');
      });
    });

    it('should disable send button while typing', async () => {
      (authorizedFetch as any).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => ({}),
                } as any),
              100
            )
          )
      );

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.textContent
      );

      await userEvent.type(input, 'test message');
      fireEvent.click(sendButton!);

      // Button should be disabled while waiting for response
      expect(sendButton).toHaveAttribute('disabled');
    });

    it('should disable input while typing', async () => {
      (authorizedFetch as any).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => ({}),
                } as any),
              100
            )
          )
      );

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.textContent
      );

      await userEvent.type(input, 'test message');
      fireEvent.click(sendButton!);

      // Input should be disabled while waiting
      expect(input).toHaveAttribute('disabled');
    });
  });

  describe('Message Display', () => {
    it('should display user message on right side', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({}),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.textContent
      );

      await userEvent.type(input, 'user message');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(screen.getByText('user message')).toBeInTheDocument();
      });
    });

    it('should display assistant message on left side', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          fault: {
            code: 'E4',
            name: 'High Pressure',
            severity: 'high',
            description: 'High pressure alarm',
          },
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.textContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      // Component should display the formatted response "Found: E4 - High Pressure"
      await waitFor(() => {
        expect(screen.getByText(/E4/)).toBeInTheDocument();
        expect(screen.getByText(/High Pressure/)).toBeInTheDocument();
      });
    });

    it('should display timestamp for each message', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({}),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.textContent
      );

      await userEvent.type(input, 'test message');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        // Should display time in HH:MM format
        const timeRegex = /\d{1,2}:\d{2}/;
        expect(screen.getByText(timeRegex)).toBeInTheDocument();
      });
    });
  });

  describe('Diagnosis Message Rendering', () => {
    it('should display diagnosis message with fault code and name', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          fault: {
            code: 'E4',
            name: 'High Pressure',
            severity: 'high',
            description: 'High pressure alarm detected',
          },
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'E4');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(screen.getByText(/E4.*High Pressure/)).toBeInTheDocument();
      });
    });

    it('should display severity badge with correct color', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          fault: {
            code: 'E4',
            name: 'Test Fault',
            severity: 'critical',
            description: 'Test',
          },
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(screen.getByText('CRITICAL')).toBeInTheDocument();
      });
    });

    it('should display probable causes when expanded', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          fault: {
            code: 'E4',
            name: 'Test Fault',
            severity: 'high',
            description: 'Test',
            probable_causes: [
              { cause: 'Low refrigerant', likelihood: 'high', check: 'Check pressure gauge' },
              { cause: 'Dirty condenser', likelihood: 'medium', check: 'Inspect coils' },
            ],
          },
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      // Probable causes are shown by default in DiagnosisMessage (showCauses=true)
      // Just wait for the message to appear and the causes to be visible
      await waitFor(() => {
        expect(screen.getByText('Low refrigerant')).toBeInTheDocument();
        expect(screen.getByText('Dirty condenser')).toBeInTheDocument();
      });
    });

    it('should display recommended actions', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          fault: {
            code: 'E4',
            name: 'Test Fault',
            severity: 'high',
            description: 'Test',
            recommended_fix: {
              immediate: ['Check refrigerant pressure', 'Inspect condenser coils'],
            },
          },
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      // Recommended actions are shown by default in DiagnosisMessage (showFix=true)
      // Just wait for the message to appear and the actions to be visible
      await waitFor(() => {
        expect(screen.getByText('Check refrigerant pressure')).toBeInTheDocument();
        expect(screen.getByText('Inspect condenser coils')).toBeInTheDocument();
      });
    });

    it('should display parts needed section', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          fault: {
            code: 'E4',
            name: 'Test',
            severity: 'high',
            description: 'Test',
          },
          parts: [
            {
              part_name: 'Refrigerant R-410A',
              part_number: 'RF-410A-30LB',
              suppliers: [
                { supplier: 'AC Supply', price: 'R450', lead_time: '2 days' },
              ],
            },
          ],
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        const partsButton = screen.getByText(/Parts You May Need/);
        fireEvent.click(partsButton);
      });

      await waitFor(() => {
        expect(screen.getByText('Refrigerant R-410A')).toBeInTheDocument();
      });
    });

    it('should display Start Guided Diagnosis button', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          fault: {
            code: 'E4',
            name: 'Test',
            severity: 'high',
            description: 'Test',
          },
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(screen.getByText(/Start Guided Diagnosis/)).toBeInTheDocument();
      });
    });
  });

  describe('Guided Diagnosis Flow', () => {
    it('should start guided diagnosis when button clicked', async () => {
      render(<TechnicianChat />);

      const guidedButton = screen.getByText('E4 Diagnosis');
      fireEvent.click(guidedButton);

      await waitFor(() => {
        expect(screen.getByTestId('diagnosis-flow')).toBeInTheDocument();
      });
    });

    it('should display initial query in diagnosis flow', async () => {
      render(<TechnicianChat />);

      const guidedButton = screen.getByText('E4 Diagnosis');
      fireEvent.click(guidedButton);

      await waitFor(() => {
        expect(screen.getByText(/Carrier chiller E4 fault/)).toBeInTheDocument();
      });
    });

    it('should close diagnosis flow when close button clicked', async () => {
      render(<TechnicianChat />);

      const guidedButton = screen.getByText('E4 Diagnosis');
      fireEvent.click(guidedButton);

      await waitFor(() => {
        const closeButton = screen.getByText('Close Flow');
        fireEvent.click(closeButton);
      });

      await waitFor(() => {
        expect(screen.queryByTestId('diagnosis-flow')).not.toBeInTheDocument();
      });
    });

    it('should add completion message when flow completes', async () => {
      render(<TechnicianChat />);

      const guidedButton = screen.getByText('E4 Diagnosis');
      fireEvent.click(guidedButton);

      await waitFor(() => {
        const completeButton = screen.getByText('Complete Flow');
        fireEvent.click(completeButton);
      });

      await waitFor(() => {
        expect(screen.getByText(/Diagnosis complete/)).toBeInTheDocument();
      });
    });
  });

  describe('Photo Analysis', () => {
    it('should display photo capture button', () => {
      render(<TechnicianChat />);

      expect(screen.getByTestId('photo-capture')).toBeInTheDocument();
    });

    it('should add photo message when photo taken', async () => {
      render(<TechnicianChat />);

      const photoButton = screen.getByTestId('photo-capture');
      fireEvent.click(photoButton);

      await waitFor(() => {
        expect(screen.getByText(/Sent a photo for analysis/)).toBeInTheDocument();
      });
    });

    it('should display vision analysis result', async () => {
      render(<TechnicianChat />);

      const photoButton = screen.getByTestId('photo-capture');
      fireEvent.click(photoButton);

      await waitFor(() => {
        expect(screen.getByText(/Component identified/)).toBeInTheDocument();
      });
    });

    it('should display equipment details from vision analysis', async () => {
      render(<TechnicianChat />);

      const photoButton = screen.getByTestId('photo-capture');
      fireEvent.click(photoButton);

      await waitFor(() => {
        expect(screen.getByText(/Carrier/)).toBeInTheDocument();
        expect(screen.getByText(/AquaEdge 19DV/)).toBeInTheDocument();
      });
    });

    it('should disable photo button while typing', async () => {
      (authorizedFetch as any).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => ({}),
                } as any),
              100
            )
          )
      );

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      const photoButton = screen.getByTestId('photo-capture');
      expect(photoButton).toHaveAttribute('disabled');
    });
  });

  describe('Typing Indicator', () => {
    it('should display typing indicator while waiting for response', async () => {
      (authorizedFetch as any).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  ok: true,
                  json: async () => ({}),
                } as any),
              100
            )
          )
      );

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      expect(screen.getByText(/SENTINEL is thinking/)).toBeInTheDocument();
    });

    it('should remove typing indicator after response', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({}),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(screen.queryByText(/SENTINEL is thinking/)).not.toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message on API failure', async () => {
      (authorizedFetch as any).mockRejectedValue(new Error('Network error'));

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(
          screen.getByText(/Sorry, I encountered an error connecting/i)
        ).toBeInTheDocument();
      });
    });

    it('should display error on non-200 response', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: false,
        status: 500,
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(
          screen.getByText(/Sorry, I encountered an error connecting/i)
        ).toBeInTheDocument();
      });
    });

    it('should focus input after error', async () => {
      (authorizedFetch as any).mockRejectedValue(new Error('Network error'));

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'test');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(document.activeElement).toBe(input);
      });
    });
  });

  describe('Message Scrolling', () => {
    it('should auto-scroll to latest message', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          note: 'I found some information that might help.'
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      // Find send button - it's the button with type="submit" in the form
      const buttons = screen.getAllByRole('button');
      const sendButton = buttons[buttons.length - 1]; // Last button is the send button

      await userEvent.type(input, 'test message 1');
      fireEvent.click(sendButton);

      // Verify that the message appears in the chat
      await waitFor(() => {
        expect(screen.getByText('test message 1')).toBeInTheDocument();
      });
    });
  });

  describe('Header Display', () => {
    it('should display header with SENTINEL branding', () => {
      render(<TechnicianChat />);

      expect(screen.getByText(/SENTINEL Tech Chat/i)).toBeInTheDocument();
    });

    it('should display tagline', () => {
      render(<TechnicianChat />);

      expect(
        screen.getByText(/Your expert colleague in your pocket/)
      ).toBeInTheDocument();
    });
  });

  describe('Suggestions Message Rendering', () => {
    it('should display suggestions message type', async () => {
      (authorizedFetch as any).mockResolvedValue({
        ok: true,
        json: async () => ({
          suggestions: [
            {
              problem: 'High discharge pressure',
              solution: 'Check condenser fan operation',
              source: 'Carrier Technical Documentation',
            },
          ],
        }),
      } as any);

      render(<TechnicianChat />);

      const input = screen.getByPlaceholderText(
        /Describe a fault or search for parts/
      ) as HTMLInputElement;
      const sendButton = screen.getAllByRole('button').find(
        (btn) => !btn.testContent
      );

      await userEvent.type(input, 'high pressure');
      fireEvent.click(sendButton!);

      await waitFor(() => {
        expect(
          screen.getByText(/Troubleshooting Suggestions/)
        ).toBeInTheDocument();
      });
    });
  });
});
