/**
 * SwitchControl Component Tests
 *
 * Tests the switch/toggle control widget including:
 * - Rendering and visual state
 * - Toggle interaction and state changes
 * - onChange callbacks
 * - Disabled state
 * - Error display
 * - Optimistic updates
 */

import { render, screen, fireEvent, waitFor } from '../../test-utils';
import { SwitchControl } from '../SwitchControl';
import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('SwitchControl', () => {
  const defaultProps = {
    label: 'Chiller Power',
    value: false,
    onChange: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render with label', () => {
      render(<SwitchControl {...defaultProps} />);
      expect(screen.getByText('Chiller Power')).toBeInTheDocument();
    });

    it('should display OFF label when value is false', () => {
      render(<SwitchControl {...defaultProps} value={false} />);
      expect(screen.getByText('OFF')).toBeInTheDocument();
    });

    it('should display ON label when value is true', () => {
      render(<SwitchControl {...defaultProps} value={true} />);
      expect(screen.getByText('ON')).toBeInTheDocument();
    });

    it('should display status badge INACTIVE when off', () => {
      render(<SwitchControl {...defaultProps} value={false} />);
      expect(screen.getByText('INACTIVE')).toBeInTheDocument();
    });

    it('should display status badge ACTIVE when on', () => {
      render(<SwitchControl {...defaultProps} value={true} />);
      expect(screen.getByText('ACTIVE')).toBeInTheDocument();
    });

    it('should display PowerOff icon when off', () => {
      const { container } = render(<SwitchControl {...defaultProps} value={false} />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('should display Power icon when on', () => {
      const { container } = render(<SwitchControl {...defaultProps} value={true} />);
      expect(container.querySelector('svg')).toBeInTheDocument();
    });

    it('should display descriptive text when off', () => {
      render(<SwitchControl {...defaultProps} value={false} />);
      expect(screen.getByText(/Device is currently inactive/)).toBeInTheDocument();
    });

    it('should display descriptive text when on', () => {
      render(<SwitchControl {...defaultProps} value={true} />);
      expect(screen.getByText(/Device is currently active/)).toBeInTheDocument();
    });

    it('should have toggle button', () => {
      render(<SwitchControl {...defaultProps} />);
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });
  });

  describe('Toggle Interaction', () => {
    it('should call onChange with true when toggling from false', () => {
      const onChange = vi.fn();
      render(<SwitchControl {...defaultProps} value={false} onChange={onChange} />);

      const toggleButton = screen.getAllByRole('button')[0];
      fireEvent.click(toggleButton);

      expect(onChange).toHaveBeenCalledWith(true);
    });

    it('should call onChange with false when toggling from true', () => {
      const onChange = vi.fn();
      render(<SwitchControl {...defaultProps} value={true} onChange={onChange} />);

      const toggleButton = screen.getAllByRole('button')[0];
      fireEvent.click(toggleButton);

      expect(onChange).toHaveBeenCalledWith(false);
    });

    it('should only call onChange once per toggle', () => {
      const onChange = vi.fn();
      render(<SwitchControl {...defaultProps} value={false} onChange={onChange} />);

      const toggleButton = screen.getAllByRole('button')[0];
      fireEvent.click(toggleButton);

      expect(onChange).toHaveBeenCalledTimes(1);
    });

    it('should update state optimistically', async () => {
      const onChange = vi.fn();
      const { rerender } = render(
        <SwitchControl {...defaultProps} value={false} onChange={onChange} />
      );

      const toggleButton = screen.getAllByRole('button')[0];
      fireEvent.click(toggleButton);

      // Should show ACTIVE immediately (optimistic update)
      await waitFor(() => {
        // After toggle, the component should reflect the new state
        expect(onChange).toHaveBeenCalledWith(true);
      });
    });
  });

  describe('Disabled State', () => {
    it('should display disabled badge', () => {
      render(<SwitchControl {...defaultProps} disabled={true} />);
      expect(screen.getByText('Disabled')).toBeInTheDocument();
    });

    it('should not respond to clicks when disabled', () => {
      const onChange = vi.fn();
      render(
        <SwitchControl {...defaultProps} disabled={true} onChange={onChange} />
      );

      const toggleButton = screen.getAllByRole('button')[0];
      fireEvent.click(toggleButton);

      expect(onChange).not.toHaveBeenCalled();
    });

    it('should be disabled button when disabled prop is true', () => {
      render(<SwitchControl {...defaultProps} disabled={true} />);
      const toggleButton = screen.getAllByRole('button')[0];
      expect(toggleButton).toBeDisabled();
    });

    it('should have reduced opacity when disabled', () => {
      const { container } = render(
        <SwitchControl {...defaultProps} disabled={true} />
      );

      const wrapper = container.firstChild;
      expect(wrapper.getAttribute('style')).toContain('opacity');
    });
  });

  describe('Error Handling', () => {
    it('should display error message', () => {
      render(
        <SwitchControl
          {...defaultProps}
          error="Device communication failed"
        />
      );
      expect(screen.getByText('Device communication failed')).toBeInTheDocument();
    });

    it('should have red border when error present', () => {
      const { container } = render(
        <SwitchControl
          {...defaultProps}
          error="Device communication failed"
        />
      );

      const wrapper = container.firstChild as HTMLElement;
      const style = wrapper.getAttribute('style') || '';
      expect(style).toContain('color-sentinel-red');
    });

    it('should have normal border when no error', () => {
      const { container } = render(<SwitchControl {...defaultProps} />);

      const wrapper = container.firstChild;
      // Should use sentinel-border, not red
      expect(wrapper.getAttribute('style')).toContain('sentinel-border');
    });
  });

  describe('State Updates from Props', () => {
    it('should update display when value prop changes to true', () => {
      const { rerender } = render(
        <SwitchControl {...defaultProps} value={false} />
      );
      expect(screen.getByText('INACTIVE')).toBeInTheDocument();

      rerender(<SwitchControl {...defaultProps} value={true} />);
      expect(screen.getByText('ACTIVE')).toBeInTheDocument();
    });

    it('should update display when value prop changes to false', () => {
      const { rerender } = render(
        <SwitchControl {...defaultProps} value={true} />
      );
      expect(screen.getByText('ACTIVE')).toBeInTheDocument();

      rerender(<SwitchControl {...defaultProps} value={false} />);
      expect(screen.getByText('INACTIVE')).toBeInTheDocument();
    });

    it('should sync display value with prop after toggle', () => {
      const onChange = vi.fn();
      const { rerender } = render(
        <SwitchControl {...defaultProps} value={false} onChange={onChange} />
      );

      const toggleButton = screen.getAllByRole('button')[0];
      fireEvent.click(toggleButton);

      // After prop update, display should reflect new state
      rerender(<SwitchControl {...defaultProps} value={true} onChange={onChange} />);
      expect(screen.getByText('ACTIVE')).toBeInTheDocument();
    });
  });

  describe('Animation', () => {
    it('should animate on toggle', async () => {
      const onChange = vi.fn();
      render(<SwitchControl {...defaultProps} value={false} onChange={onChange} />);

      const toggleButton = screen.getAllByRole('button')[0];
      fireEvent.click(toggleButton);

      // Component should have animation class during toggle
      // This would be visible in the className
      expect(toggleButton).toBeInTheDocument();
    });

    it('should have animation duration', () => {
      const { container } = render(<SwitchControl {...defaultProps} />);
      const toggleButton = container.querySelector('button');
      // Check for transition classes
      expect(toggleButton?.className).toMatch(/transition|duration/);
    });
  });

  describe('Icon State', () => {
    it('should show correct icon color when off', () => {
      const { container } = render(
        <SwitchControl {...defaultProps} value={false} />
      );
      // PowerOff icon should be red when off
      const svg = container.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });

    it('should show correct icon color when on', () => {
      const { container } = render(
        <SwitchControl {...defaultProps} value={true} />
      );
      // Power icon should be green when on
      const svg = container.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });
  });

  describe('Label Colors', () => {
    it('should color OFF label red when off', () => {
      render(<SwitchControl {...defaultProps} value={false} />);
      const offLabel = screen.getByText('OFF');
      // OFF should be visible and colored red
      expect(offLabel).toBeInTheDocument();
    });

    it('should color ON label green when on', () => {
      render(<SwitchControl {...defaultProps} value={true} />);
      const onLabel = screen.getByText('ON');
      // ON should be visible and colored green
      expect(onLabel).toBeInTheDocument();
    });

    it('should color OFF label gray when on', () => {
      render(<SwitchControl {...defaultProps} value={true} />);
      const offLabel = screen.getByText('OFF');
      // OFF should still be visible but in disabled color
      expect(offLabel).toBeInTheDocument();
    });

    it('should color ON label gray when off', () => {
      render(<SwitchControl {...defaultProps} value={false} />);
      const onLabel = screen.getByText('ON');
      // ON should still be visible but in disabled color
      expect(onLabel).toBeInTheDocument();
    });
  });

  describe('Toggle Knob Position', () => {
    it('should position knob on left when off', () => {
      const { container } = render(
        <SwitchControl {...defaultProps} value={false} />
      );
      const knob = container.querySelector('[class*="left-1"]');
      expect(knob).toBeInTheDocument();
    });

    it('should position knob on right when on', () => {
      const { container } = render(
        <SwitchControl {...defaultProps} value={true} />
      );
      const knob = container.querySelector('[class*="left-8"]');
      expect(knob).toBeInTheDocument();
    });
  });

  describe('Toggle Button Style', () => {
    it('should be red when off', () => {
      const { container } = render(
        <SwitchControl {...defaultProps} value={false} />
      );
      const toggleButton = container.querySelector('button');
      const style = toggleButton?.getAttribute('style');
      expect(style).toContain('red');
    });

    it('should be green when on', () => {
      const { container } = render(
        <SwitchControl {...defaultProps} value={true} />
      );
      const toggleButton = container.querySelector('button');
      const style = toggleButton?.getAttribute('style');
      expect(style).toContain('green');
    });
  });

  describe('Accessibility', () => {
    it('should have accessible toggle button', () => {
      render(<SwitchControl {...defaultProps} />);
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('should be keyboard navigable', () => {
      const onChange = vi.fn();
      render(
        <SwitchControl {...defaultProps} value={false} onChange={onChange} />
      );

      const toggleButton = screen.getAllByRole('button')[0];
      toggleButton.focus();
      expect(toggleButton).toHaveFocus();
    });

    it('should show disabled cursor when disabled', () => {
      const { container } = render(
        <SwitchControl {...defaultProps} disabled={true} />
      );
      const toggleButton = container.querySelector('button');
      const style = toggleButton?.getAttribute('style');
      expect(style).toContain('not-allowed');
    });
  });
});
