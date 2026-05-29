import React, { useState, useEffect } from 'react';
import { Card } from './Card';
import { AlertCircle, Save, RotateCcw } from 'lucide-react';
import { api } from '@/lib/api';
import { PageLoading } from './PageLoading';

interface BoundaryConfig {
  device_id: string;
  device_name: string;
  point_name: string;
  lower_boundary: number;
  upper_boundary: number;
  warning_threshold: number;
  temporary_relaxation?: {
    relaxation_amount: number;
    expires_at: string;
    reason: string;
  };
}

interface SafetyBoundaryConfigProps {
  deviceId?: string;
  onBoundaryUpdate?: (config: BoundaryConfig) => void;
}

export const SafetyBoundaryConfig: React.FC<SafetyBoundaryConfigProps> = ({
  deviceId,
  onBoundaryUpdate,
}) => {
  const [boundaries, setBoundaries] = useState<BoundaryConfig[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedBoundary, setSelectedBoundary] = useState<BoundaryConfig | null>(null);
  const [showEditor, setShowEditor] = useState(false);
  const [showRelaxDialog, setShowRelaxDialog] = useState(false);
  const [editValues, setEditValues] = useState<Partial<BoundaryConfig>>({});
  const [relaxationAmount, setRelaxationAmount] = useState('5');
  const [relaxationReason, setRelaxationReason] = useState('');

  const fetchBoundaries = async () => {
    setIsLoading(true);
    try {
      const response = await api.getBoundaryStatus(deviceId);
      const boundariesData = response.data || [];
      setBoundaries(
        Array.isArray(boundariesData)
          ? boundariesData
          : Object.entries(boundariesData).map(([id, data]) => ({
              device_id: id,
              ...(typeof data === 'object' ? data : {}),
            }))
      );
    } catch (error) {
      console.error('Failed to fetch boundaries:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchBoundaries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  const handleEditBoundary = (boundary: BoundaryConfig) => {
    setSelectedBoundary(boundary);
    setEditValues({ ...boundary });
    setShowEditor(true);
  };

  const handleSaveBoundary = async () => {
    if (!selectedBoundary) return;

    try {
      await api.updateBoundary(selectedBoundary.device_id, editValues as any);
      setBoundaries(
        boundaries.map((b) =>
          b.device_id === selectedBoundary.device_id
            ? { ...b, ...editValues }
            : b
        )
      );
      setShowEditor(false);
      setSelectedBoundary(null);
      if (onBoundaryUpdate) {
        onBoundaryUpdate({ ...selectedBoundary, ...editValues });
      }
    } catch (error) {
      console.error('Failed to save boundary:', error);
    }
  };

  const handleApplyRelaxation = async () => {
    if (!selectedBoundary || !relaxationReason) return;

    try {
      // Apply temporary relaxation
      const relaxedBoundary = {
        ...selectedBoundary,
        upper_boundary: selectedBoundary.upper_boundary + parseFloat(relaxationAmount),
        temporary_relaxation: {
          relaxation_amount: parseFloat(relaxationAmount),
          expires_at: new Date(Date.now() + 3600000).toISOString(), // 1 hour
          reason: relaxationReason,
        },
      };

      await api.updateBoundary(selectedBoundary.device_id, relaxedBoundary as any);
      setBoundaries(
        boundaries.map((b) =>
          b.device_id === selectedBoundary.device_id ? relaxedBoundary : b
        )
      );
      setShowRelaxDialog(false);
      setRelaxationAmount('5');
      setRelaxationReason('');
    } catch (error) {
      console.error('Failed to apply relaxation:', error);
    }
  };

  const resetBoundary = async (device: BoundaryConfig) => {
    try {
      const defaultConfig = {
        ...device,
        temporary_relaxation: undefined,
      };
      await api.updateBoundary(device.device_id, defaultConfig as any);
      setBoundaries(
        boundaries.map((b) =>
          b.device_id === device.device_id ? defaultConfig : b
        )
      );
    } catch (error) {
      console.error('Failed to reset boundary:', error);
    }
  };

  const validateBoundaries = (
    lower: number,
    upper: number,
    warning: number
  ): string[] => {
    const errors: string[] = [];
    if (lower >= upper) {
      errors.push('Lower boundary must be less than upper boundary');
    }
    if (warning < lower || warning > upper) {
      errors.push('Warning threshold must be between boundaries');
    }
    return errors;
  };

  return (
    <Card className="p-6 rounded-lg">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
          Safety Boundary Configuration
        </h3>
        <p className="text-sm text-gray-500">
          Configure and monitor safety boundaries for each control point
        </p>
      </div>

      {isLoading ? (
        <PageLoading compact message="Loading boundary configuration..." />
      ) : (
        <div className="space-y-4">
          {boundaries.length === 0 ? (
            <p className="text-gray-500 text-center py-8">
              No boundary configurations available
            </p>
          ) : (
            boundaries.map((boundary) => (
              <div
                key={boundary.device_id}
                className="border rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h4 className="font-medium text-gray-900 dark:text-gray-100">
                      {boundary.device_name}
                    </h4>
                    <p className="text-sm text-gray-500">{boundary.point_name}</p>
                  </div>
                  <div className="flex space-x-2">
                    <button
                      onClick={() => handleEditBoundary(boundary)}
                      className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                    >
                      Edit
                    </button>
                    {boundary.temporary_relaxation && (
                      <button
                        onClick={() => resetBoundary(boundary)}
                        className="px-3 py-1 bg-gray-600 text-white text-sm rounded hover:bg-gray-700 transition-colors flex items-center space-x-1"
                      >
                        <RotateCcw className="h-3 w-3" />
                        <span>Reset</span>
                      </button>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded">
                    <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
                      Lower
                    </div>
                    <div className="font-semibold text-gray-900 dark:text-gray-100">
                      {boundary.lower_boundary}
                    </div>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded border-2 border-yellow-400">
                    <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
                      Warning
                    </div>
                    <div className="font-semibold text-yellow-600">
                      {boundary.warning_threshold}
                    </div>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded">
                    <div className="text-gray-500 text-xs uppercase tracking-wider mb-1">
                      Upper
                    </div>
                    <div className="font-semibold text-gray-900 dark:text-gray-100">
                      {boundary.upper_boundary}
                    </div>
                  </div>
                </div>

                {boundary.temporary_relaxation && (
                  <div className="mt-3 p-3 bg-yellow-50 dark:bg-yellow-900 border border-yellow-200 rounded">
                    <div className="flex items-start space-x-2">
                      <AlertCircle className="h-4 w-4 text-yellow-600 mt-0.5 flex-shrink-0" />
                      <div className="text-sm">
                        <div className="font-medium text-yellow-900">
                          Temporary Relaxation Active
                        </div>
                        <div className="text-xs text-yellow-800 mt-1">
                          +{boundary.temporary_relaxation.relaxation_amount} until{' '}
                          {new Date(
                            boundary.temporary_relaxation.expires_at
                          ).toLocaleTimeString()}
                        </div>
                        <div className="text-xs text-yellow-700 mt-1 italic">
                          Reason: {boundary.temporary_relaxation.reason}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Boundary Editor Dialog */}
      {showEditor && selectedBoundary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <Card className="w-96 p-6 rounded-lg shadow-md">
            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
              Edit Boundary Configuration
            </h3>

            <div className="space-y-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                  Lower Boundary
                </label>
                <input
                  type="number"
                  value={editValues.lower_boundary || ''}
                  onChange={(e) =>
                    setEditValues({
                      ...editValues,
                      lower_boundary: parseFloat(e.target.value),
                    })
                  }
                  className="w-full px-3 py-2 border rounded text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                  Warning Threshold
                </label>
                <input
                  type="number"
                  value={editValues.warning_threshold || ''}
                  onChange={(e) =>
                    setEditValues({
                      ...editValues,
                      warning_threshold: parseFloat(e.target.value),
                    })
                  }
                  className="w-full px-3 py-2 border rounded text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                  Upper Boundary
                </label>
                <input
                  type="number"
                  value={editValues.upper_boundary || ''}
                  onChange={(e) =>
                    setEditValues({
                      ...editValues,
                      upper_boundary: parseFloat(e.target.value),
                    })
                  }
                  className="w-full px-3 py-2 border rounded text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                />
              </div>

              {validateBoundaries(
                editValues.lower_boundary || 0,
                editValues.upper_boundary || 0,
                editValues.warning_threshold || 0
              ).length > 0 && (
                <div className="p-3 bg-red-50 dark:bg-red-900 border border-red-200 rounded">
                  {validateBoundaries(
                    editValues.lower_boundary || 0,
                    editValues.upper_boundary || 0,
                    editValues.warning_threshold || 0
                  ).map((error, idx) => (
                    <div key={idx} className="text-sm text-red-700 dark:text-red-200">
                      {error}
                    </div>
                  ))}
                </div>
              )}

              <div className="pt-2 border-t">
                <button
                  onClick={() => setShowRelaxDialog(true)}
                  className="text-sm text-blue-600 hover:text-blue-800 transition-colors"
                >
                  Apply Temporary Relaxation...
                </button>
              </div>
            </div>

            <div className="flex space-x-3">
              <button
                onClick={handleSaveBoundary}
                disabled={
                  validateBoundaries(
                    editValues.lower_boundary || 0,
                    editValues.upper_boundary || 0,
                    editValues.warning_threshold || 0
                  ).length > 0
                }
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center justify-center space-x-2"
              >
                <Save className="h-4 w-4" />
                <span>Save</span>
              </button>
              <button
                onClick={() => {
                  setShowEditor(false);
                  setSelectedBoundary(null);
                  setShowRelaxDialog(false);
                }}
                className="flex-1 px-4 py-2 bg-gray-300 text-gray-900 rounded font-medium hover:bg-gray-400 transition-colors"
              >
                Cancel
              </button>
            </div>
          </Card>
        </div>
      )}

      {/* Temporary Relaxation Dialog */}
      {showRelaxDialog && selectedBoundary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <Card className="w-96 p-6 rounded-lg shadow-md border-l-4 border-l-yellow-500">
            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
              Temporary Boundary Relaxation
            </h3>

            <div className="bg-yellow-50 dark:bg-yellow-900 p-3 rounded mb-4 text-sm text-yellow-900 dark:text-yellow-100">
              Temporarily adjust boundaries for maintenance. This will auto-revert after 1 hour.
            </div>

            <div className="space-y-4 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                  Relaxation Amount
                </label>
                <input
                  type="number"
                  value={relaxationAmount}
                  onChange={(e) => setRelaxationAmount(e.target.value)}
                  className="w-full px-3 py-2 border rounded text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700"
                />
                <div className="text-xs text-gray-500 mt-1">
                  New upper boundary: {(selectedBoundary.upper_boundary + parseFloat(relaxationAmount)).toFixed(2)}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">
                  Reason for Relaxation
                </label>
                <textarea
                  value={relaxationReason}
                  onChange={(e) => setRelaxationReason(e.target.value)}
                  placeholder="Why is this relaxation needed?"
                  className="w-full px-3 py-2 border rounded text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 resize-none"
                  rows={3}
                />
              </div>
            </div>

            <div className="flex space-x-3">
              <button
                onClick={handleApplyRelaxation}
                disabled={!relaxationReason}
                className="flex-1 px-4 py-2 bg-yellow-600 text-white rounded font-medium hover:bg-yellow-700 transition-colors disabled:opacity-50"
              >
                Apply Relaxation
              </button>
              <button
                onClick={() => setShowRelaxDialog(false)}
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
