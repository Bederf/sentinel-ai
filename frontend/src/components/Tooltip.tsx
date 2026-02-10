/**
 * Tooltip - Simple hover tooltip component
 */

import React, { useState } from 'react';

interface TooltipProps {
  content: string;
  children: React.ReactNode;
  side?: 'top' | 'bottom' | 'left' | 'right';
}

export function Tooltip({ content, children, side = 'top' }: TooltipProps) {
  const [visible, setVisible] = useState(false);

  const getPosition = () => {
    switch (side) {
      case 'bottom':
        return { top: '100%', left: '50%', transform: 'translateX(-50%) translateY(8px)' };
      case 'left':
        return { top: '50%', right: '100%', transform: 'translateY(-50%) translateX(-8px)' };
      case 'right':
        return { top: '50%', left: '100%', transform: 'translateY(-50%) translateX(8px)' };
      default:
        return { bottom: '100%', left: '50%', transform: 'translateX(-50%) translateY(-8px)' };
    }
  };

  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      {visible && (
        <div
          className="absolute z-50 px-3 py-2 text-xs font-medium text-white bg-gray-900 rounded whitespace-nowrap pointer-events-none"
          style={getPosition() as React.CSSProperties}
        >
          {content}
          {/* Arrow */}
          <div
            className="absolute w-2 h-2 bg-gray-900"
            style={
              side === 'bottom'
                ? { top: '-4px', left: '50%', transform: 'translateX(-50%) rotate(45deg)' }
                : side === 'left'
                  ? { right: '-4px', top: '50%', transform: 'translateY(-50%) rotate(45deg)' }
                  : side === 'right'
                    ? { left: '-4px', top: '50%', transform: 'translateY(-50%) rotate(45deg)' }
                    : { bottom: '-4px', left: '50%', transform: 'translateX(-50%) rotate(45deg)' }
            }
          />
        </div>
      )}
    </div>
  );
}
