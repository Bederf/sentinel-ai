import React, { useState } from 'react';
import { authorizedFetch } from '../lib/api/client';

interface EmergencyStopButtonProps {
  onEmergencyStop?: () => void;
  disabled?: boolean;
  className?: string;
}

export const EmergencyStopButton: React.FC<EmergencyStopButtonProps> = ({
  onEmergencyStop,
  disabled = false,
  className = '',
}) => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleEmergencyStop = async () => {
    if (!showConfirm) {
      setShowConfirm(true);
      return;
    }

    try {
      setIsProcessing(true);
      const response = await authorizedFetch('/api/safety/escalation/emergency-stop', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data = await response.json();

      if (data.success) {
        alert(`Emergency stop executed successfully!\n\nResponse time: ${data.response_time_seconds?.toFixed(2) || 'N/A'}s\nDevices affected: ${data.devices_affected || 0}`);
      } else {
        alert(`Emergency stop partially completed. ${data.message}`);
      }

      onEmergencyStop?.();
    } catch (error) {
      console.error('Emergency stop failed:', error);
      alert('Failed to execute emergency stop.');
    } finally {
      setIsProcessing(false);
      setShowConfirm(false);
    }
  };

  return (
    <div className={`relative inline-block ${className}`}>
      <button
        onClick={handleEmergencyStop}
        disabled={disabled || isProcessing}
        className={`relative overflow-hidden
          px-8 py-4 rounded-lg font-bold text-white
          transition-all duration-200
          ${isProcessing ? 'bg-red-500' : 'bg-red-600 hover:bg-red-700'}
          transform hover:scale-105 focus:outline-none focus:ring-4
          focus:ring-red-300 disabled:opacity-50 disabled:cursor-not-allowed
          shadow-lg disabled:shadow-none
        `}
      >
        <span className="relative z-10 flex items-center justify-center">
          {isProcessing ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white mr-2" />
              STOPPING...
            </>
          ) : (
            <>
              ⚠️ EMERGENCY STOP ⚠️
            </>
          )}
        </span>

        {!isProcessing && (
          <div className="absolute inset-0 bg-red-400 opacity-20 animate-ping" />
        )}

        {showConfirm && (
          <div className="absolute bottom-full mb-2 w-64 p-3 bg-yellow-100 dark:bg-yellow-900 border-2
            border-yellow-400 text-yellow-800 dark:text-yellow-200 rounded shadow-lg z-50">
            <div className="text-sm font-medium">
              CONFIRM EMERGENCY STOP
            </div>
            <div className="text-xs mt-1">
              Click again to confirm. This will stop autonomous mode immediately.
            </div>
          </div>
        )}
      </button>
    </div>
  );
};
