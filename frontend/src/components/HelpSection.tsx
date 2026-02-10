/**
 * HelpSection - Informational box for wizard step guidance
 */

import React from 'react';
import { InfoIcon } from 'lucide-react';

interface HelpSectionProps {
  title: string;
  children: React.ReactNode;
  variant?: 'info' | 'success' | 'warning';
}

export function HelpSection({ title, children, variant = 'info' }: HelpSectionProps) {
  const getColors = () => {
    switch (variant) {
      case 'success':
        return {
          bg: 'var(--color-sentinel-green)11',
          border: 'var(--color-sentinel-green)',
          text: 'var(--color-sentinel-green)',
        };
      case 'warning':
        return {
          bg: 'var(--color-sentinel-yellow)11',
          border: 'var(--color-sentinel-yellow)',
          text: 'var(--color-sentinel-yellow)',
        };
      default:
        return {
          bg: 'var(--color-sentinel-blue)11',
          border: 'var(--color-sentinel-blue)',
          text: 'var(--color-sentinel-blue)',
        };
    }
  };

  const colors = getColors();

  return (
    <div
      className="rounded-lg p-4 border-l-4 space-y-2"
      style={{
        background: colors.bg,
        borderColor: colors.border,
      }}
    >
      <div className="flex items-center gap-2">
        <InfoIcon
          className="w-5 h-5 shrink-0"
          style={{ color: colors.text }}
        />
        <p
          className="text-sm font-semibold"
          style={{ color: colors.text }}
        >
          {title}
        </p>
      </div>
      <div
        className="text-sm ml-7"
        style={{ color: colors.text }}
      >
        {children}
      </div>
    </div>
  );
}
