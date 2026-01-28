import React, { useState } from 'react';
import type { ReactNode } from 'react';

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
  delay?: number;
  className?: string;
}

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  position = 'top',
  delay = 300,
  className = '',
}) => {
  const [isVisible, setIsVisible] = useState(false);
  const [timeoutId, setTimeoutId] = useState<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = () => {
    const id = setTimeout(() => {
      setIsVisible(true);
    }, delay);
    setTimeoutId(id);
  };

  const handleMouseLeave = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      setTimeoutId(null);
    }
    setIsVisible(false);
  };

  const positionClasses = {
    top: 'bottom-full left-1/2 transform -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 transform -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 transform -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 transform -translate-y-1/2 ml-2',
  };

  const arrowClasses = {
    top: 'bottom-[-6px] left-1/2 transform -translate-x-1/2 border-t-gray-800',
    bottom: 'top-[-6px] left-1/2 transform -translate-x-1/2 border-b-gray-800',
    left: 'right-[-6px] top-1/2 transform -translate-y-1/2 border-l-gray-800',
    right: 'left-[-6px] top-1/2 transform -translate-y-1/2 border-r-gray-800',
  };

  return (
    <div
      className={`relative inline-block ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {children}
      {isVisible && (
        <div
          className={`
            absolute z-50
            ${positionClasses[position]}
            animate-fadeIn
          `}
        >
          <div className="relative">
            <div className="bg-gray-800 text-white rounded-md shadow-lg p-2 max-w-xs">
              {content}
            </div>
            {/* Arrow */}
            <div
              className={`
                absolute w-0 h-0
                border-4 border-transparent
                ${arrowClasses[position]}
              `}
            />
          </div>
        </div>
      )}
    </div>
  );
};