import { authorizedFetch } from './client';

// ---------------------------------------------------------------------------
// Search types (existing)
// ---------------------------------------------------------------------------

export interface ConceptDocumentSearchRequest {
  site_id: string;
  building_id?: string;
  query: string;
  top_k?: number;
}

export interface ConceptDocumentSearchResult {
  document_id: string;
  concept_document_id: string;
  title: string;
  document_type?: string | null;
  document_date?: string | null;
  building_name?: string | null;
  equipment_category?: string | null;
  equipment_name?: string | null;
  path: string;
  open_url: string;
  download_url?: string | null;
  actual_path?: string | null;
  match_reasons: string[];
  snippet?: string | null;
}

export interface ConceptDocumentSearchResponse {
  mode: 'concept_document_search';
  query: string;
  building_id: string;
  results: ConceptDocumentSearchResult[];
  total_results: number;
  weak_results?: boolean;
}

export interface ConceptDocumentActionRequest {
  site_id: string;
  document_id: string;
  action: 'open' | 'download';
  query?: string;
}

// ---------------------------------------------------------------------------
// Upload types (F1-F8 controlled fields)
// ---------------------------------------------------------------------------

export interface ConceptDocumentUploadMetadata {
  site_id: string;
  discipline: string;       // F2
  document_type: string;    // F3
  frequency: string;        // F4
  document_creation_date: string; // F5 — YYYY-MM-DD, must NOT default to today
  trigger_type: string;     // F6
  trigger_date: string | null;    // F6 date — only for Vital records
}

export interface ConceptDocumentFieldOptions {
  discipline: string[];
  document_type: string[];
  frequency: string[];
  trigger_type: string[];
  vital_trigger_types: string[];
  notes: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function parseApiError(response: Response, fallback: string): Promise<Error> {
  try {
    const data = await response.json();
    // Handle Pydantic 422 validation errors
    if (Array.isArray(data.detail)) {
      const msgs = data.detail
        .map((e: { msg?: string; loc?: string[] }) =>
          `${e.loc?.slice(-1)[0] ?? 'field'}: ${e.msg ?? 'invalid'}`
        )
        .join(', ');
      return new Error(msgs);
    }
    return new Error(data.detail || fallback);
  } catch {
    return new Error(fallback);
  }
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export const conceptDocumentsApi = {
  // --- Search (site-002 legacy keyword search) ---

  async search(payload: ConceptDocumentSearchRequest): Promise<ConceptDocumentSearchResponse> {
    const response = await authorizedFetch('/api/technical/concept-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...payload,
        top_k: payload.top_k ?? 10,
      }),
    });

    if (!response.ok) {
      throw await parseApiError(response, `Concept search failed: ${response.status}`);
    }

    return response.json();
  },

  async logAction(payload: ConceptDocumentActionRequest): Promise<void> {
    const response = await authorizedFetch('/api/technical/concept-search/click', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw await parseApiError(response, `Concept action log failed: ${response.status}`);
    }
  },

  // --- Upload field options (F1-F8 approved dropdown values) ---

  async getUploadFields(): Promise<ConceptDocumentFieldOptions> {
    const response = await authorizedFetch('/api/concept/documents/fields');
    if (!response.ok) {
      throw await parseApiError(response, `Failed to load upload fields: ${response.status}`);
    }
    return response.json();
  },

  // --- Upload document with F1-F8 controlled fields ---

  async uploadDocument(file: File, metadata: ConceptDocumentUploadMetadata): Promise<void> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('metadata_json', JSON.stringify(metadata));

    // Do NOT set Content-Type — browser sets it automatically with boundary for FormData
    const token = (await import('./client')).getAccessToken();
    const response = await authorizedFetch('/api/concept/documents/upload', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });

    if (!response.ok) {
      throw await parseApiError(response, `Document upload failed: ${response.status}`);
    }
  },
};
