import React from 'react';
import { Tooltip } from './Tooltip';

export type SafetyStatus = 'safe' | 'warning' | 'blocked' | 'alarm' | 'unknown';

interface SafetyIndicatorProps {
  status: SafetyStatus;
  deviceId?: string;
  deviceName?: string;
  onClick?: () => void;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

export const SafetyIndicator: React.FC<SafetyIndicatorProps> = ({
  status,
  deviceId,
  deviceName,
  onClick,
  size = 'md',
  showLabel = false,
  className = '',
}) => {
  // Status colors matching Grafana-style design
  const statusConfig = {
    safe: {
      color: 'bg-green-500',
      borderColor: 'border-green-400',
      textColor: 'text-green-700',
      label: 'Safe',
      icon: '✓',
    },
    warning: {
      color: 'bg-yellow-500',
      borderColor: 'border-yellow-400',
      textColor: 'text-yellow-700',
      label: 'Warning',
      icon: '⚠',
    },
    blocked: {
      color: 'bg-red-500',
      borderColor: 'border-red-400',
      textColor: 'text-red-700',
      label: 'Blocked',
      icon: '⛔',
    },
    alarm: {
      color: 'bg-orange-500',
      borderColor: 'border-orange-400',
      textColor: 'text-orange-700',
      label: 'Alarm',
      icon: '🚨',
    },
    unknown: {
      color: 'bg-gray-400',
      borderColor: 'border-gray-300',
      textColor: 'text-gray-600',
      label: 'Unknown',
      icon: '?',
    },
  };

  const config = statusConfig[status];

  // Size configuration
  const sizeConfig = {
    sm: {
      dotSize: 'w-2 h-2',
      iconSize: 'text-xs',
      labelSize: 'text-xs',
    },
    md: {
      dotSize: 'w-3 h-3',
      iconSize: 'text-sm',
      labelSize: 'text-sm',
    },
    lg: {
      dotSize: 'w-4 h-4',
      iconSize: 'text-base',
      labelSize: 'text-base',
    },
  };

  const sizeStyle = sizeConfig[size];

  // Tooltip content
  const tooltipContent = (
    <div className="p-2 max-w-xs">
      <div className="font-semibold text-gray-900 mb-1">
        Safety Status: {config.label}
      </div>
      {deviceName && (
        <div className="text-sm text-gray-700 mb-1">
          Device: {deviceName}
        </div>
      )}
      {deviceId && (
        <div className="text-xs text-gray-500 mb-2">
          ID: {deviceId}
        </div>
      )}
      <div className="text-sm text-gray-700">
        {status === 'safe' && 'All safety rules are satisfied.'}
        {status === 'warning' && 'Safety warnings detected. Operation allowed with caution.'}
        {status === 'blocked' && 'Safety violations detected. Operation blocked.'}
        {status === 'alarm' && 'Safety alarm active. Immediate attention required.'}
        {status === 'unknown' && 'Safety status unknown or not available.'}
      </div>
    </div>
  );

  const indicatorContent = (
    <div
      className={`
        inline-flex items-center gap-1.5
        ${onClick ? 'cursor-pointer hover:opacity-80 transition-opacity' : ''}
        ${className}
      `}
      onClick={onClick}
    >
      {/* Status dot */}
      <div
        className={`
          ${config.color} ${sizeStyle.dotSize}
          rounded-full border ${config.borderColor}
          flex items-center justify-center
          ${size === 'sm' ? '' : 'shadow-sm'}
        `}
        aria-label={`Safety status: ${config.label}`}
      >
        {size !== 'sm' && (
          <span className={`${config.textColor} ${sizeStyle.iconSize} font-bold`}>
            {config.icon}
          </span>
        )}
      </div>

      {/* Optional label */}
      {showLabel && (
        <span className={`${config.textColor} ${sizeStyle.labelSize} font-medium`}>
          {config.label}
        </span>
      )}
    </div>
  );

  // Wrap with tooltip if we have device info
  if (deviceName || deviceId) {
    return (
      <Tooltip content={tooltipContent} position="top">
        {indicatorContent}
      </Tooltip>
    );
  }

  return indicatorContent;
};

// Helper component for inline safety status display
interface InlineSafetyStatusProps {
  status: SafetyStatus;
  message?: string;
  className?: string;
}

export const InlineSafetyStatus: React.FC<InlineSafetyStatusProps> = ({
  status,
  message,
  className = '',
}) => {
  const statusConfig = {
    safe: { color: 'text-green-600', bg: 'bg-green-50', border: 'border-green-200' },
    warning: { color: 'text-yellow-600', bg: 'bg-yellow-50', border: 'border-yellow-200' },
    blocked: { color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200' },
    alarm: { color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-200' },
    unknown: { color: 'text-gray-600', bg: 'bg-gray-50', border: 'border-gray-200' },
  };

  const config = statusConfig[status];
  const labels = {
    safe: 'Safe',
    warning: 'Warning',
    blocked: 'Blocked',
    alarm: 'Alarm',
    unknown: 'Unknown',
  };

  return (
    <div
      className={`
        inline-flex items-center gap-2 px-3 py-1.5 rounded-md
        ${config.bg} ${config.border} border
        ${className}
      `}
    >
      <SafetyIndicator status={status} size="sm" />
      <div>
        <div className={`text-sm font-medium ${config.color}`}>
          {labels[status]}
        </div>
        {message && (
          <div className="text-xs text-gray-600 mt-0.5">
            {message}
          </div>
        )}
      </div>
    </div>
  );
};