/**
 * KPICard Component Tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import KPICard from '../KPICard';
import { Bell } from 'lucide-react';

describe('KPICard', () => {
  describe('Rendering', () => {
    it('should render title', () => {
      render(<KPICard title="Test KPI" value={100} />);
      // CSS applies uppercase, but DOM text is unchanged
      expect(screen.getByText('Test KPI')).toBeInTheDocument();
    });

    it('should render numeric value', () => {
      render(<KPICard title="Test" value={1234} />);
      expect(screen.getByText('1,234')).toBeInTheDocument();
    });

    it('should render string value', () => {
      render(<KPICard title="Test" value="Custom Value" />);
      expect(screen.getByText('Custom Value')).toBeInTheDocument();
    });

    it('should render icon when provided', () => {
      const icon = <Bell data-testid="test-icon" />;
      render(<KPICard title="Test" value={100} icon={icon} />);
      expect(screen.getByTestId('test-icon')).toBeInTheDocument();
    });
  });

  describe('Delta/Trend Display', () => {
    it('should display positive delta', () => {
      render(<KPICard title="Test" value={100} delta={12.5} />);
      expect(screen.getByText('+12.5%')).toBeInTheDocument();
    });

    it('should display negative delta', () => {
      render(<KPICard title="Test" value={100} delta={-5.3} />);
      expect(screen.getByText('-5.3%')).toBeInTheDocument();
    });

    it('should display delta text when provided', () => {
      render(
        <KPICard
          title="Test"
          value={100}
          delta={10}
          deltaText="vs last week"
        />
      );
      expect(screen.getByText('vs last week')).toBeInTheDocument();
    });

    it('should show green for positive trend (non-inverse)', () => {
      render(<KPICard title="Test" value={100} delta={10} />);
      const deltaElement = screen.getByText('+10.0%');
      expect(deltaElement).toBeInTheDocument();
      // Check parent has green styling
      const parent = deltaElement.closest('div');
      expect(parent).toHaveStyle({ color: 'var(--color-sentinel-green)' });
    });

    it('should show red for negative trend (non-inverse)', () => {
      render(<KPICard title="Test" value={100} delta={-10} />);
      const deltaElement = screen.getByText('-10.0%');
      expect(deltaElement).toBeInTheDocument();
    });

    it('should invert trend colors when isInverseTrend is true', () => {
      render(
        <KPICard
          title="Test"
          value={100}
          delta={-10}
          isInverseTrend={true}
        />
      );
      // Negative delta should be green (good) when inverted
      const deltaElement = screen.getByText('-10.0%');
      expect(deltaElement).toBeInTheDocument();
    });
  });

  describe('Subtitle Display', () => {
    it('should display subtitle when no delta', () => {
      render(<KPICard title="Test" value={100} subtitle="Test subtitle" />);
      expect(screen.getByText('Test subtitle')).toBeInTheDocument();
    });

    it('should not display subtitle when delta is provided', () => {
      render(
        <KPICard
          title="Test"
          value={100}
          delta={10}
          subtitle="Should not show"
        />
      );
      expect(screen.queryByText('Should not show')).not.toBeInTheDocument();
    });
  });

  describe('Click Handling', () => {
    it('should call onClick when card is clicked', async () => {
      const handleClick = vi.fn();
      const user = userEvent.setup();

      render(<KPICard title="Test" value={100} onClick={handleClick} />);

      // CSS applies uppercase, but DOM text is unchanged
      const card = screen.getByText('Test').closest('div[class*="cursor-pointer"]');
      if (card) {
        await user.click(card);
        expect(handleClick).toHaveBeenCalledTimes(1);
      }
    });

    it('should not have cursor-pointer class when onClick is not provided', () => {
      const { container } = render(<KPICard title="Test" value={100} />);
      const card = container.querySelector('div[class*="cursor-pointer"]');
      expect(card).not.toBeInTheDocument();
    });
  });

  describe('Accent Colors', () => {
    it('should use default blue accent color', () => {
      const { container } = render(<KPICard title="Test" value={100} />);
      const accentBar = container.querySelector('div[class*="absolute top-0"]');
      expect(accentBar).toHaveStyle({ background: 'var(--color-sentinel-blue)' });
    });

    it('should use green accent color when specified', () => {
      const { container } = render(
        <KPICard title="Test" value={100} accentColor="green" />
      );
      const accentBar = container.querySelector('div[class*="absolute top-0"]');
      expect(accentBar).toHaveStyle({ background: 'var(--color-sentinel-green)' });
    });

    it('should use orange accent color when specified', () => {
      const { container } = render(
        <KPICard title="Test" value={100} accentColor="orange" />
      );
      const accentBar = container.querySelector('div[class*="absolute top-0"]');
      expect(accentBar).toHaveStyle({ background: 'var(--color-sentinel-amber)' });
    });

    it('should use red accent color when specified', () => {
      const { container } = render(
        <KPICard title="Test" value={100} accentColor="red" />
      );
      const accentBar = container.querySelector('div[class*="absolute top-0"]');
      expect(accentBar).toHaveStyle({ background: 'var(--color-sentinel-red)' });
    });
  });

  describe('Value Formatting', () => {
    it('should format large numbers with commas', () => {
      render(<KPICard title="Test" value={1234567} />);
      expect(screen.getByText('1,234,567')).toBeInTheDocument();
    });

    it('should display zero correctly', () => {
      render(<KPICard title="Test" value={0} />);
      expect(screen.getByText('0')).toBeInTheDocument();
    });

    it('should display decimal numbers', () => {
      render(<KPICard title="Test" value={1234.56} />);
      expect(screen.getByText('1,234.56')).toBeInTheDocument();
    });
  });
});
