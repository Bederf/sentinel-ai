/**
 * Documents API client for building-scoped document uploads
 *
 * Building-specific documentation can be uploaded through the chat interface
 * and will be automatically indexed for semantic search when chatting about that building.
 */

import { authorizedFetch, API_BASE_URL } from './client';

export interface Document {
  id: string;
  title: string;
  code: string;
  document_type: string;
  site_id: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse {
  document_id: string;
  title: string;
  chunk_count: number;
  indexing_status: string;
  storage_path: string;
}

export interface TechnicianDocumentUploadRequest {
  file: File;
  equipmentId: string;
  documentName: string;
  documentSubClass: string;
  categoryDiscipline: string;
  documentCreationDate: string;
  triggerDate: string;
  title?: string;
  siteId?: string;
}

export const documentsApi = {
  /**
   * Upload a document for a specific building.
   *
   * The document will be extracted, stored in Supabase Storage,
   * and indexed into the RAG system with building association.
   *
   * @param siteId - Building UUID
   * @param file - Document file (PDF, DOCX, or TXT)
   * @param title - Optional document title (defaults to filename)
   * @param documentType - Document classification (default: "building_manual")
   * @returns Upload confirmation with document ID and chunk count
   */
  async uploadDocument(
    siteId: string,
    file: File,
    title?: string,
    documentType: string = 'building_manual'
  ): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('site_id', siteId);
    if (title) {
      formData.append('title', title);
    }
    formData.append('document_type', documentType);

    const response = await authorizedFetch(`${API_BASE_URL}/documents/upload`, {
      method: 'POST',
      body: formData,
      // Don't set Content-Type - browser will set multipart boundary automatically
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || `Upload failed: ${response.status}`);
    }

    return response.json();
  },

  /**
   * Upload a technician/compliance document with strict metadata validation.
   *
   * Identity and site are derived server-side from the authenticated user
   * (siteId is optional and only used in explicit multi-site scenarios).
   */
  async uploadTechnicianDocument(payload: TechnicianDocumentUploadRequest): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', payload.file);
    formData.append('equipment_id', payload.equipmentId);
    formData.append('document_name', payload.documentName);
    formData.append('document_sub_class', payload.documentSubClass);
    formData.append('category_discipline', payload.categoryDiscipline);
    formData.append('document_creation_date', payload.documentCreationDate);
    formData.append('trigger_date', payload.triggerDate);
    if (payload.title) {
      formData.append('title', payload.title);
    }
    if (payload.siteId) {
      formData.append('site_id', payload.siteId);
    }

    const response = await authorizedFetch(`${API_BASE_URL}/documents/technician/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Technician upload failed' }));
      throw new Error(error.detail || `Technician upload failed: ${response.status}`);
    }

    return response.json();
  },

  /**
   * Check if document service is available.
   */
  async health(): Promise<{ status: string }> {
    const response = await authorizedFetch(`${API_BASE_URL}/documents/health`);
    return response.json();
  },
};
