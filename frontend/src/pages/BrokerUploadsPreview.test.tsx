import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import BrokerUploads from './BrokerUploads';
import { brokerUploadsApi } from '../api';

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    brokerUploadsApi: {
      ...actual.brokerUploadsApi,
      list: vi.fn().mockResolvedValue([]),
      preview: vi.fn(),
      upload: vi.fn(),
    },
  };
});

afterEach(() => {
  cleanup();
  vi.mocked(brokerUploadsApi.preview).mockReset();
  vi.mocked(brokerUploadsApi.upload).mockReset();
});

const conflict = {
  action: 'CONFLICT_REVIEW_REQUIRED',
  persisted: false,
  file: { original_filename: 'report.pdf', size_bytes: 324692, sha256: 'a'.repeat(64), duplicate_file: false, duplicate_of_upload_id: null },
  discovery: { discovery_source: 'Trendlyne', discovery_url: null, discovery_url_status: 'UNAVAILABLE' },
  canonical_source: { source_type: 'BROKER_RESEARCH', publication_name: 'ICICI Securities', proposed_verification_status: 'VERIFIED_PRIMARY', verification_state: 'PENDING_VISUAL_CONFIRMATION' },
  extraction: {
    report_type: { value: 'Company Update', status: 'KNOWN' },
    report_date: { value: '2026-08-31', status: 'KNOWN' },
    report_cmp: { value: '720', status: 'KNOWN' },
    cmp_as_of: { value: null, status: 'NOT_STATED' },
    target: { value: '920', status: 'KNOWN' },
    previous_target: { value: '1020', status: 'KNOWN' },
    entry_low: { value: null, status: 'NOT_STATED' },
    stop_loss: { value: null, status: 'NOT_STATED' },
    time_horizon: { value: null, status: 'NOT_STATED' },
    analysts: { value: ['Ravi Sample'], status: 'KNOWN' },
  },
  broker: { name: 'ICICI Securities' },
  stock: { company_name: 'HDFC Bank', nse_symbol: 'HDFCBANK', status: 'KNOWN' },
  rating: { original: 'BUY (Maintain)', normalized: 'BUY' },
  existing_match: { recommendation_id: 1, normalized_rating: 'BUY', recommendation_date: '2026-08-31', recommended_price: '709.6', target_price: '925' },
  differences: [{ field: 'target', report: '920', stored: '925' }],
  not_stated_in_report: [],
  warnings: ['TARGET_REVISED: previous target 1020 shown in parentheses'],
};

function choosePdf() {
  const input = document.getElementById('broker-pdf-file') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(['%PDF-1.4'], 'report.pdf', { type: 'application/pdf' })] } });
}

describe('Broker PDF preview', () => {
  it('requires a file before previewing', async () => {
    render(<MemoryRouter><BrokerUploads /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: 'Preview PDF' }));
    expect(await screen.findByText('Choose a PDF file to preview')).toBeDefined();
    expect(brokerUploadsApi.preview).not.toHaveBeenCalled();
  });

  it('shows extracted values, the conflict and that nothing was saved', async () => {
    vi.mocked(brokerUploadsApi.preview).mockResolvedValue(conflict);
    render(<MemoryRouter><BrokerUploads /></MemoryRouter>);
    choosePdf();
    fireEvent.click(screen.getByRole('button', { name: 'Preview PDF' }));
    expect(await screen.findByText('CONFLICT_REVIEW_REQUIRED')).toBeDefined();
    expect(screen.getByText(/nothing was saved or imported/i)).toBeDefined();
    expect(screen.getByText('920 (previous 1020)')).toBeDefined();
    expect(screen.getByText('BUY (Maintain) → BUY')).toBeDefined();
    expect(screen.getAllByText('Not stated').length).toBe(3); // entry, stop, horizon
    expect(screen.getByText('target: report 920 vs stored 925')).toBeDefined();
    expect(screen.getByText('a'.repeat(64))).toBeDefined();
    expect(brokerUploadsApi.upload).not.toHaveBeenCalled();
    // The detected broker is offered for a later upload, but nothing is stored automatically.
    expect((screen.getByPlaceholderText('e.g. Motilal Oswal') as HTMLInputElement).value).toBe('ICICI Securities');
  });

  it('passes the discovery source and symbol hint to the preview', async () => {
    vi.mocked(brokerUploadsApi.preview).mockResolvedValue({ ...conflict, action: 'NEW', differences: [], existing_match: null });
    render(<MemoryRouter><BrokerUploads /></MemoryRouter>);
    choosePdf();
    fireEvent.change(screen.getByPlaceholderText('e.g. RELIANCE'), { target: { value: 'HDFCBANK' } });
    fireEvent.click(screen.getByRole('button', { name: 'Preview PDF' }));
    expect(await screen.findByText('NEW')).toBeDefined();
    expect(vi.mocked(brokerUploadsApi.preview).mock.calls[0].slice(1)).toEqual(['HDFCBANK', 'Trendlyne', undefined]);
  });
});
