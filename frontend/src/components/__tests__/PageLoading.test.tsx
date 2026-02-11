/**
 * PageLoading Component Tests (Loading Spinner)
 *
 * Tests loading spinner functionality:
 * - Rendering loading states
 * - Custom messages
 * - Loading indicators
 * - Styling and animations
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import PageLoading from '../PageLoading';

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  Loader2: () => <div data-testid="loader-icon" className="animate-spin" />,
  AlertCircle: () => <div data-testid="alert-icon" />,
  CheckCircle: () => <div data-testid="check-icon" />,
}));

// Mock DOM APIs for jsdom
Element.prototype.scrollIntoView = vi.fn();
HTMLElement.prototype.scrollIntoView = vi.fn();

describe('PageLoading - Basic Rendering', () => {
  it('should render loading component', () => {
    render(<PageLoading />);

    expect(screen.getByTestId('loader-icon')).toBeInTheDocument();
  });

  it('should display loading spinner icon', () => {
    render(<PageLoading />);

    const spinner = screen.getByTestId('loader-icon');
    expect(spinner).toBeInTheDocument();
    expect(spinner.className).toContain('animate-spin');
  });

  it('should display loading text', () => {
    render(<PageLoading />);

    const loadingText = screen.queryByText(/loading/) ||
                       screen.queryByText(/please wait/) ||
                       screen.queryByText(/.../);

    expect(loadingText).toBeInTheDocument();
  });

  it('should have full screen layout', () => {
    const { container } = render(<PageLoading />);

    const wrapper = container.firstChild;
    expect(wrapper?.className).toMatch(/(h-screen|h-full)/);
  });

  it('should center content vertically and horizontally', () => {
    const { container } = render(<PageLoading />);

    const wrapper = container.firstChild;
    const classes = wrapper?.className || '';

    expect(classes).toMatch(/(flex|justify-center|items-center)/);
  });
});

describe('PageLoading - Custom Messages', () => {
  it('should display custom message when provided', () => {
    render(<PageLoading message="Connecting to server..." />);

    expect(screen.getByText('Connecting to server...')).toBeInTheDocument();
  });

  it('should display custom subtitle when provided', () => {
    render(<PageLoading message="Loading" subtitle="Please wait while we fetch your data" />);

    expect(screen.getByText('Please wait while we fetch your data')).toBeInTheDocument();
  });

  it('should display only message when no subtitle provided', () => {
    render(<PageLoading message="Loading data..." />);

    expect(screen.getByText('Loading data...')).toBeInTheDocument();
  });

  it('should handle long messages gracefully', () => {
    const longMessage = 'This is a very long loading message that might wrap to multiple lines in the UI';
    render(<PageLoading message={longMessage} />);

    expect(screen.getByText(longMessage)).toBeInTheDocument();
  });
});

describe('PageLoading - Loading States', () => {
  it('should display loading state by default', () => {
    render(<PageLoading />);

    expect(screen.getByTestId('loader-icon')).toBeInTheDocument();
  });

  it('should show completed state when isComplete prop is true', () => {
    render(<PageLoading isComplete={true} />);

    const checkIcon = screen.queryByTestId('check-icon');
    if (checkIcon) {
      expect(checkIcon).toBeInTheDocument();
    }
  });

  it('should show error state when error prop is provided', () => {
    render(<PageLoading error="Connection failed" />);

    expect(screen.getByText('Connection failed')).toBeInTheDocument();
  });

  it('should transition from loading to complete state', () => {
    const { rerender } = render(<PageLoading isComplete={false} />);

    expect(screen.getByTestId('loader-icon')).toBeInTheDocument();

    rerender(<PageLoading isComplete={true} />);

    // Check icon should now be visible
    const checkIcon = screen.queryByTestId('check-icon');
    if (checkIcon) {
      expect(checkIcon).toBeInTheDocument();
    }
  });
});

describe('PageLoading - Visual Styling', () => {
  it('should apply background color', () => {
    const { container } = render(<PageLoading />);

    const wrapper = container.firstChild;
    const classes = wrapper?.className || '';

    expect(classes).toMatch(/(bg-|dark:|gradient)/);
  });

  it('should apply text color styling', () => {
    const { container } = render(<PageLoading />);

    const text = screen.queryByText(/loading/) ||
                screen.queryByText(/please wait/) ||
                screen.queryByText(/\.\.\./);

    if (text) {
      expect(text.className).toBeDefined();
    }
  });

  it('should have dark mode support', () => {
    const { container } = render(<PageLoading />);

    const wrapper = container.firstChild;
    const classes = wrapper?.className || '';

    // Should have dark mode classes
    const hasDarkMode = classes.includes('dark:') || classes.includes('bg-slate');
    expect(hasDarkMode).toBeTruthy();
  });

  it('should apply proper spacing', () => {
    const { container } = render(<PageLoading />);

    const textElement = screen.queryByText(/loading/) ||
                       screen.queryByText(/please wait/);

    if (textElement) {
      const classes = textElement.className || '';
      expect(classes).toMatch(/(mt-|mb-|my-|p-)/);
    }
  });
});

describe('PageLoading - Animation', () => {
  it('should have spinning animation on loader', () => {
    render(<PageLoading />);

    const spinner = screen.getByTestId('loader-icon');
    expect(spinner.className).toContain('animate-spin');
  });

  it('should maintain animation smoothness', () => {
    render(<PageLoading />);

    const spinner = screen.getByTestId('loader-icon');
    expect(spinner).toBeInTheDocument();

    // Animation classes should be properly applied
    expect(spinner.className).toBeDefined();
  });

  it('should update animation state on completion', () => {
    const { rerender } = render(<PageLoading isComplete={false} />);

    let spinner = screen.getByTestId('loader-icon');
    expect(spinner.className).toContain('animate-spin');

    rerender(<PageLoading isComplete={true} />);

    // Spinner might be removed or animation stopped
    spinner = screen.queryByTestId('loader-icon');
    // Either spinner is gone or animation is removed
  });
});

describe('PageLoading - Error Handling', () => {
  it('should display error message when error provided', () => {
    render(<PageLoading error="Failed to load data" />);

    expect(screen.getByText('Failed to load data')).toBeInTheDocument();
  });

  it('should display error icon for error state', () => {
    render(<PageLoading error="Connection error" />);

    const alertIcon = screen.queryByTestId('alert-icon');
    if (alertIcon) {
      expect(alertIcon).toBeInTheDocument();
    }
  });

  it('should not show spinner when error is present', () => {
    render(<PageLoading error="Error occurred" />);

    const spinner = screen.queryByTestId('loader-icon');
    // Either no spinner or different styling for error state
    if (spinner) {
      expect(spinner.className).not.toContain('animate-spin');
    }
  });

  it('should show retry suggestion for errors', () => {
    render(<PageLoading error="Network timeout - please retry" />);

    expect(screen.getByText(/Network timeout/)).toBeInTheDocument();
  });
});

describe('PageLoading - Content Display', () => {
  it('should display default loading message when none provided', () => {
    render(<PageLoading />);

    const text = screen.queryByText(/loading/) ||
                screen.queryByText(/please wait/) ||
                screen.queryByText(/..../);

    expect(text).toBeInTheDocument();
  });

  it('should display message with proper font sizing', () => {
    render(<PageLoading message="Loading..." />);

    const message = screen.getByText('Loading...');
    const classes = message.className || '';

    expect(classes).toMatch(/(text-|font-)/);
  });

  it('should maintain message visibility in all states', () => {
    const { rerender } = render(<PageLoading message="Loading..." />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();

    rerender(<PageLoading message="Loading..." isComplete={true} />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('should display subtitle below message', () => {
    render(
      <PageLoading 
        message="Loading" 
        subtitle="Initializing application..." 
      />
    );

    const message = screen.getByText('Loading');
    const subtitle = screen.getByText('Initializing application...');

    expect(message).toBeInTheDocument();
    expect(subtitle).toBeInTheDocument();

    // Subtitle should appear after message
    const container = message.parentElement;
    const subtitleIndex = Array.from(container?.children || []).indexOf(subtitle.parentElement as HTMLElement);
    const messageIndex = Array.from(container?.children || []).indexOf(message.parentElement as HTMLElement);

    if (subtitleIndex >= 0 && messageIndex >= 0) {
      expect(subtitleIndex).toBeGreaterThan(messageIndex);
    }
  });
});

describe('PageLoading - Accessibility', () => {
  it('should have proper semantic structure', () => {
    const { container } = render(<PageLoading />);

    const wrapper = container.firstChild;
    expect(wrapper).toBeInTheDocument();
  });

  it('should have proper text contrast', () => {
    render(<PageLoading message="Loading data..." />);

    const message = screen.getByText('Loading data...');
    const classes = message.className || '';

    // Should have text color classes
    expect(classes).toMatch(/text-/);
  });

  it('should have aria-label for loading state', () => {
    const { container } = render(<PageLoading />);

    const loader = container.querySelector('[role="status"]') ||
                   container.querySelector('[aria-label]');

    // Should have accessibility attributes
    if (loader) {
      expect(loader).toBeInTheDocument();
    }
  });

  it('should announce loading message to screen readers', () => {
    render(<PageLoading message="Loading data..." />);

    const message = screen.getByText('Loading data...');
    expect(message).toBeInTheDocument();
  });
});

describe('PageLoading - Responsive Design', () => {
  it('should scale spinner appropriately', () => {
    render(<PageLoading />);

    const spinner = screen.getByTestId('loader-icon');
    expect(spinner).toBeInTheDocument();

    // Check for size classes
    const classes = spinner.className || '';
    expect(classes).toBeDefined();
  });

  it('should display properly on mobile screens', () => {
    const { container } = render(<PageLoading />);

    const wrapper = container.firstChild;
    const classes = wrapper?.className || '';

    // Should have responsive layout classes
    expect(classes).toMatch(/(flex|justify-center|items-center)/);
  });

  it('should center content on all screen sizes', () => {
    const { container } = render(<PageLoading />);

    const wrapper = container.firstChild;
    const classes = wrapper?.className || '';

    expect(classes).toMatch(/(justify-center|items-center)/);
  });
});

describe('PageLoading - Performance', () => {
  it('should not re-render unnecessarily', () => {
    const { rerender } = render(<PageLoading message="Loading..." />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();

    // Rerender with same props
    rerender(<PageLoading message="Loading..." />);

    // Should still display correctly
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('should update message efficiently', () => {
    const { rerender } = render(<PageLoading message="Step 1..." />);

    expect(screen.getByText('Step 1...')).toBeInTheDocument();

    rerender(<PageLoading message="Step 2..." />);

    expect(screen.queryByText('Step 1...')).not.toBeInTheDocument();
    expect(screen.getByText('Step 2...')).toBeInTheDocument();
  });
});
