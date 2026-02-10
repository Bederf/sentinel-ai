/**
 * Document Upload Component - Upload building-specific documentation
 *
 * Features:
 * - File type validation (PDF, DOCX, TXT)
 * - File size validation (max 10MB)
 * - Upload progress indicator
 * - Success/error messages via toast
 */

import { useRef, useState } from 'react';
import { Paperclip, Loader } from 'lucide-react';
import { documentsApi } from '@/lib/api/documents';

interface DocumentUploadProps {
  buildingId: string;
  onUploadComplete?: () => void;
  onError?: (error: string) => void;
}

export function DocumentUpload({
  buildingId,
  onUploadComplete,
  onError,
}: DocumentUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const SUPPORTED_TYPES = ['.pdf', '.docx', '.txt'];
  const MAX_SIZE_MB = 10;
  const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

  const handleFileClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Reset previous messages
    setError(null);
    setSuccess(null);

    // Validate file type
    const fileExt = `.${file.name.split('.').pop()?.toLowerCase() || ''}`;
    if (!SUPPORTED_TYPES.includes(fileExt)) {
      const errorMsg = `Invalid file type. Supported: ${SUPPORTED_TYPES.join(', ')}`;
      setError(errorMsg);
      onError?.(errorMsg);
      return;
    }

    // Validate file size
    if (file.size > MAX_SIZE_BYTES) {
      const errorMsg = `File too large. Maximum size: ${MAX_SIZE_MB}MB`;
      setError(errorMsg);
      onError?.(errorMsg);
      return;
    }

    // Upload file
    setUploading(true);
    try {
      const response = await documentsApi.uploadDocument(
        buildingId,
        file,
        undefined, // Use filename as title
        'building_manual'
      );

      const successMsg = `Document uploaded successfully (${response.chunk_count} chunks indexed)`;
      setSuccess(successMsg);
      onUploadComplete?.();

      // Clear success message after 5 seconds
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Upload failed';
      setError(errorMsg);
      onError?.(errorMsg);
    } finally {
      setUploading(false);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept={SUPPORTED_TYPES.join(',')}
        onChange={handleFileChange}
        disabled={uploading}
        className="hidden"
        aria-label="Document file input"
      />

      {/* Upload button */}
      <button
        onClick={handleFileClick}
        disabled={uploading || !buildingId}
        className="px-2 py-1.5 rounded flex items-center gap-2 transition-all hover:brightness-110 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:brightness-100 disabled:hover:scale-100"
        style={{
          background: uploading
            ? 'var(--color-grafana-border)'
            : 'var(--color-grafana-bg-secondary)',
          border: '1px solid var(--color-grafana-border)',
          color: 'var(--color-grafana-text-secondary)',
        }}
        title={!buildingId ? 'Select a building first' : 'Upload document'}
        aria-label="Upload document"
      >
        {uploading ? (
          <>
            <Loader className="w-4 h-4 animate-spin" />
            <span className="text-xs">Uploading...</span>
          </>
        ) : (
          <>
            <Paperclip className="w-4 h-4" />
            <span className="text-xs hidden sm:inline">Upload</span>
          </>
        )}
      </button>

      {/* Error message */}
      {error && (
        <div
          className="text-xs rounded p-2"
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
          className="text-xs rounded p-2"
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
  );
}

export default DocumentUpload;
