// FileUploadStep.tsx
import { useState, useCallback } from 'react';
import { Alert, Button, Callout, Title, Text } from '@tremor/react';
import { Upload } from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

interface FormatDetectionResult {
  file_format: 'csv' | 'excel' | 'json';
  delimiter: string;
  vendor: string;
  confidence: number;
  suggested_mappings: Record<string, string>;
  row_count: number;
}

export function FileUploadStep({
  buildingId: _buildingId,
  onNext
}: {
  buildingId: string;
  onNext: (data: { file: File; formatDetection: FormatDetectionResult }) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [result, setResult] = useState<FormatDetectionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      setFile(droppedFile);
      setResult(null);
      setError(null);
    }
  }, []);

  const handleSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setResult(null);
      setError(null);
    }
  }, []);

  const handleDetect = async () => {
    if (!file) return;

    setUploading(true);
    setDetecting(true);
    setError(null);

    try {
      // Upload file and detect format
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(
        `${API_BASE_URL}/api/integration/detect-format`,
        {
          method: 'POST',
          body: formData
        }
      );

      if (!response.ok) {
        throw new Error('Failed to detect format');
      }

      const detection: FormatDetectionResult = await response.json();
      setResult(detection);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Detection failed');
    } finally {
      setUploading(false);
      setDetecting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <Title>Upload Sample Log File</Title>
        <Text className="mt-2">
          Upload a sample BMS log file (CSV, Excel, or JSON) to auto-detect format and vendor.
        </Text>
      </div>

      {/* Upload area */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        className="border-2 border-dashed border-gray-300 rounded-lg p-12 text-center hover:border-blue-500 transition-colors"
      >
        <input
          type="file"
          onChange={handleSelect}
          accept=".csv,.xlsx,.xls,.json"
          className="hidden"
          id="file-upload"
        />
        <label htmlFor="file-upload" className="cursor-pointer">
          <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
          <p className="text-lg font-medium text-gray-700">
            Drop file here or click to upload
          </p>
          <p className="text-sm text-gray-500 mt-2">
            CSV, Excel, or JSON (max 10MB)
          </p>
        </label>
      </div>

      {/* Selected file */}
      {file && (
        <Callout title="Selected file" color="neutral">
          <p className="font-medium">{file.name}</p>
          <p className="text-sm text-gray-500">
            {(file.size / 1024).toFixed(2)} KB
          </p>
        </Callout>
      )}

      {/* Detection result */}
      {result && (
        <Alert title="Format Detected" color="success">
          <div className="mt-4 space-y-2">
            <p><strong>Format:</strong> {result.file_format.toUpperCase()}</p>
            <p><strong>Delimiter:</strong> "{result.delimiter}"</p>
            <p><strong>Vendor:</strong> {result.vendor}</p>
            <p><strong>Confidence:</strong> {(result.confidence * 100).toFixed(0)}%</p>
            <p><strong>Rows:</strong> {result.row_count.toLocaleString()}</p>
          </div>
        </Alert>
      )}

      {/* Error */}
      {error && (
        <Alert title="Error" color="red">{error}</Alert>
      )}

      {/* Actions */}
      <div className="flex justify-between">
        <Button
          onClick={handleDetect}
          disabled={!file || uploading || detecting}
          color="blue"
        >
          {detecting ? 'Detecting...' : uploading ? 'Uploading...' : 'Detect Format'}
        </Button>

        <Button
          onClick={() => {
            if (file && result) {
              onNext({ file, formatDetection: result });
            }
          }}
          disabled={!result}
          color="green"
        >
          Next: Map Columns
        </Button>
      </div>
    </div>
  );
}
