import React from 'react';

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  glass?: boolean;
}

export const Card: React.FC<CardProps> = ({ children, className = '', glass = false }) => {
  if (glass) {
    return (
      <div className={`glass-card ${className}`}>
        {children}
      </div>
    );
  }

  return (
    <div
      className={`rounded-lg shadow-md ${className}`}
      style={{
        background: "var(--color-sentinel-bg-panel)",
        border: "1px solid var(--color-sentinel-border)",
      }}
    >
      {children}
    </div>
  );
};
