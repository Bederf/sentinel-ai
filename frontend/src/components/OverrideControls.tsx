import React, { useState } from 'react';
import { Card } from './Card';
import { AlertCircle, ToggleLeft, ToggleRight, Clock } from 'lucide-react';
import { api } from '@/lib/api';

interface OverrideControlsProps {
  onStatusChange?: (enabled: boolean) => void;
}

interface DeviceOverride {
  device_id: string;
  device_name: string;
  override_until: string;
  reason: string;
  initiated_by: string;
}

export const OverrideControls: React.FC<OverrideControlsProps> = ({
  onStatusChange,
}) => {
  const [autonomousEnabled, setAutonomousEnabled] = useState(true);
  const [showModeWarning, setShowModeWarning] = useState(false);
  const [deviceOverrides, setDeviceOverrides] = useState<DeviceOverride[]>([]);
  const [showDeviceOverrideDialog, setShowDeviceOverrideDialog] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState('');
  const [overrideDuration, setOverrideDuration] = useState('300'); // 5 minutes in seconds
  const [overrideReason, setOverrideReason] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const durationOptions = [
    { value: '300', label: '5 minutes' },
    { value: '1800', label: '30 minutes' },
    { value: '3600', label: '1 hour' },
  ];

  const handleToggleAutonomous = async () => {
    setShowModeWarning(true);
  };

  const confirmToggleAutonomous = async (enable: boolean) => {
    setIsLoading(true);
    try {
      if (enable) {
        await api.enableAutonomousMode();
        setAutonomousEnabled(true);
      } else {
        await api.disableAutonomousMode();
        setAutonomousEnabled(false);
      }
      setShowModeWarning(false);
      if (onStatusChange) {
        onStatusChange(enable);
      }
    } catch (error) {
      console.error('Failed to toggle autonomous mode:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeviceOverride = async () => {
    if (!selectedDevice || !overrideReason) {
      return;
    }

    setIsLoading(true);
    try {
      // This would be a new API endpoint for device-specific overrides
      // For now, we'll just update the UI
      const until = new Date(Date.now() + parseInt(overrideDuration) * 1000);
      const newOverride: DeviceOverride = {
        device_id: selectedDevice,
        device_name: selectedDevice, // Should be fetched from API
        override_until: until.toISOString(),
        reason: overrideReason,
        initiated_by: 'operator',
      };

      setDeviceOverrides([...deviceOverrides, newOverride]);
      setSelectedDevice('');
      setOverrideReason('');
      setShowDeviceOverrideDialog(false);
    } catch (error) {
      console.error('Failed to set device override:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const removeDeviceOverride = (deviceId: string) => {
    setDeviceOverrides(
      deviceOverrides.filter((o) => o.device_id !== deviceId)
    );
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = date.getTime() - now.getTime();
    const diffMins = Math.round(diffMs / 60000);

    if (diffMins <= 0) {
      return 'Expired';
    } else if (diffMins < 60) {
      return `${diffMins}m remaining`;
    } else {
      return `${Math.round(diffMins / 60)}h remaining`;
    }
  };

  return (
    <Card className="p-6 rounded-lg">
      <div className="mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
          Override Controls
        </h3>

        {/* Autonomous Mode Toggle */}
        <div className="border rounded-lg p-4 mb-6 bg-gray-50 dark:bg-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-gray-900 dark:text-gray-100">
                Autonomous Mode
              </h4>
              <p className="text-sm text-gray-500 mt-1">
                {autonomousEnabled
                  ? 'System is making autonomous decisions'
                  : 'System is in manual mode only'}
              </p>
            </div>
            <button
              onClick={handleToggleAutonomous}
              disabled={isLoading}
              className={`flex items-center space-x-2 px-4 py-2 rounded transition-all ${
                autonomousEnabled
                  ? 'bg-green-100 text-green-900 hover:bg-green-200'
                  : 'bg-gray-300 text-gray-900 hover:bg-gray-400'
              } disabled:opacity-50`}
            >
              {autonomousEnabled ? (
                <ToggleRight className="h-5 w-5" />
              ) : (
                <ToggleLeft className="h-5 w-5" />
              )}
              <span>{autonomousEnabled ? 'Enabled' : 'Disabled'}</span>
            </button>
          </div>
        </div>

        {/* Device Overrides */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between mb-4">
            <h4 className="font-medium text-gray-900 dark:text-gray-100 flex items-center space-x-2">
              <Clock className="h-4 w-4" />
              <span>Device Overrides</span>
            </h4>
            <button
              onClick={() => setShowDeviceOverrideDialog(true)}
              className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
            >
              Add Override
            </button>
          </div>

          {deviceOverrides.length === 0 ? (
            <p className="text-sm text-gray-500 py-4">
              No active device overrides
            </p>
          ) : (
            <div className="space-y-3">
              {deviceOverrides.map((override) => (
                <div
                  key={override.device_id}
                  className="border rounded p-3 flex items-center justify-between bg-yellow-50 dark:bg-yellow-900"
                >
                  <div className="flex-1">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {override.device_name}
                    </div>
                    <div className="text-xs text-gray-600 dark:text-gray-400">
                      {override.reason}
                    </div>
                    <div className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
                      {formatTime(override.override_until)}
                    </div>
                  </div>
                  <button
                    onClick={() => removeDeviceOverride(override.device_id)}
                    className="ml-4 px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700 transition-colors"
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Mode Warning Dialog */}
      {showModeWarning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <Card className="w-96 p-6 rounded-lg shadow-2xl border-l-4 border-l-yellow-500">
            <div className="flex items-center space-x-3 mb-4">
              <AlertCircle className="h-6 w-6 text-yellow-600" />
              <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
                Safety Warning
              </h3>
            </div>

            <div className="bg-yellow-50 dark:bg-yellow-900 p-4 rounded mb-4">
              <p className="text-sm text-gray-900 dark:text-gray-100">
                {autonomousEnabled
                  ? 'Disabling autonomous mode means the system will no longer make automatic decisions. Manual control only.'
                  : 'Enabling autonomous mode means the system will resume automatic decision-making within configured boundaries.'}
              </p>
            </div>

            <div className="flex space-x-3">
              <button
                onClick={() => confirmToggleAutonomous(!autonomousEnabled)}
                disabled={isLoading}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {isLoading ? 'Processing...' : 'Confirm'}
              </button>
              <button
                onClick={() => setShowModeWarning(false)}
                className="flex-1 px-4 py-2 bg-gray-300 text-gray-900 rounded font-medium hover:bg-gray-400 transition-colors"
              >
                Cancel
              </button>
            </div>
          </Card>
        </div>
      )}

      {/* Device Override Dialog */}
      {showDeviceOverrideDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <Card className="w-96 p-6 rounded-lg shadow-2xl">
            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
              Temporary Device Override
            </h3>

            <div className="space-y-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                  Device
                </label>
                <input
                  type="text"
                  value={selectedDevice}
                  onChange={(e) => setSelectedDevice(e.target.value)}
                  placeholder="Enter device ID or name"
                  className="w-full px-3 py-2 border rounded text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                  Duration
                </label>
                <select
                  value={overrideDuration}
                  onChange={(e) => setOverrideDuration(e.target.value)}
                  className="w-full px-3 py-2 border rounded text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                >
                  {durationOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                  Reason
                </label>
                <textarea
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="Why is this override needed?"
                  className="w-full px-3 py-2 border rounded text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 resize-none"
                  rows={3}
                />
              </div>
            </div>

            <div className="flex space-x-3">
              <button
                onClick={handleDeviceOverride}
                disabled={isLoading || !selectedDevice || !overrideReason}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {isLoading ? 'Processing...' : 'Apply Override'}
              </button>
              <button
                onClick={() => {
                  setShowDeviceOverrideDialog(false);
                  setSelectedDevice('');
                  setOverrideReason('');
                }}
                className="flex-1 px-4 py-2 bg-gray-300 text-gray-900 rounded font-medium hover:bg-gray-400 transition-colors"
              >
                Cancel
              </button>
            </div>
          </Card>
        </div>
      )}
    </Card>
  );
};
