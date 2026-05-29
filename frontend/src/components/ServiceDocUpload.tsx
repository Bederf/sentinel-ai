/**
 * ServiceDocUpload - Document upload with metadata fields for Tech Chat
 *
 * Technicians upload service sheets / job cards with structured metadata:
 * - Equipment ID (which asset)
 * - Document type (service report, equipment manual, etc.)
 * - Vendor / service company
 * - Service date
 * - Title (auto-populated from filename)
 *
 * The metadata ensures documents are auto-linked to equipment for RAG citations.
 */

import { useEffect, useRef, useState } from 'react';
import { Paperclip, Loader, X, Upload, FileText, ChevronDown } from 'lucide-react';
import { documentsApi } from '@/lib/api/documents';
import { sitesApi } from '@/lib/api/sites';
import type { Equipment } from '@/lib/api/sites';

interface ServiceDocUploadProps {
  siteId: string;
  onUploadComplete?: (title: string) => void;
  onError?: (error: string) => void;
  disabled?: boolean;
}

const SUPPORTED_TYPES = ['.pdf', '.docx', '.txt'];
const MAX_SIZE_MB = 10;
const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

const DOCUMENT_TYPES = [
  { value: 'service_report', label: 'Service Report / Job Card' },
  { value: 'equipment_manual', label: 'Equipment Manual' },
  { value: 'maintenance_procedure', label: 'Maintenance Procedure' },
  { value: 'troubleshooting_guide', label: 'Troubleshooting Guide' },
  { value: 'technical_bulletin', label: 'Technical Bulletin' },
  { value: 'safety_procedure', label: 'Safety Procedure' },
];

export default function ServiceDocUpload({
  siteId,
  onUploadComplete,
  onError,
  disabled = false,
}: ServiceDocUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Equipment list for searchable dropdown
  const [equipmentList, setEquipmentList] = useState<Equipment[]>([]);
  const [equipmentSearch, setEquipmentSearch] = useState('');
  const [showEquipmentDropdown, setShowEquipmentDropdown] = useState(false);
  const equipmentDropdownRef = useRef<HTMLDivElement>(null);

  // Form fields
  const [title, setTitle] = useState('');
  const [equipmentId, setEquipmentId] = useState('');
  const [documentType, setDocumentType] = useState('service_report');
  const [vendor, setVendor] = useState('');
  const [serviceDate, setServiceDate] = useState('');

  // Fetch equipment list when form opens
  useEffect(() => {
    if (!showForm || !siteId || equipmentList.length > 0) return;
    sitesApi.getEquipment(siteId).then((res) => {
      setEquipmentList(res.equipment || []);
    }).catch(() => { /* silent — tech can still type manually */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showForm, siteId]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!showEquipmentDropdown) return;
    const handler = (e: MouseEvent) => {
      if (equipmentDropdownRef.current && !equipmentDropdownRef.current.contains(e.target as Node)) {
        setShowEquipmentDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showEquipmentDropdown]);

  const filteredEquipment = equipmentSearch
    ? equipmentList.filter(
        (eq) =>
          eq.code.toLowerCase().includes(equipmentSearch.toLowerCase()) ||
          eq.name.toLowerCase().includes(equipmentSearch.toLowerCase()) ||
          eq.equipment_type.toLowerCase().includes(equipmentSearch.toLowerCase())
      )
    : equipmentList;

  const resetForm = () => {
    setSelectedFile(null);
    setShowForm(false);
    setTitle('');
    setEquipmentId('');
    setEquipmentSearch('');
    setShowEquipmentDropdown(false);
    setDocumentType('service_report');
    setVendor('');
    setServiceDate('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const fileExt = `.${file.name.split('.').pop()?.toLowerCase() || ''}`;
    if (!SUPPORTED_TYPES.includes(fileExt)) {
      onError?.(`Invalid file type. Supported: ${SUPPORTED_TYPES.join(', ')}`);
      return;
    }
    if (file.size > MAX_SIZE_BYTES) {
      onError?.(`File too large. Maximum: ${MAX_SIZE_MB}MB`);
      return;
    }

    setSelectedFile(file);
    setTitle(file.name.replace(/\.[^.]+$/, ''));
    setShowForm(true);
  };

  const handleUpload = async () => {
    if (!selectedFile || !siteId) return;

    setUploading(true);
    try {
      const _response = await documentsApi.uploadDocument(
        siteId,
        selectedFile,
        title || undefined,
        documentType,
      );

      onUploadComplete?.(title || selectedFile.name);
      resetForm();
    } catch (err) {
      const msg = err instanceof Error ? err.message : typeof err === 'string' ? err : 'Upload failed';
      onError?.(msg);
    } finally {
      setUploading(false);
    }
  };

  // Collapsed state: just the paperclip button
  if (!showForm) {
    return (
      <>
        <input
          ref={fileInputRef}
          type="file"
          accept={SUPPORTED_TYPES.join(',')}
          onChange={handleFileSelect}
          disabled={disabled || uploading}
          className="hidden"
          aria-label="Upload service document"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploading || !siteId}
          className="flex-none p-2.5 rounded-lg transition-colors hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
          title="Upload service document"
          aria-label="Upload service document"
        >
          <Paperclip className="w-5 h-5 text-gray-500 dark:text-gray-400" />
        </button>
      </>
    );
  }

  // Expanded state: metadata form
  return (
    <div className="absolute bottom-full left-0 right-0 mb-2 mx-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg p-4 z-10">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-blue-600" />
          <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
            Upload Service Document
          </h4>
        </div>
        <button
          onClick={resetForm}
          className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
          aria-label="Cancel upload"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* Selected file */}
      <div className="flex items-center gap-2 mb-3 p-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
        <Paperclip className="w-4 h-4 text-gray-400 flex-none" />
        <span className="text-sm text-gray-700 dark:text-gray-300 truncate">
          {selectedFile?.name}
        </span>
        <span className="text-xs text-gray-400 flex-none">
          {selectedFile ? `${(selectedFile.size / 1024).toFixed(0)} KB` : ''}
        </span>
      </div>

      {/* Form fields - 2 column grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        {/* Title */}
        <div className="sm:col-span-2">
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Title
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Chiller Service Report – Jan 2026"
            className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Equipment Code — searchable dropdown */}
        <div ref={equipmentDropdownRef} className="relative">
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Equipment Code
          </label>
          <div className="relative">
            <input
              type="text"
              value={equipmentId ? equipmentId : equipmentSearch}
              onChange={(e) => {
                setEquipmentSearch(e.target.value);
                setEquipmentId('');
                setShowEquipmentDropdown(true);
              }}
              onFocus={() => setShowEquipmentDropdown(true)}
              placeholder="Type to search… e.g. chiller"
              className="w-full px-3 py-2 pr-8 text-sm bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {equipmentId && (
              <button
                type="button"
                onClick={() => { setEquipmentId(''); setEquipmentSearch(''); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                aria-label="Clear equipment"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
            {!equipmentId && (
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
            )}
          </div>
          {showEquipmentDropdown && filteredEquipment.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full max-h-40 overflow-y-auto bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg">
              {filteredEquipment.slice(0, 20).map((eq) => (
                <li key={eq.code}>
                  <button
                    type="button"
                    onClick={() => {
                      setEquipmentId(eq.code);
                      setEquipmentSearch('');
                      setShowEquipmentDropdown(false);
                    }}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 dark:hover:bg-gray-600 transition-colors"
                  >
                    <span className="font-medium text-gray-900 dark:text-white">{eq.code}</span>
                    <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">{eq.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Document Type */}
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Document Type
          </label>
          <select
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {DOCUMENT_TYPES.map((dt) => (
              <option key={dt.value} value={dt.value}>
                {dt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Vendor */}
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Vendor / Service Company
          </label>
          <input
            type="text"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            placeholder="e.g. CoolTech Services"
            className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Service Date */}
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Service Date
          </label>
          <input
            type="date"
            value={serviceDate}
            onChange={(e) => setServiceDate(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Upload button */}
      <button
        onClick={handleUpload}
        disabled={uploading || !selectedFile}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
      >
        {uploading ? (
          <>
            <Loader className="w-4 h-4 animate-spin" />
            Uploading & Indexing...
          </>
        ) : (
          <>
            <Upload className="w-4 h-4" />
            Upload & Index Document
          </>
        )}
      </button>

      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 text-center">
        PDF, DOCX, TXT up to {MAX_SIZE_MB}MB. Auto-indexed for AI search.
      </p>
    </div>
  );
}
