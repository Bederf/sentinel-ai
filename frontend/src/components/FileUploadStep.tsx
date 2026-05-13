// FileUploadStep.tsx
import { useState, useCallback } from 'react';

import { Upload } from 'lucide-react';
import { authorizedFetch } from '../lib/api/client';

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
  siteId: _siteId,
  onNext
}: {
  siteId: string;
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

      const response = await authorizedFetch(
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
        <h3 className="text-lg font-semibold" style={{ color: 'var(--color-sentinel-text-primary)' }}>Upload Sample Log File</h3>
        <p className="mt-2 text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
          Upload a sample BMS log file (CSV, Excel, or JSON) to auto-detect format and vendor.
        </p>
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
        <div className="p-3 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', borderLeft: '4px solid var(--color-sentinel-blue)' }}>
          <p className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>{file.name}</p>
          <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}>
            {(file.size / 1024).toFixed(2)} KB
          </p>
        </div>
      )}

      {/* Detection result */}
      {result && (
        <div className="p-3 rounded" style={{ background: 'var(--color-sentinel-bg-secondary)', border: '1px solid var(--color-sentinel-border)', borderLeft: '4px solid var(--color-sentinel-cyan)' }}>
          <p className="font-medium" style={{ color: 'var(--color-sentinel-text-primary)' }}>Format Detected</p>
          <div className="mt-4 space-y-2">
            <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}><strong>Format:</strong> {result.file_format.toUpperCase()}</p>
            <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}><strong>Delimiter:</strong> "{result.delimiter}"</p>
            <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}><strong>Vendor:</strong> {result.vendor}</p>
            <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}><strong>Confidence:</strong> {((result.confidence ?? 0) * 100).toFixed(0)}%</p>
            <p className="text-sm" style={{ color: 'var(--color-sentinel-text-secondary)' }}><strong>Rows:</strong> {result.row_count.toLocaleString()}</p>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 rounded" style={{ background: 'rgba(220, 38, 38, 0.15)', border: '1px solid rgba(220, 38, 38, 0.3)', borderLeft: '4px solid var(--color-sentinel-red)' }}>
          <p className="font-medium text-sm" style={{ color: 'var(--color-sentinel-red)' }}>Error</p>
          <p className="text-sm mt-1" style={{ color: 'var(--color-sentinel-text-secondary)' }}>{error}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between">
        <button
          onClick={handleDetect}
          disabled={!file || uploading || detecting}
          className="px-4 py-2 rounded text-sm font-medium transition-colors"
          style={{
            background: !file || uploading || detecting ? 'var(--color-sentinel-bg-secondary)' : 'var(--color-sentinel-blue)',
            color: !file || uploading || detecting ? 'var(--color-sentinel-text-disabled)' : '#fff',
            border: '1px solid var(--color-sentinel-border)',
            opacity: !file || uploading || detecting ? 0.5 : 1,
            cursor: !file || uploading || detecting ? 'not-allowed' : 'pointer',
          }}
        >
          {detecting ? 'Detecting...' : uploading ? 'Uploading...' : 'Detect Format'}
        </button>

        <button
          onClick={() => {
            if (file && result) {
              onNext({ file, formatDetection: result });
            }
          }}
          disabled={!result}
          className="px-4 py-2 rounded text-sm font-medium transition-colors"
          style={{
            background: !result ? 'var(--color-sentinel-bg-secondary)' : 'var(--color-sentinel-green)',
            color: !result ? 'var(--color-sentinel-text-disabled)' : '#fff',
            border: '1px solid var(--color-sentinel-border)',
            opacity: !result ? 0.5 : 1,
            cursor: !result ? 'not-allowed' : 'pointer',
          }}
        >
          Next: Map Columns
        </button>
      </div>
    </div>
  );
}
