// IntegrationWizard.tsx
import { useState } from 'react';
import { Button, Card, Title, Text, Callout } from '@tremor/react';
import { CheckCircle } from 'lucide-react';
import { authorizedFetch } from '../lib/api/client';
import { FileUploadStep } from './FileUploadStep';
import { ColumnMappingStep } from './ColumnMappingStep';
import { PointMatchingStep } from './PointMatchingStep';

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

interface FormatDetectionResult {
  file_format: 'csv' | 'excel' | 'json';
  delimiter: string;
  vendor: string;
  confidence: number;
  suggested_mappings: Record<string, string>;
  row_count: number;
}

type WizardStep = 'upload' | 'mapping' | 'matching' | 'review';

interface ReviewStepProps {
  siteId: string;
  wizardData: {
    file: File | null;
    formatDetection: FormatDetectionResult | null;
    columnMappings: Record<string, any>;
    pointMatches: any[];
    syncSettings: {
      poll_frequency_minutes: number;
      store_raw_days: number;
      store_aggregated_years: number;
    };
  };
  onActivate: () => Promise<void>;
  onBack: () => void;
}

function ReviewStep({ siteId, wizardData, onActivate, onBack }: ReviewStepProps) {
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleActivate = async () => {
    setActivating(true);
    setError(null);
    try {
      await onActivate();
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activation failed');
    } finally {
      setActivating(false);
    }
  };

  if (success) {
    return (
      <div className="space-y-6 text-center">
        <div className="flex justify-center">
          <CheckCircle className="w-16 h-16 text-green-500" />
        </div>
        <Title>Integration Activated!</Title>
        <Text>
          Your BMS integration has been successfully configured and activated.
          Data sync will begin according to your settings.
        </Text>
        <div className="bg-gray-50 rounded-lg p-4 mt-4 text-left">
          <Title className="text-lg">Configuration Summary</Title>
          <div className="mt-4 space-y-2 text-sm">
            <p><strong>Building ID:</strong> {siteId}</p>
            <p><strong>File:</strong> {wizardData.file?.name}</p>
            <p><strong>Format:</strong> {wizardData.formatDetection?.file_format.toUpperCase()}</p>
            <p><strong>Vendor:</strong> {wizardData.formatDetection?.vendor}</p>
            <p><strong>Points Matched:</strong> {wizardData.pointMatches.length}</p>
            <p><strong>Poll Frequency:</strong> {wizardData.syncSettings.poll_frequency_minutes} minutes</p>
            <p><strong>Data Retention:</strong> {wizardData.syncSettings.store_raw_days} days (raw), {wizardData.syncSettings.store_aggregated_years} years (aggregated)</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Title>Review & Activate Integration</Title>
        <Text className="mt-2">
          Review your integration configuration before activating. You can go back to make changes if needed.
        </Text>
      </div>

      {/* Summary Card */}
      <Card className="p-4">
        <Title className="text-lg">Configuration Summary</Title>
        <div className="mt-4 space-y-4">
          <div>
            <h3 className="font-medium text-gray-700">Source File</h3>
            <p className="text-sm text-gray-600">{wizardData.file?.name}</p>
          </div>

          <div>
            <h3 className="font-medium text-gray-700">Format Detection</h3>
            <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
              <div><strong>Format:</strong> {wizardData.formatDetection?.file_format.toUpperCase()}</div>
              <div><strong>Vendor:</strong> {wizardData.formatDetection?.vendor}</div>
              <div><strong>Delimiter:</strong> "{wizardData.formatDetection?.delimiter}"</div>
              <div><strong>Rows:</strong> {wizardData.formatDetection?.row_count.toLocaleString()}</div>
            </div>
          </div>

          <div>
            <h3 className="font-medium text-gray-700">Point Matching</h3>
            <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
              <div><strong>Total Points:</strong> {wizardData.pointMatches.length}</div>
              <div><strong>Matched:</strong> {wizardData.pointMatches.filter((m: any) => m.asset_id).length}</div>
              <div><strong>High Confidence:</strong> {wizardData.pointMatches.filter((m: any) => m.confidence === 'high').length}</div>
              <div><strong>Medium/Low:</strong> {wizardData.pointMatches.filter((m: any) => m.confidence !== 'high').length}</div>
            </div>
          </div>

          <div>
            <h3 className="font-medium text-gray-700">Sync Settings</h3>
            <div className="grid grid-cols-2 gap-2 mt-2 text-sm">
              <div><strong>Poll Frequency:</strong> {wizardData.syncSettings.poll_frequency_minutes} minutes</div>
              <div><strong>Store Raw:</strong> {wizardData.syncSettings.store_raw_days} days</div>
              <div><strong>Store Aggregated:</strong> {wizardData.syncSettings.store_aggregated_years} years</div>
            </div>
          </div>
        </div>
      </Card>

      {/* Error */}
      {error && (
        <Callout title="Error" color="rose">{error}</Callout>
      )}

      {/* Warning callout */}
      <Callout title="Before you activate" color="yellow">
        <ul className="list-disc list-inside text-sm space-y-1 mt-2">
          <li>Ensure your file contains at least 30 days of historical data for best results</li>
          <li>Verify that high-confidence matches look correct</li>
          <li>Review unmatched points and manually match critical assets</li>
          <li>Check that sync settings align with your data retention policies</li>
        </ul>
      </Callout>

      {/* Actions */}
      <div className="flex justify-between">
        <Button onClick={onBack} variant="secondary" color="gray" disabled={activating}>
          Back
        </Button>

        <Button
          onClick={handleActivate}
          disabled={activating}
          color="green"
        >
          {activating ? 'Activating...' : 'Activate Integration'}
        </Button>
      </div>
    </div>
  );
}


export function IntegrationWizard({ siteId, onClose, onComplete: _onComplete }: {
  siteId: string;
  onClose: () => void;
  onComplete: () => void;
}) {
  const [currentStep, setCurrentStep] = useState<WizardStep>('upload');
  const [wizardData, setWizardData] = useState<{
    file: File | null;
    formatDetection: FormatDetectionResult | null;
    columnMappings: Record<string, any>;
    pointMatches: any[];
    syncSettings: {
      poll_frequency_minutes: number;
      store_raw_days: number;
      store_aggregated_years: number;
    };
  }>({
    file: null,
    formatDetection: null,
    columnMappings: {},
    pointMatches: [],
    syncSettings: {
      poll_frequency_minutes: 5,
      store_raw_days: 90,
      store_aggregated_years: 2
    }
  });

  const steps = [
    { id: 'upload', title: 'Upload File', description: 'Upload sample log file' },
    { id: 'mapping', title: 'Map Columns', description: 'Configure field mappings' },
    { id: 'matching', title: 'Match Points', description: 'Link BMS points to assets' },
    { id: 'review', title: 'Review', description: 'Review and activate' }
  ];

  const currentStepIndex = steps.findIndex(s => s.id === currentStep);

  return (
    <Card className="p-6 max-w-4xl mx-auto">
      {/* Progress stepper */}
      <div className="mb-8">
        <div className="flex items-center justify-between">
          {steps.map((step, index) => (
            <div key={step.id} className="flex items-center flex-1">
              <div className={`flex flex-col items-center ${
                index <= currentStepIndex ? 'text-blue-500' : 'text-gray-400'
              }`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 ${
                  index <= currentStepIndex
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-300'
                }`}>
                  {index + 1}
                </div>
                <span className="text-xs mt-1 text-center">{step.title}</span>
                <span className="text-xs mt-0.5 text-center opacity-75">{step.description}</span>
              </div>
              {index < steps.length - 1 && (
                <div className={`flex-1 h-0.5 mx-2 ${
                  index < currentStepIndex ? 'bg-blue-500' : 'bg-gray-300'
                }`} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Step content */}
      {currentStep === 'upload' && (
        <FileUploadStep
          siteId={siteId}
          onNext={(data) => {
            setWizardData({ ...wizardData, ...data });
            setCurrentStep('mapping');
          }}
        />
      )}

      {currentStep === 'mapping' && wizardData.formatDetection && (
        <ColumnMappingStep
          siteId={siteId}
          formatDetection={wizardData.formatDetection}
          onNext={(data) => {
            setWizardData({ ...wizardData, ...data });
            setCurrentStep('matching');
          }}
          onBack={() => setCurrentStep('upload')}
        />
      )}

      {currentStep === 'matching' && (
        <PointMatchingStep
          siteId={siteId}
          columnMappings={[]}
          onNext={(data) => {
            setWizardData({ ...wizardData, ...data });
            setCurrentStep('review');
          }}
          onBack={() => setCurrentStep('mapping')}
        />
      )}

      {currentStep === 'review' && (
        <ReviewStep
          siteId={siteId}
          wizardData={wizardData}
          onActivate={async () => {
            // Activate integration
            const response = await authorizedFetch(`${API_BASE_URL}/api/integration/ingest`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                site_id: siteId,
                log_source_id: 'temp-source-id',
                dry_run: false,
                sync_settings: wizardData.syncSettings
              })
            });

            if (!response.ok) {
              throw new Error('Failed to activate integration');
            }
          }}
          onBack={() => setCurrentStep('matching')}
        />
      )}

      {/* Navigation buttons - hide on review step (handled internally) */}
      {currentStep !== 'review' && (
        <div className="flex justify-between mt-6 pt-6 border-t">
          {currentStep !== 'upload' && (
            <button
              onClick={() => {
                const stepOrder: WizardStep[] = ['upload', 'mapping', 'matching', 'review'];
                const idx = stepOrder.indexOf(currentStep);
                setCurrentStep(stepOrder[idx - 1]);
              }}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Back
            </button>
          )}
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-600 hover:text-gray-800 ml-auto"
          >
            Cancel
          </button>
        </div>
      )}
    </Card>
  );
}
