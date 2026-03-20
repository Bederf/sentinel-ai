import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import TechnicianChat from '../TechnicianChat';

const scrollIntoViewMock = vi.fn();
Element.prototype.scrollIntoView = scrollIntoViewMock;
HTMLElement.prototype.scrollIntoView = scrollIntoViewMock;

vi.mock('@/lib/api/client', () => ({
  authorizedFetch: vi.fn(),
}));

vi.mock('../DiagnosisFlow', () => ({
  default: () => <div data-testid="diagnosis-flow" />,
}));

vi.mock('../PhotoCapture', () => ({
  default: () => <button data-testid="photo-capture">Photo</button>,
}));

import { authorizedFetch } from '@/lib/api/client';

describe('TechnicianChat Concept mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('open', vi.fn());
  });

  it('switches to Concept search mode and queries the technical search endpoint', async () => {
    (authorizedFetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({
        mode: 'concept_document_search',
        query: 'elevator annual lift inspection certificate',
        building_id: 'site-002',
        total_results: 1,
        weak_results: false,
        results: [
          {
            document_id: 'doc-1',
            concept_document_id: 'concept-1',
            title: 'Lift Annual Inspection Certificate 2025.pdf',
            document_type: 'certificate',
            document_date: '2025-01-14',
            building_name: 'Fairlands',
            equipment_category: 'elevator',
            equipment_name: 'Lift 2',
            path: 'Fairlands / Vertical Transport / Lift 2',
            open_url: 'https://concept.example/open/1',
            download_url: 'https://concept.example/download/1',
            match_reasons: ['lift', 'inspection', 'certificate', 'annual'],
            snippet: 'Annual lift inspection certificate issued for Lift 2...',
          },
        ],
      }),
    });

    render(<TechnicianChat siteId="site-002" siteLabel="Fairlands" />);

    await userEvent.click(screen.getByRole('button', { pressed: false, name: /search concept documents/i }));
    expect(screen.getByText(/concept document search active/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search stored site documents/i)).toBeInTheDocument();
    expect(screen.getAllByText(/find saved documents in concept using natural language/i)).toHaveLength(2);

    await userEvent.type(
      screen.getByPlaceholderText(/search stored site documents/i),
      'elevator annual lift inspection certificate',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Run Concept document search' }));

    await waitFor(() => {
      expect((authorizedFetch as any).mock.calls[0][0]).toBe('/api/technical/concept-search');
    });

    expect(await screen.findByText('Lift Annual Inspection Certificate 2025.pdf')).toBeInTheDocument();
    expect(screen.getByText('1 matching document found')).toBeInTheDocument();
  });

  it('logs and opens Concept files from search results', async () => {
    (authorizedFetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          mode: 'concept_document_search',
          query: 'last generator service sheets',
          building_id: 'site-002',
          total_results: 1,
          weak_results: false,
          results: [
            {
              document_id: 'doc-2',
              concept_document_id: 'concept-2',
              title: 'Generator Service Sheet May 2025.pdf',
              document_type: 'service sheet',
              document_date: '2025-05-01',
              building_name: 'Fairlands',
              equipment_category: 'generator',
              equipment_name: 'Generator 1',
              path: 'Fairlands / Energy Centre / Generator 1',
              open_url: 'https://concept.example/open/2',
              download_url: 'https://concept.example/download/2',
              match_reasons: ['generator', 'service'],
              snippet: 'Service sheet for Generator 1...',
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({}),
      });

    render(<TechnicianChat siteId="site-002" siteLabel="Fairlands" />);

    await userEvent.click(screen.getByRole('button', { pressed: false, name: /search concept documents/i }));
    await userEvent.type(
      screen.getByPlaceholderText(/search stored site documents/i),
      'last generator service sheets',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Run Concept document search' }));
    expect(await screen.findByText('Generator Service Sheet May 2025.pdf')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /open file/i }));

    await waitFor(() => {
      expect((authorizedFetch as any).mock.calls[1][0]).toBe('/api/technical/concept-search/click');
      expect(window.open).toHaveBeenCalledWith(
        'https://concept.example/open/2',
        '_blank',
        'noopener,noreferrer',
      );
    });
  });

  it('disables placeholder Concept links that are not browser-openable', async () => {
    (authorizedFetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({
        mode: 'concept_document_search',
        query: 'generator service sheets 2024',
        building_id: 'site-001',
        total_results: 1,
        weak_results: false,
        results: [
          {
            document_id: 'doc-3',
            concept_document_id: 'concept-3',
            title: 'Generator Service Sheet 2024.pdf',
            document_type: 'service sheet',
            document_date: '2024-03-11',
            building_name: 'Fairlands',
            equipment_category: 'generator',
            equipment_name: 'Generator 1',
            path: 'Self Service Documents',
            open_url: 'concept://document/49196',
            download_url: 'concept://document/49196',
            match_reasons: ['2024', 'generator', 'service', 'service sheet'],
            snippet: 'Pilot export row',
          },
        ],
      }),
    });

    render(<TechnicianChat siteId="site-001" siteLabel="Fairlands" />);

    await userEvent.click(screen.getByRole('button', { pressed: false, name: /search concept documents/i }));
    await userEvent.type(
      screen.getByPlaceholderText(/search stored site documents/i),
      'generator service sheets 2024',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Run Concept document search' }));

    expect(await screen.findByText('Generator Service Sheet 2024.pdf')).toBeInTheDocument();
    expect(screen.getByText(/live concept link not available in this pilot export yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /link unavailable/i })).toBeDisabled();
    expect(window.open).not.toHaveBeenCalled();
  });
});
