import { authorizedFetch } from './client';

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

async function parseApiError(response: Response, fallback: string): Promise<Error> {
  try {
    const data = await response.json();
    return new Error(data.detail || fallback);
  } catch {
    return new Error(fallback);
  }
}

export const conceptDocumentsApi = {
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
};
