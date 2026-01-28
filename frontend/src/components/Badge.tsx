import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ children, className = '' }) => {
  return (
    <span className={`inline-flex items-center px-2 py-1 text-xs font-medium rounded-full ${className}`}>
      {children}
    </span>
  );
};
