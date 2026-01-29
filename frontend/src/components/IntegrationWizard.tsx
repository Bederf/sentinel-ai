// IntegrationWizard.tsx
import { useState } from 'react';
import { Card } from '@tremor/react';
import { FileUploadStep } from './FileUploadStep';
import { ColumnMappingStep } from './ColumnMappingStep';
import { PointMatchingStep } from './PointMatchingStep';

interface FormatDetectionResult {
  file_format: 'csv' | 'excel' | 'json';
  delimiter: string;
  vendor: string;
  confidence: number;
  suggested_mappings: Record<string, string>;
  row_count: number;
}

type WizardStep = 'upload' | 'mapping' | 'matching' | 'review';

export function IntegrationWizard({ buildingId, onClose, onComplete: _onComplete }: {
  buildingId: string;
  onClose: () => void;
  onComplete: () => void;
}) {
  const [currentStep, setCurrentStep] = useState<WizardStep>('upload');
  const [wizardData, setWizardData] = useState<{
    file: File | null;
    formatDetection: FormatDetectionResult | null;
    columnMappings: Record<string, any>;
    pointMatches: any[];
    syncSettings: Record<string, any>;
  }>({
    file: null,
    formatDetection: null,
    columnMappings: {},
    pointMatches: [],
    syncSettings: {}
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
          buildingId={buildingId}
          onNext={(data) => {
            setWizardData({ ...wizardData, ...data });
            setCurrentStep('mapping');
          }}
        />
      )}

      {currentStep === 'mapping' && (
        <ColumnMappingStep
          buildingId={buildingId}
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
          buildingId={buildingId}
          columnMappings={wizardData.columnMappings}
          onNext={(data) => {
            setWizardData({ ...wizardData, ...data });
            setCurrentStep('review');
          }}
          onBack={() => setCurrentStep('mapping')}
        />
      )}

      {/* Navigation buttons */}
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
    </Card>
  );
}
