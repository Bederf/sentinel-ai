/**
 * ConceptDocumentUpload
 *
 * Uploads a document to the Concept MRI DMS with mandatory F1-F8
 * controlled fields enforced at the point of upload.
 *
 * SEPARATE from DocumentUpload.tsx — that component feeds the system
 * document RAG. This component feeds the Concept DMS / advanced RAG
 * pipeline for properly onboarded sites.
 *
 * Dropdown values are fetched from GET /api/concept/documents/fields
 * so they stay in sync with the backend register automatically.
 */

import { useEffect, useRef, useState } from 'react';
import { Paperclip, Loader, X, Calendar, FileText, AlertCircle } from 'lucide-react';
import { conceptDocumentsApi } from '@/lib/api/conceptDocuments';
import type { ConceptDocumentFieldOptions } from '@/lib/api/conceptDocuments';

// Trigger types that require a trigger_date (Vital records)
const VITAL_TRIGGER_TYPES = new Set([
  'Certificate / Permit Expiry Date',
  'Equipment Decommission Date',
  'Building Demolition / Disposal Date',
  'Lease Termination Date',
  'Installation Decommission Date',
  'Vessel Decommission Date',
  'Tank Decommission Date',
  'Date Survey Issued',
  'Date of Incident',
]);

interface ConceptDocumentUploadProps {
  siteId: string;
  onUploadComplete?: () => void;
  onError?: (error: string) => void;
}

const SUPPORTED_TYPES = ['.pdf', '.docx', '.xlsx', '.txt'];
const MAX_SIZE_MB = 20;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

export function ConceptDocumentUpload({
  siteId,
  onUploadComplete,
  onError,
}: ConceptDocumentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [fieldOptions, setFieldOptions] = useState<ConceptDocumentFieldOptions | null>(null);
  const [loadingFields, setLoadingFields] = useState(false);

  // Form state — F1-F8
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [discipline, setDiscipline] = useState('');            // F2
  const [documentType, setDocumentType] = useState('');        // F3
  const [frequency, setFrequency] = useState('');              // F4
  const [documentCreationDate, setDocumentCreationDate] = useState(''); // F5 — no default (POPIA)
  const [triggerType, setTriggerType] = useState('Same as Document Creation Date'); // F6
  const [triggerDate, setTriggerDate] = useState('');          // F6 date

  const isVitalRecord = VITAL_TRIGGER_TYPES.has(triggerType);

  // Fetch approved dropdown values from the backend register
  useEffect(() => {
    if (!isPanelOpen || fieldOptions) return;
    const fetchFields = async () => {
      setLoadingFields(true);
      try {
        const data = await conceptDocumentsApi.getUploadFields();
        setFieldOptions(data);
      } catch {
        setError('Could not load document field options. Please try again.');
      } finally {
        setLoadingFields(false);
      }
    };
    fetchFields();
  }, [isPanelOpen, fieldOptions]);

  const resetForm = () => {
    setSelectedFile(null);
    setDiscipline('');
    setDocumentType('');
    setFrequency('');
    setDocumentCreationDate('');
    setTriggerType('Same as Document Creation Date');
    setTriggerDate('');
    setError(null);
    setSuccess(null);
  };

  const handleOpenPanel = () => {
    resetForm();
    setIsPanelOpen(true);
  };

  const handleClosePanel = () => {
    setIsPanelOpen(false);
    resetForm();
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const fileExt = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
    if (!SUPPORTED_TYPES.includes(fileExt)) {
      setError(`Unsupported file type. Accepted: ${SUPPORTED_TYPES.join(', ')}`);
      setSelectedFile(null);
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      setError(`File too large. Maximum: ${MAX_SIZE_MB}MB`);
      setSelectedFile(null);
      return;
    }
    setError(null);
    setSelectedFile(file);
  };

  const isFormValid =
    selectedFile &&
    discipline &&
    documentType &&
    frequency &&
    documentCreationDate &&
    (!isVitalRecord || triggerDate);

  const handleUpload = async () => {
    if (!isFormValid || !selectedFile) {
      setError('Please complete all required fields before uploading.');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      await conceptDocumentsApi.uploadDocument(selectedFile, {
        site_id: siteId,
        discipline,
        document_type: documentType,
        frequency,
        document_creation_date: documentCreationDate,
        trigger_type: triggerType,
        trigger_date: isVitalRecord && triggerDate ? triggerDate : null,
      });
      setSuccess('Document uploaded successfully.');
      onUploadComplete?.();
      setTimeout(() => handleClosePanel(), 2000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed';
      setError(msg);
      onError?.(msg);
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      {/* Trigger button */}
      <button
        onClick={handleOpenPanel}
        disabled={!siteId}
        className="px-2 py-1.5 rounded flex items-center gap-2 transition-all hover:brightness-110 hover:scale-105 disabled:opacity-40 disabled:cursor-not-allowed"
        style={{
          background: 'var(--color-sentinel-bg-secondary)',
          border: '1px solid var(--color-sentinel-border)',
          color: 'var(--color-sentinel-text-secondary)',
        }}
        title={!siteId ? 'Select a site first' : 'Upload compliance document to Concept'}
        aria-label="Upload Concept document"
      >
        <Paperclip className="w-4 h-4" />
        <span className="text-xs hidden sm:inline">Upload Doc</span>
      </button>

      {/* Panel */}
      {isPanelOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            style={{ background: 'rgba(0,0,0,0.5)' }}
            onClick={handleClosePanel}
          />

          {/* Side panel */}
          <div
            className="fixed top-0 right-0 h-full z-50 flex flex-col overflow-hidden"
            style={{
              width: '420px',
              maxWidth: '95vw',
              background: 'var(--color-sentinel-bg-panel)',
              borderLeft: '1px solid var(--color-sentinel-border)',
            }}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between p-4 shrink-0"
              style={{ borderBottom: '1px solid var(--color-sentinel-border)' }}
            >
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5" style={{ color: 'var(--color-sentinel-blue)' }} />
                <div>
                  <h2 className="font-semibold text-sm" style={{ color: 'var(--color-sentinel-text-primary)' }}>
                    Upload Compliance Document
                  </h2>
                  <p className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                    All fields are mandatory
                  </p>
                </div>
              </div>
              <button onClick={handleClosePanel} className="p-1 rounded hover:brightness-110" aria-label="Close">
                <X className="w-5 h-5" style={{ color: 'var(--color-sentinel-text-secondary)' }} />
              </button>
            </div>

            {/* Form */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {loadingFields ? (
                <div className="flex items-center justify-center py-8 gap-2" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                  <Loader className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Loading field options...</span>
                </div>
              ) : (
                <>
                  {/* F2 — Discipline */}
                  <Field label="Discipline" required>
                    <Select
                      value={discipline}
                      onChange={setDiscipline}
                      placeholder="Select discipline..."
                      options={fieldOptions?.discipline ?? []}
                    />
                  </Field>

                  {/* F3 — Document Type */}
                  <Field label="Document Type" required>
                    <Select
                      value={documentType}
                      onChange={setDocumentType}
                      placeholder="Select document type..."
                      options={fieldOptions?.document_type ?? []}
                    />
                  </Field>

                  {/* F4 — Frequency */}
                  <Field label="Inspection / Service Frequency" required>
                    <Select
                      value={frequency}
                      onChange={setFrequency}
                      placeholder="Select frequency..."
                      options={fieldOptions?.frequency ?? []}
                    />
                  </Field>

                  {/* F5 — Document Creation Date */}
                  <Field
                    label="Document Creation Date"
                    required
                    hint="The actual date of the activity — not today's upload date."
                  >
                    <div className="relative">
                      <Calendar
                        className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                        style={{ color: 'var(--color-sentinel-text-disabled)' }}
                      />
                      <input
                        type="date"
                        value={documentCreationDate}
                        onChange={(e) => setDocumentCreationDate(e.target.value)}
                        max={new Date().toISOString().split('T')[0]}
                        className="w-full pl-10 pr-3 py-2 rounded border text-sm"
                        style={{
                          background: 'var(--color-sentinel-bg-secondary)',
                          borderColor: 'var(--color-sentinel-border)',
                          color: 'var(--color-sentinel-text-primary)',
                        }}
                      />
                    </div>
                  </Field>

                  {/* F6 — Trigger Type */}
                  <Field label="Retention Trigger Type" required>
                    <Select
                      value={triggerType}
                      onChange={setTriggerType}
                      placeholder="Select trigger type..."
                      options={fieldOptions?.trigger_type ?? []}
                    />
                  </Field>

                  {/* F6 — Trigger Date (Vital records only) */}
                  {isVitalRecord && (
                    <Field
                      label="Trigger Date"
                      required
                      hint="Required for Vital records. Retention clock starts on this date."
                    >
                      <div className="relative">
                        <Calendar
                          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                          style={{ color: 'var(--color-sentinel-amber)' }}
                        />
                        <input
                          type="date"
                          value={triggerDate}
                          onChange={(e) => setTriggerDate(e.target.value)}
                          className="w-full pl-10 pr-3 py-2 rounded border text-sm"
                          style={{
                            background: 'var(--color-sentinel-bg-secondary)',
                            borderColor: 'var(--color-sentinel-amber)',
                            color: 'var(--color-sentinel-text-primary)',
                          }}
                        />
                      </div>
                    </Field>
                  )}

                  {/* File */}
                  <Field label={`File (${SUPPORTED_TYPES.join(', ')} — max ${MAX_SIZE_MB}MB)`} required>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept={SUPPORTED_TYPES.join(',')}
                      onChange={handleFileChange}
                      className="hidden"
                      aria-label="Document file"
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full px-4 py-3 rounded border-2 border-dashed text-center transition-all hover:brightness-110"
                      style={{
                        borderColor: selectedFile
                          ? 'var(--color-sentinel-blue)'
                          : 'var(--color-sentinel-border)',
                        background: 'var(--color-sentinel-bg-secondary)',
                        color: selectedFile
                          ? 'var(--color-sentinel-text-primary)'
                          : 'var(--color-sentinel-text-disabled)',
                      }}
                    >
                      {selectedFile ? (
                        <div>
                          <Paperclip className="w-5 h-5 mx-auto mb-1" style={{ color: 'var(--color-sentinel-blue)' }} />
                          <span className="text-sm font-medium block">{selectedFile.name}</span>
                          <span className="text-xs block mt-0.5">
                            {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                          </span>
                        </div>
                      ) : (
                        <div>
                          <Paperclip className="w-5 h-5 mx-auto mb-1" />
                          <span className="text-sm">Click to select file</span>
                        </div>
                      )}
                    </button>
                  </Field>

                  {/* F7 / F8 note */}
                  <p className="text-xs" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
                    Uploaded by is recorded automatically from your session.
                    Retention period is calculated from discipline + document type + frequency.
                  </p>
                </>
              )}

              {/* Error */}
              {error && (
                <div
                  className="flex items-start gap-2 text-sm rounded p-3"
                  style={{
                    background: 'rgba(210,15,57,0.1)',
                    border: '1px solid rgb(210,15,57)',
                    color: 'rgb(210,15,57)',
                  }}
                >
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              {/* Success */}
              {success && (
                <div
                  className="text-sm rounded p-3"
                  style={{
                    background: 'rgba(87,148,26,0.1)',
                    border: '1px solid rgb(87,148,26)',
                    color: 'rgb(87,148,26)',
                  }}
                >
                  {success}
                </div>
              )}
            </div>

            {/* Footer */}
            <div
              className="p-4 shrink-0"
              style={{ borderTop: '1px solid var(--color-sentinel-border)' }}
            >
              <button
                onClick={handleUpload}
                disabled={uploading || !isFormValid}
                className="w-full py-3 rounded font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:brightness-110 flex items-center justify-center gap-2"
                style={{
                  background: uploading ? 'var(--color-sentinel-border)' : 'var(--color-sentinel-blue)',
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        className="block text-sm font-medium mb-1"
        style={{ color: 'var(--color-sentinel-text-secondary)' }}
      >
        {label}
        {required && <span style={{ color: 'var(--color-sentinel-amber)' }}> *</span>}
      </label>
      {hint && (
        <p className="text-xs mb-2" style={{ color: 'var(--color-sentinel-text-disabled)' }}>
          {hint}
        </p>
      )}
      {children}
    </div>
  );
}

function Select({
  value,
  onChange,
  placeholder,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 rounded border text-sm"
      style={{
        background: 'var(--color-sentinel-bg-secondary)',
        borderColor: 'var(--color-sentinel-border)',
        color: value ? 'var(--color-sentinel-text-primary)' : 'var(--color-sentinel-text-disabled)',
      }}
    >
      <option value="">{placeholder}</option>
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </select>
  );
}

export default ConceptDocumentUpload;
