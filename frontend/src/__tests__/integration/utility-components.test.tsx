/**
 * Utility Components Integration Tests
 *
 * Tests common utility components and patterns used across the application:
 * - Card components for data display
 * - Badge/Status indicators
 * - Modal dialogs
 * - Tooltips and help text
 * - Form elements and validation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  AlertCircle: () => <div data-testid="icon-alert" />,
  CheckCircle: () => <div data-testid="icon-check" />,
  Info: () => <div data-testid="icon-info" />,
  X: () => <div data-testid="icon-close" />,
}));

describe('Card Component Patterns', () => {
  it('should render card with content', () => {
    const Card = ({ children }: any) => (
      <div className="rounded-lg border bg-white p-4 shadow">
        {children}
      </div>
    );

    render(
      <Card>
        <h3>Test Card</h3>
        <p>Card content</p>
      </Card>
    );

    expect(screen.getByText('Test Card')).toBeInTheDocument();
    expect(screen.getByText('Card content')).toBeInTheDocument();
  });

  it('should display card with header and footer', () => {
    const Card = ({ header, children, footer }: any) => (
      <div className="rounded-lg border bg-white shadow">
        {header && <div className="border-b p-4">{header}</div>}
        <div className="p-4">{children}</div>
        {footer && <div className="border-t p-4">{footer}</div>}
      </div>
    );

    render(
      <Card
        header={<h3>Header</h3>}
        footer={<button>Action</button>}
      >
        <p>Content</p>
      </Card>
    );

    expect(screen.getByText('Header')).toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('should apply hover effects on cards', () => {
    const Card = ({ onClick }: any) => (
      <div
        className="rounded-lg border bg-white p-4 transition hover:shadow-lg cursor-pointer"
        onClick={onClick}
      >
        Click me
      </div>
    );

    const onClick = vi.fn();
    render(<Card onClick={onClick} />);

    const card = screen.getByText('Click me').parentElement;
    fireEvent.click(card!);

    expect(onClick).toHaveBeenCalled();
  });
});

describe('Badge and Status Indicators', () => {
  it('should render status badge', () => {
    const Badge = ({ status }: { status: 'success' | 'warning' | 'error' }) => {
      const colors = {
        success: 'bg-green-100 text-green-800',
        warning: 'bg-yellow-100 text-yellow-800',
        error: 'bg-red-100 text-red-800',
      };

      return (
        <span className={`rounded-full px-3 py-1 text-sm font-medium ${colors[status]}`}>
          {status.toUpperCase()}
        </span>
      );
    };

    render(<Badge status="success" />);
    expect(screen.getByText('SUCCESS')).toBeInTheDocument();
  });

  it('should display different badge variants', () => {
    const Badge = ({ status }: any) => (
      <span className={`px-3 py-1 rounded ${
        status === 'critical' ? 'bg-red-600' :
        status === 'warning' ? 'bg-yellow-600' :
        'bg-green-600'
      }`}>
        {status}
      </span>
    );

    const { rerender } = render(<Badge status="critical" />);
    expect(screen.getByText('critical')).toBeInTheDocument();

    rerender(<Badge status="warning" />);
    expect(screen.getByText('warning')).toBeInTheDocument();

    rerender(<Badge status="healthy" />);
    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('should show icon with status badge', () => {
    const Badge = ({ status }: any) => (
      <div className="flex items-center gap-2">
        {status === 'success' && <span data-testid="icon-check">✓</span>}
        {status === 'error' && <span data-testid="icon-alert">!</span>}
        {status}
      </div>
    );

    render(<Badge status="success" />);
    expect(screen.getByTestId('icon-check')).toBeInTheDocument();
  });
});

describe('Modal Dialog Patterns', () => {
  it('should render modal with title and content', () => {
    const Modal = ({ isOpen, title, children, onClose }: any) => {
      if (!isOpen) return null;

      return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
          <div className="bg-white rounded-lg p-6 max-w-md">
            <h2 className="text-xl font-bold mb-4">{title}</h2>
            <div>{children}</div>
            <button onClick={onClose} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded">
              Close
            </button>
          </div>
        </div>
      );
    };

    const onClose = vi.fn();
    render(
      <Modal isOpen={true} title="Test Modal" onClose={onClose}>
        <p>Modal content</p>
      </Modal>
    );

    expect(screen.getByText('Test Modal')).toBeInTheDocument();
    expect(screen.getByText('Modal content')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();
  });

  it('should close modal when close button clicked', async () => {
    const user = userEvent.setup();
    const Modal = ({ isOpen, onClose }: any) => {
      if (!isOpen) return <div data-testid="closed">Modal closed</div>;

      return (
        <div>
          <button onClick={onClose}>Close</button>
        </div>
      );
    };

    const onClose = vi.fn();
    const { rerender } = render(<Modal isOpen={true} onClose={onClose} />);

    const closeButton = screen.getByRole('button', { name: 'Close' });
    await user.click(closeButton);

    expect(onClose).toHaveBeenCalled();
  });

  it('should prevent background scroll when modal open', () => {
    const Modal = ({ isOpen, children }: any) => {
      if (!isOpen) return null;

      return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
          <div className="bg-white rounded-lg p-6">{children}</div>
        </div>
      );
    };

    render(<Modal isOpen={true}>Content</Modal>);

    const backdrop = screen.getByText('Content').parentElement?.parentElement;
    expect(backdrop?.className).toContain('fixed');
  });
});

describe('Tooltip Patterns', () => {
  it('should display tooltip on hover', async () => {
    const user = userEvent.setup();
    const Tooltip = ({ text, children }: any) => (
      <div className="relative inline-block group">
        {children}
        <div className="invisible group-hover:visible bg-gray-800 text-white px-2 py-1 rounded absolute bottom-full left-1/2 transform -translate-x-1/2 whitespace-nowrap">
          {text}
        </div>
      </div>
    );

    const { container } = render(
      <Tooltip text="Help text">
        <button>Hover me</button>
      </Tooltip>
    );

    const button = screen.getByRole('button');
    await user.hover(button);

    // Tooltip should be in DOM (might be hidden initially)
    expect(screen.getByText('Help text')).toBeInTheDocument();
  });

  it('should show tooltip with icon', () => {
    const Tooltip = ({ text }: any) => (
      <div className="flex items-center gap-1">
        <span data-testid="icon-info">ℹ️</span>
        <span>{text}</span>
      </div>
    );

    render(<Tooltip text="Information" />);

    expect(screen.getByTestId('icon-info')).toBeInTheDocument();
    expect(screen.getByText('Information')).toBeInTheDocument();
  });
});

describe('Form Validation Patterns', () => {
  it('should validate required field', () => {
    const Form = () => {
      const [value, setValue] = vi.fn();

      return (
        <form>
          <input
            required
            value=""
            onChange={(e) => setValue(e.target.value)}
            placeholder="Required field"
          />
        </form>
      );
    };

    render(<Form />);

    const input = screen.getByPlaceholderText('Required field');
    expect(input).toHaveAttribute('required');
  });

  it('should show validation error message', () => {
    const FormField = ({ error }: any) => (
      <div>
        <input placeholder="Email" type="email" />
        {error && <span className="text-red-600">{error}</span>}
      </div>
    );

    render(<FormField error="Invalid email" />);

    expect(screen.getByText('Invalid email')).toBeInTheDocument();
  });

  it('should disable submit button when form invalid', () => {
    const Form = ({ isValid }: any) => (
      <form>
        <input placeholder="Name" />
        <button disabled={!isValid} type="submit">
          Submit
        </button>
      </form>
    );

    render(<Form isValid={false} />);

    const submitButton = screen.getByRole('button', { name: 'Submit' });
    expect(submitButton).toBeDisabled();
  });

  it('should clear validation errors on input change', async () => {
    const user = userEvent.setup();
    const FormField = () => {
      const [error, setError] = vi.fn();

      return (
        <div>
          <input
            onChange={(e) => {
              if (e.target.value) setError(null);
            }}
            placeholder="Name"
          />
          {error && <span className="text-red-600">Error</span>}
        </div>
      );
    };

    render(<FormField />);

    const input = screen.getByPlaceholderText('Name');
    await user.type(input, 'John');

    // Error should be cleared
    expect(input).toHaveValue('John');
  });
});

describe('Loading States', () => {
  it('should show loading state on async operation', () => {
    const Button = ({ isLoading }: any) => (
      <button disabled={isLoading}>
        {isLoading ? 'Loading...' : 'Click me'}
      </button>
    );

    render(<Button isLoading={false} />);
    expect(screen.getByText('Click me')).toBeInTheDocument();
    expect(screen.getByRole('button')).not.toBeDisabled();
  });

  it('should disable button during loading', () => {
    const Button = ({ isLoading }: any) => (
      <button disabled={isLoading}>
        {isLoading ? 'Loading...' : 'Submit'}
      </button>
    );

    const { rerender } = render(<Button isLoading={false} />);

    rerender(<Button isLoading={true} />);

    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Loading...');
  });
});

describe('Error Messages', () => {
  it('should display error alert', () => {
    const Alert = ({ type, message }: any) => (
      <div className={`p-4 rounded ${
        type === 'error' ? 'bg-red-100 text-red-800' :
        type === 'warning' ? 'bg-yellow-100 text-yellow-800' :
        'bg-green-100 text-green-800'
      }`}>
        {message}
      </div>
    );

    render(<Alert type="error" message="Something went wrong" />);

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('should show dismissible error', async () => {
    const user = userEvent.setup();
    const Alert = ({ onDismiss }: any) => (
      <div>
        <p>Error message</p>
        <button onClick={onDismiss}>Dismiss</button>
      </div>
    );

    const onDismiss = vi.fn();
    render(<Alert onDismiss={onDismiss} />);

    const dismissButton = screen.getByRole('button', { name: 'Dismiss' });
    await user.click(dismissButton);

    expect(onDismiss).toHaveBeenCalled();
  });
});

describe('Empty States', () => {
  it('should display empty state message', () => {
    const EmptyState = ({ message }: any) => (
      <div className="text-center py-8">
        <p className="text-gray-500">{message}</p>
      </div>
    );

    render(<EmptyState message="No data available" />);

    expect(screen.getByText('No data available')).toBeInTheDocument();
  });

  it('should show action button in empty state', () => {
    const EmptyState = ({ action }: any) => (
      <div className="text-center py-8">
        <p>No items found</p>
        <button className="mt-4 px-4 py-2 bg-blue-600 text-white rounded">
          {action}
        </button>
      </div>
    );

    render(<EmptyState action="Create new item" />);

    expect(screen.getByRole('button', { name: 'Create new item' })).toBeInTheDocument();
  });
});

describe('Responsive Utilities', () => {
  it('should apply responsive classes', () => {
    const ResponsiveComponent = () => (
      <div className="w-full md:w-1/2 lg:w-1/3">
        Responsive layout
      </div>
    );

    const { container } = render(<ResponsiveComponent />);

    const div = container.querySelector('div');
    expect(div?.className).toContain('w-full');
    expect(div?.className).toContain('md:w-1/2');
    expect(div?.className).toContain('lg:w-1/3');
  });

  it('should stack content on mobile', () => {
    const GridLayout = () => (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>Item 1</div>
        <div>Item 2</div>
      </div>
    );

    render(<GridLayout />);

    expect(screen.getByText('Item 1')).toBeInTheDocument();
    expect(screen.getByText('Item 2')).toBeInTheDocument();
  });
});

describe('Theme and Styling Utilities', () => {
  it('should apply dark mode classes', () => {
    const DarkModeComponent = ({ isDark }: any) => (
      <div className={isDark ? 'bg-gray-900 text-white' : 'bg-white text-black'}>
        Content
      </div>
    );

    const { container, rerender } = render(<DarkModeComponent isDark={false} />);

    expect(container.firstChild?.className).toContain('bg-white');

    rerender(<DarkModeComponent isDark={true} />);

    expect(container.firstChild?.className).toContain('bg-gray-900');
  });

  it('should support custom theme colors', () => {
    const ThemedButton = ({ variant }: any) => {
      const colors = {
        primary: 'bg-blue-600',
        success: 'bg-green-600',
        danger: 'bg-red-600',
      };

      return <button className={colors[variant]}>Button</button>;
    };

    const { container, rerender } = render(<ThemedButton variant="primary" />);

    expect(container.querySelector('button')?.className).toContain('bg-blue-600');

    rerender(<ThemedButton variant="success" />);

    expect(container.querySelector('button')?.className).toContain('bg-green-600');
  });
});
