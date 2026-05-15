/**
 * Document Upload Component - Upload equipment/service documentation
 *
 * Features:
 * - Side panel for document type selection (hardcoded options)
 * - Date field for document date
 * - File type validation (PDF, DOCX, TXT)
 * - File size validation (max 10MB)
 */

import { useEffect, useRef, useState } from 'react';
import { Paperclip, Loader, X, Calendar, FileText, Wrench } from 'lucide-react';
import { documentsApi } from '@/lib/api/documents';
import { workflowApi } from '@/lib/api/workflow';

const PRIORITY_EQUIPMENT_KEYWORDS = [
  'GEN', 'GENERATOR', 'AHU', 'FCU', 'CHILLER', 'PUMP',
  'UPS', 'BESS', 'INVERTER', 'BOILER', 'COOLING_TOWER', 'CT',
];

function isPriorityEquipmentType(type: string): boolean {
  const normalized = type.toUpperCase().replace(/[^A-Z0-9]/g, '');
  return PRIORITY_EQUIPMENT_KEYWORDS.some((keyword) =>
    normalized.includes(keyword.replace(/[^A-Z0-9]/g, ''))
  );
}

interface DocumentUploadProps {
  siteId: string;
  onUploadComplete?: () => void;
  onError?: (error: string) => void;
}

// Hardcoded document types matching backend TECHNICIAN_DOCUMENT_NAMES
const DOCUMENT_TYPES = [
  { value: 'Roof Guarantee Certificate', label: 'Roof Guarantee Certificate' },
  { value: 'Warranties', label: 'Warranties' },
  { value: 'Air-Handler Unit (AHU) Major Service', label: 'AHU Major Service' },
  { value: 'Air-Handler Unit (AHU) Minor Service', label: 'AHU Minor Service' },
  { value: 'Air-Handler Unit (AHU) Weekly Inspection', label: 'AHU Weekly Inspection' },
  { value: 'Cooling Tower (CT) Major Service', label: 'Cooling Tower Major Service' },
  { value: 'Cooling Tower (CT) Minor Service', label: 'Cooling Tower Minor Service' },
  { value: 'Chiller Major Service', label: 'Chiller Major Service' },
  { value: 'Chiller Minor Service', label: 'Chiller Minor Service' },
  { value: 'Fire Pump System Inspection', label: 'Fire Pump System Inspection' },
  { value: 'Generator Major Service', label: 'Generator Major Service' },
  { value: 'Generator Minor Service', label: 'Generator Minor Service' },
  { value: 'Generator Weekly Test', label: 'Generator Weekly Test' },
  { value: 'UPS Weekly Inspection', label: 'UPS Weekly Inspection' },
  { value: 'Certificate of Compliance (COC)', label: 'Certificate of Compliance' },
  { value: 'Electrical Equipment Certificates', label: 'Electrical Certificates' },
  { value: 'Building Inspection Report', label: 'Building Inspection Report' },
  { value: 'Plumbing Certificate of Compliance', label: 'Plumbing Certificate' },
] as const;

export type DocumentType = string;

export function DocumentUpload({
  siteId,
  onUploadComplete,
  onError,
}: DocumentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState<string>('');
  const [documentDate, setDocumentDate] = useState<string>('');
  const [equipmentList, setEquipmentList] = useState<{ equipment_id: string; name: string; type: string }[]>([]);
  const [selectedEquipment, setSelectedEquipment] = useState<string>('');
  const [loadingEquipment, setLoadingEquipment] = useState(false);

  const SUPPORTED_TYPES = ['.pdf', '.docx', '.txt'];
  const MAX_SIZE_MB = 10;
  const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

  // Fetch priority equipment list (same data as Maintenance page)
  useEffect(() => {
    if (!isPanelOpen || !siteId || equipmentList.length > 0) return;
    const fetchEquipment = async () => {
      setLoadingEquipment(true);
      try {
        const data = await workflowApi.getDashboardEquipment(siteId);
        const filtered = (data.equipment || []).filter((eq) => isPriorityEquipmentType(eq.type));
        setEquipmentList(filtered);
      } catch {
        setEquipmentList([]);
      } finally {
        setLoadingEquipment(false);
      }
    };
    fetchEquipment();
  }, [isPanelOpen, siteId, equipmentList.length]);

  const handleOpenPanel = () => {
    setIsPanelOpen(true);
    setError(null);
    setSuccess(null);
    setSelectedFile(null);
    setDocumentType('');
    setDocumentDate('');
    setSelectedEquipment('');
  };

  const handleClosePanel = () => {
    setIsPanelOpen(false);
    setError(null);
    setSuccess(null);
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const fileExt = `.${file.name.split('.').pop()?.toLowerCase() || ''}`;
    if (!SUPPORTED_TYPES.includes(fileExt)) {
      setError(`Invalid file type. Supported: ${SUPPORTED_TYPES.join(', ')}`);
      setSelectedFile(null);
      return;
    }

    if (file.size > MAX_SIZE_BYTES) {
      setError(`File too large. Maximum size: ${MAX_SIZE_MB}MB`);
      setSelectedFile(null);
      return;
    }

    setError(null);
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile || !documentType || !documentDate) {
      setError('Please fill in all fields');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const title = selectedEquipment
        ? `${selectedEquipment} - ${documentType}`
        : documentType;
      await documentsApi.uploadDocument(
        siteId,
        selectedFile,
        title,
        'service_report'
      );

      setSuccess(`Document uploaded successfully`);
      onUploadComplete?.();

      setTimeout(() => {
        handleClosePanel();
      }, 2000);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Upload failed';
      setError(errorMsg);
      onError?.(errorMsg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      {/* Upload button */}
      <button
        onClick={handleOpenPanel}
        className="px-2 py-1.5 rounded flex items-center gap-2 transition-all hover:brightness-110 hover:scale-105"
        style={{
          background: 'var(--color-grafana-bg-secondary)',
          border: '1px solid var(--color-grafana-border)',
          color: 'var(--color-grafana-text-secondary)',
        }}
        title={!siteId ? 'Select a building first' : 'Upload document'}
        aria-label="Upload document"
      >
        <Paperclip className="w-4 h-4" />
        <span className="text-xs hidden sm:inline">Upload</span>
      </button>

      {/* Side panel overlay */}
      {isPanelOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            style={{ background: 'rgba(0, 0, 0, 0.5)' }}
            onClick={handleClosePanel}
          />

          {/* Side panel */}
          <div
            className="fixed top-0 right-0 h-full z-50 flex flex-col"
            style={{
              width: '400px',
              maxWidth: '90vw',
              background: 'var(--color-grafana-bg-panel)',
              borderLeft: '1px solid var(--color-grafana-border)',
            }}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between p-4"
              style={{ borderBottom: '1px solid var(--color-grafana-border)' }}
            >
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5" style={{ color: 'var(--color-sentinel-amber)' }} />
                <h2 className="font-semibold" style={{ color: 'var(--color-grafana-text-primary)' }}>
                  Upload Document
                </h2>
              </div>
              <button
                onClick={handleClosePanel}
                className="p-1 rounded hover:brightness-110"
                aria-label="Close panel"
              >
                <X className="w-5 h-5" style={{ color: 'var(--color-grafana-text-secondary)' }} />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Document Type Selection */}
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--color-grafana-text-secondary)' }}
                >
                  Document Type
                </label>
                <select
                  value={documentType}
                  onChange={(e) => setDocumentType(e.target.value)}
                  className="w-full px-3 py-2 rounded border"
                  style={{
                    background: 'var(--color-grafana-bg-secondary)',
                    borderColor: 'var(--color-grafana-border)',
                    color: 'var(--color-grafana-text-primary)',
                  }}
                >
                  <option value="">Select document type...</option>
                  {DOCUMENT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Equipment Selection (same list as Maintenance page) */}
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--color-grafana-text-secondary)' }}
                >
                  Equipment
                </label>
                <div className="relative">
                  <Wrench
                    className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                    style={{ color: 'var(--color-grafana-text-disabled)' }}
                  />
                  <select
                    value={selectedEquipment}
                    onChange={(e) => setSelectedEquipment(e.target.value)}
                    className="w-full pl-10 pr-3 py-2 rounded border"
                    style={{
                      background: 'var(--color-grafana-bg-secondary)',
                      borderColor: 'var(--color-grafana-border)',
                      color: loadingEquipment
                        ? 'var(--color-grafana-text-disabled)'
                        : 'var(--color-grafana-text-primary)',
                    }}
                    disabled={loadingEquipment}
                  >
                    <option value="">
                      {loadingEquipment ? 'Loading equipment...' : 'Select equipment (optional)'}
                    </option>
                    {equipmentList.map((eq) => (
                      <option key={eq.equipment_id} value={eq.equipment_id}>
                        {eq.equipment_id} — {eq.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Document Date */}
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--color-grafana-text-secondary)' }}
                >
                  Document Date
                </label>
                <div className="relative">
                  <Calendar
                    className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                    style={{ color: 'var(--color-grafana-text-disabled)' }}
                  />
                  <input
                    type="date"
                    value={documentDate}
                    onChange={(e) => setDocumentDate(e.target.value)}
                    className="w-full pl-10 pr-3 py-2 rounded border"
                    style={{
                      background: 'var(--color-grafana-bg-secondary)',
                      borderColor: 'var(--color-grafana-border)',
                      color: 'var(--color-grafana-text-primary)',
                    }}
                  />
                </div>
              </div>

              {/* File Selection */}
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--color-grafana-text-secondary)' }}
                >
                  File (PDF, DOCX, TXT - max 10MB)
                </label>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={SUPPORTED_TYPES.join(',')}
                  onChange={handleFileChange}
                  className="hidden"
                  aria-label="Document file input"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full px-4 py-3 rounded border-2 border-dashed text-center transition-all hover:brightness-110"
                  style={{
                    borderColor: selectedFile
                      ? 'var(--color-sentinel-amber)'
                      : 'var(--color-grafana-border)',
                    background: 'var(--color-grafana-bg-secondary)',
                    color: selectedFile
                      ? 'var(--color-grafana-text-primary)'
                      : 'var(--color-grafana-text-disabled)',
                  }}
                >
                  {selectedFile ? (
                    <div>
                      <Paperclip className="w-5 h-5 mx-auto mb-1" style={{ color: 'var(--color-sentinel-amber)' }} />
                      <span className="text-sm font-medium">{selectedFile.name}</span>
                      <span className="text-xs block mt-1">
                        ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
                      </span>
                    </div>
                  ) : (
                    <div>
                      <Paperclip className="w-5 h-5 mx-auto mb-1" />
                      <span className="text-sm">Click to select file</span>
                    </div>
                  )}
                </button>
              </div>

              {/* Error message */}
              {error && (
                <div
                  className="text-sm rounded p-3"
                  style={{
                    background: 'rgba(210, 15, 57, 0.1)',
                    border: '1px solid rgb(210, 15, 57)',
                    color: 'rgb(210, 15, 57)',
                  }}
                >
                  {error}
                </div>
              )}

              {/* Success message */}
              {success && (
                <div
                  className="text-sm rounded p-3"
                  style={{
                    background: 'rgba(87, 148, 26, 0.1)',
                    border: '1px solid rgb(87, 148, 26)',
                    color: 'rgb(87, 148, 26)',
                  }}
                >
                  {success}
                </div>
              )}
            </div>

            {/* Footer with Upload button */}
            <div
              className="p-4"
              style={{ borderTop: '1px solid var(--color-grafana-border)' }}
            >
              <button
                onClick={handleUpload}
                disabled={uploading || !selectedFile || !documentType || !documentDate}
                className="w-full py-3 rounded font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:brightness-110 flex items-center justify-center gap-2"
                style={{
                  background: uploading
                    ? 'var(--color-grafana-border)'
                    : 'var(--color-sentinel-blue)',
                  color: 'white',
                }}
              >
                {uploading ? (
                  <>
                    <Loader className="w-4 h-4 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Paperclip className="w-4 h-4" />
                    Upload Document
                  </>
                )}
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

export default DocumentUpload;
