/**
 * PhotoCapture Component - Camera capture for equipment photos
 *
 * Features:
 * - Device camera capture on mobile (rear camera)
 * - File upload fallback on desktop
 * - Image preview before sending
 * - Compression for large images
 * - Support for JPEG, PNG, WebP
 */

import { useRef, useState, useCallback } from 'react';
import type { ChangeEvent } from 'react';
import { Camera, X, Loader2 } from 'lucide-react';
import { authorizedFetch } from '../lib/api/client';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Max image size: 5MB
const MAX_SIZE = 5 * 1024 * 1024;

interface PhotoCaptureProps {
  /** Callback when analysis is complete */
  onAnalysisComplete: (result: VisionResult) => void;
  /** Callback for errors */
  onError?: (error: string) => void;
  /** Analysis type to perform */
  analysisType?: 'analyze' | 'component' | 'model-plate' | 'diagnose' | 'error-display';
  /** Optional context for analysis */
  context?: string;
  /** Disabled state */
  disabled?: boolean;
}

interface VisionResult {
  success: boolean;
  analysis?: string;
  components?: Array<{
    name: string;
    manufacturer?: string;
    model?: string;
    condition?: string;
    confidence?: number;
  }>;
  issues?: Array<{
    type: string;
    severity: string;
    location?: string;
    description?: string;
    recommendation?: string;
  }>;
  fault_codes?: string[];
  manufacturer?: string;
  model?: string;
  serial?: string;
  raw_text?: string;
  [key: string]: unknown;
}

export default function PhotoCapture({
  onAnalysisComplete,
  onError,
  analysisType = 'analyze',
  context,
  disabled = false
}: PhotoCaptureProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // Convert file to base64
  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = (error) => reject(error);
    });
  };

  // Compress image if needed
  const compressImage = async (file: File, maxSize: number): Promise<{ data: string; type: string }> => {
    const base64 = await fileToBase64(file);

    // If file is small enough, return as-is
    if (file.size <= maxSize) {
      return {
        data: base64.split(',')[1],
        type: file.type
      };
    }

    // Compress using canvas
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        let { width, height } = img;

        // Scale down if larger than 1920px
        const maxDimension = 1920;
        if (width > maxDimension || height > maxDimension) {
          const ratio = Math.min(maxDimension / width, maxDimension / height);
          width = Math.round(width * ratio);
          height = Math.round(height * ratio);
        }

        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext('2d');
        if (!ctx) {
          reject(new Error('Failed to get canvas context'));
          return;
        }

        ctx.drawImage(img, 0, 0, width, height);

        // Get compressed data URL
        const compressed = canvas.toDataURL('image/jpeg', 0.85);
        resolve({
          data: compressed.split(',')[1],
          type: 'image/jpeg'
        });
      };
      img.onerror = () => reject(new Error('Failed to load image'));
      img.src = base64;
    });
  };

  // Analyze image via API
  const analyzeImage = async (imageData: string, mediaType: string) => {
    setIsAnalyzing(true);

    try {
      // Map analysis type to endpoint
      const endpoints: Record<string, string> = {
        'analyze': '/api/vision/analyze',
        'component': '/api/vision/component',
        'model-plate': '/api/vision/model-plate',
        'diagnose': '/api/vision/diagnose',
        'error-display': '/api/vision/error-display'
      };

      const endpoint = endpoints[analysisType] || '/api/vision/analyze';

      // Build request body based on endpoint
      const body: Record<string, unknown> = {
        image: imageData,
        media_type: mediaType
      };

      if (context) {
        if (analysisType === 'component') {
          body.context = context;
        } else if (analysisType === 'diagnose') {
          body.equipment_context = context;
        } else if (analysisType === 'error-display') {
          body.manufacturer = context;
        } else {
          body.prompt = context;
        }
      }

      const response = await authorizedFetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `Analysis failed: ${response.status}`);
      }

      const result = await response.json();
      onAnalysisComplete(result);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Analysis failed';
      onError?.(message);
    } finally {
      setIsAnalyzing(false);
      setPreview(null);
    }
  };

  // Handle file selection
  const handleFileChange = useCallback(async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    if (!allowedTypes.includes(file.type)) {
      onError?.('Please select a JPEG, PNG, WebP, or GIF image');
      return;
    }

    try {
      // Show preview
      const previewUrl = await fileToBase64(file);
      setPreview(previewUrl);

      // Compress and analyze
      const { data, type } = await compressImage(file, MAX_SIZE);
      await analyzeImage(data, type);
    } catch (error) {
      onError?.(error instanceof Error ? error.message : 'Failed to process image');
      setPreview(null);
    }

    // Reset input
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  }, [analysisType, context, onAnalysisComplete, onError]);

  // Cancel preview
  const cancelPreview = () => {
    setPreview(null);
    setIsAnalyzing(false);
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  };

  // Show preview overlay when analyzing
  if (preview) {
    return (
      <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
        <div className="bg-white dark:bg-gray-800 rounded-xl max-w-md w-full overflow-hidden">
          {/* Preview image */}
          <div className="relative aspect-[4/3] bg-gray-900">
            <img
              src={preview}
              alt="Preview"
              className="w-full h-full object-contain"
            />
            {!isAnalyzing && (
              <button
                onClick={cancelPreview}
                className="absolute top-2 right-2 p-2 bg-black/50 rounded-full text-white hover:bg-black/70 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>

          {/* Status */}
          <div className="p-4">
            {isAnalyzing ? (
              <div className="flex items-center justify-center gap-3 text-blue-600 dark:text-blue-400">
                <Loader2 className="w-5 h-5 animate-spin" />
                <span className="font-medium">Analyzing image...</span>
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={() => analyzeImage(preview.split(',')[1], 'image/jpeg')}
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
                >
                  Analyze
                </button>
                <button
                  onClick={cancelPreview}
                  className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        capture="environment"
        onChange={handleFileChange}
        disabled={disabled}
        className="hidden"
      />
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={disabled || isAnalyzing}
        className="flex-none p-2.5 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        title="Take photo"
      >
        {isAnalyzing ? (
          <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
        ) : (
          <Camera className="w-5 h-5 text-gray-600 dark:text-gray-400" />
        )}
      </button>
    </>
  );
}
