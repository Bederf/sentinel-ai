/**
 * EquipmentVerificationWizard - Post-ingestion equipment verification
 * 
 * Guides users through 3-step process:
 * 1. Select equipment to test
 * 2. Run verification tests
 * 3. View results and complete
 */

import React, { useState } from 'react';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react';

interface Equipment {
  id: string;
  name: string;
  equipment_type: string;
  zone?: string;
  point_count?: number;
}

interface TestResult {
  equipment_id: string;
  equipment_name: string;
  status: 'pass' | 'fail' | 'pending';
  read_test?: {
    success: boolean;
    points_read?: number;
    error?: string;
  };
  write_test?: {
    success: boolean;
    points_written?: number;
    error?: string;
  };
  duration_ms?: number;
  error?: string;
}

interface EquipmentVerificationWizardProps {
  siteId: string;
  equipmentList: Equipment[];
  onComplete: () => void;
}

export function EquipmentVerificationWizard({
  siteId,
  equipmentList,
  onComplete,
}: EquipmentVerificationWizardProps) {
  const [step, setStep] = useState(1);
  const [selectedEquipment, setSelectedEquipment] = useState<string[]>([]);
  const [testResults, setTestResults] = useState<TestResult[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  // Step 1: Equipment Selection
  const handleToggleEquipment = (id: string) => {
    setSelectedEquipment((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleSelectRandom = () => {
    // Recommend selecting ~3 representative equipment
    const recommended = Math.min(3, equipmentList.length);
    const shuffled = [...equipmentList].sort(() => Math.random() - 0.5);
    setSelectedEquipment(shuffled.slice(0, recommended).map((e) => e.id));
  };

  // Step 2: Run Tests
  const handleRunTests = async () => {
    if (selectedEquipment.length === 0) return;

    setIsRunning(true);
    const results: TestResult[] = [];

    // Initialize pending results
    for (const eqId of selectedEquipment) {
      const equipment = equipmentList.find((e) => e.id === eqId);
      results.push({
        equipment_id: eqId,
        equipment_name: equipment?.name || eqId,
        status: 'pending',
      });
    }
    setTestResults(results);

    // Run tests sequentially
    for (let i = 0; i < selectedEquipment.length; i++) {
      const eqId = selectedEquipment[i];
      const equipment = equipmentList.find((e) => e.id === eqId);

      try {
        const startTime = performance.now();

        // Call verification API
        const response = await fetch(
          `/api/equipment/verify/${eqId}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ site_id: siteId }),
          }
        );

        const data = await response.json();
        const duration = Math.round(performance.now() - startTime);

        // Update result
        results[i] = {
          equipment_id: eqId,
          equipment_name: equipment?.name || eqId,
          status: data.success ? 'pass' : 'fail',
          read_test: data.read_test,
          write_test: data.write_test,
          duration_ms: duration,
          error: data.error,
        };

        setTestResults([...results]);
      } catch (error) {
        results[i] = {
          equipment_id: eqId,
          equipment_name: equipment?.name || eqId,
          status: 'fail',
          error: `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        };
        setTestResults([...results]);
      }

      // Add delay between tests
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    setIsRunning(false);
    setStep(3);
  };

  const passCount = testResults.filter((r) => r.status === 'pass').length;
  const failCount = testResults.filter((r) => r.status === 'fail').length;
  const canProceed = selectedEquipment.length >= 1 && selectedEquipment.length <= 10;

  return (
    <div className="max-w-2xl mx-auto">
      {/* Step Indicator */}
      <div className="flex items-center justify-center gap-4 mb-8">
        {[1, 2, 3].map((s) => (
          <React.Fragment key={s}>
            {s > 1 && (
              <div
                className={`h-1 w-8 rounded ${
                  s <= step ? 'bg-blue-500' : 'bg-gray-300'
                }`}
              />
            )}
            <div
              className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm transition-colors ${
                s === step
                  ? 'bg-blue-500 text-white'
                  : s < step
                    ? 'bg-green-500 text-white'
                    : 'bg-gray-200 text-gray-600'
              }`}
            >
              {s < step ? <CheckCircle className="w-5 h-5" /> : s}
            </div>
          </React.Fragment>
        ))}
      </div>

      {/* Step 1: Select Equipment */}
      {step === 1 && (
        <div className="space-y-5">
          <div>
            <h3 className="text-lg font-semibold mb-2">Select Equipment to Verify</h3>
            <p className="text-sm text-gray-600 mb-4">
              Test control and monitoring capabilities. Select 1-3 representative devices from
              different types.
            </p>
          </div>

          {/* Equipment List */}
          <div className="space-y-2 max-h-96 overflow-y-auto rounded-lg border border-gray-200">
            {equipmentList.map((equipment) => (
              <label
                key={equipment.id}
                className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50 transition-colors border-b border-gray-100 last:border-b-0"
              >
                <input
                  type="checkbox"
                  checked={selectedEquipment.includes(equipment.id)}
                  onChange={() => handleToggleEquipment(equipment.id)}
                  className="w-4 h-4 rounded"
                />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm truncate">{equipment.name}</div>
                  <div className="text-xs text-gray-500 space-x-2">
                    <span className="inline-block px-2 py-1 bg-gray-100 rounded">
                      {equipment.equipment_type}
                    </span>
                    {equipment.zone && (
                      <span className="inline-block px-2 py-1 bg-blue-100 text-blue-700 rounded">
                        {equipment.zone}
                      </span>
                    )}
                    {equipment.point_count && (
                      <span className="text-gray-500">{equipment.point_count} points</span>
                    )}
                  </div>
                </div>
              </label>
            ))}
          </div>

          {/* Helper buttons */}
          <div className="flex gap-2">
            <button
              onClick={handleSelectRandom}
              className="px-3 py-2 text-sm border border-blue-500 text-blue-500 rounded hover:bg-blue-50 transition-colors"
            >
              Suggest 3 Representative
            </button>
            <button
              onClick={() => setSelectedEquipment([])}
              className="px-3 py-2 text-sm border border-gray-300 text-gray-600 rounded hover:bg-gray-50 transition-colors"
            >
              Clear Selection
            </button>
          </div>

          {/* Selection summary */}
          {selectedEquipment.length > 0 && (
            <div className="p-3 bg-green-50 border border-green-200 rounded text-sm text-green-700">
              ✓ {selectedEquipment.length} equipment selected for testing
            </div>
          )}

          {/* Navigation */}
          <div className="flex justify-end gap-2 pt-4">
            <button
              onClick={onComplete}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded hover:bg-gray-50"
            >
              Skip Verification
            </button>
            <button
              onClick={() => setStep(2)}
              disabled={!canProceed}
              className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Run Tests <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Running Tests */}
      {step === 2 && (
        <div className="space-y-5">
          <div>
            <h3 className="text-lg font-semibold mb-2">Running Verification Tests</h3>
            <p className="text-sm text-gray-600">
              Testing read and write capabilities for each equipment...
            </p>
          </div>

          {/* Test Progress */}
          <div className="space-y-3">
            {testResults.map((result) => (
              <div
                key={result.equipment_id}
                className="p-4 border rounded-lg"
                style={{
                  borderColor:
                    result.status === 'pass'
                      ? '#10b981'
                      : result.status === 'fail'
                        ? '#ef4444'
                        : '#d1d5db',
                }}
              >
                <div className="flex items-center gap-3">
                  {result.status === 'pass' && (
                    <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />
                  )}
                  {result.status === 'fail' && (
                    <XCircle className="w-5 h-5 text-red-500 shrink-0" />
                  )}
                  {result.status === 'pending' && (
                    <Loader2 className="w-5 h-5 text-gray-400 animate-spin shrink-0" />
                  )}
                  <div className="flex-1">
                    <div className="font-medium text-sm">{result.equipment_name}</div>
                    {result.read_test && (
                      <div className="text-xs text-gray-600">
                        Read: {result.read_test.success ? '✓' : '✗'}{' '}
                        {result.read_test.points_read && `(${result.read_test.points_read} points)`}
                      </div>
                    )}
                    {result.write_test && (
                      <div className="text-xs text-gray-600">
                        Write: {result.write_test.success ? '✓' : '✗'}{' '}
                        {result.write_test.points_written &&
                          `(${result.write_test.points_written} points)`}
                      </div>
                    )}
                    {result.error && (
                      <div className="text-xs text-red-600">{result.error}</div>
                    )}
                  </div>
                  {result.duration_ms && (
                    <div className="text-xs text-gray-500">{result.duration_ms}ms</div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {isRunning && (
            <div className="text-center py-4">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-500" />
              <p className="text-sm text-gray-600">Testing equipment...</p>
            </div>
          )}
        </div>
      )}

      {/* Step 3: Results */}
      {step === 3 && (
        <div className="space-y-5">
          {/* Summary */}
          <div className="text-center py-6">
            {failCount === 0 ? (
              <>
                <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
                <h3 className="text-2xl font-bold text-green-700 mb-2">
                  All Tests Passed!
                </h3>
                <p className="text-gray-600">
                  {passCount}/{testResults.length} equipment verified successfully
                </p>
              </>
            ) : (
              <>
                <AlertTriangle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
                <h3 className="text-2xl font-bold text-yellow-700 mb-2">
                  {passCount} of {testResults.length} Tests Passed
                </h3>
                <p className="text-gray-600">
                  {failCount} equipment need attention
                </p>
              </>
            )}
          </div>

          {/* Results Table */}
          <div className="rounded-lg border border-gray-200 overflow-hidden">
            <div className="grid grid-cols-4 gap-4 p-4 bg-gray-50 font-semibold text-sm border-b border-gray-200">
              <div>Equipment</div>
              <div>Read</div>
              <div>Write</div>
              <div>Status</div>
            </div>
            {testResults.map((result) => (
              <div
                key={result.equipment_id}
                className="grid grid-cols-4 gap-4 p-4 border-b border-gray-100 text-sm last:border-b-0"
              >
                <div className="font-medium truncate">{result.equipment_name}</div>
                <div>
                  {result.read_test?.success ? (
                    <span className="text-green-600">✓</span>
                  ) : (
                    <span className="text-red-600">✗</span>
                  )}
                </div>
                <div>
                  {result.write_test?.success ? (
                    <span className="text-green-600">✓</span>
                  ) : (
                    <span className="text-red-600">✗</span>
                  )}
                </div>
                <div>
                  {result.status === 'pass' ? (
                    <span className="px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-medium">
                      Pass
                    </span>
                  ) : (
                    <span className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs font-medium">
                      Fail
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Failed equipment notes */}
          {failCount > 0 && (
            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded text-sm">
              <p className="font-semibold text-yellow-900 mb-2">⚠️ Troubleshooting Tips:</p>
              <ul className="text-yellow-800 space-y-1 ml-4 list-disc">
                <li>Check BMS connection credentials</li>
                <li>Verify network connectivity to BMS device</li>
                <li>Confirm equipment is powered on and responding</li>
                <li>Review equipment configuration in BMS</li>
                <li>Contact BMS administrator if issues persist</li>
              </ul>
            </div>
          )}

          {/* Navigation */}
          <div className="flex justify-between gap-2 pt-4">
            <button
              onClick={() => setStep(1)}
              className="flex items-center gap-2 px-4 py-2 text-sm border border-gray-300 text-gray-600 rounded hover:bg-gray-50"
            >
              <ChevronLeft className="w-4 h-4" /> Select Different Equipment
            </button>
            <button
              onClick={onComplete}
              className={`flex items-center gap-2 px-6 py-2 text-sm font-medium rounded text-white transition-colors ${
                failCount === 0
                  ? 'bg-green-500 hover:bg-green-600'
                  : 'bg-gray-500 hover:bg-gray-600'
              }`}
            >
              {failCount === 0 ? 'Complete Setup' : 'Proceed with Caution'}
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
