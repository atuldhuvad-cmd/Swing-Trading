import { useEffect, useState } from 'react';
import BackLink from '../components/BackLink';
import { brokerUploadsApi } from '../api';

interface UploadEntry {
  upload_id: string;
  broker_name: string;
  stock_symbol: string | null;
  note: string | null;
  original_filename: string;
  size_bytes: number;
  uploaded_at: string;
  sha256?: string | null;
  discovery_source?: string | null;
}

interface ExtractedField {
  value: any;
  status: string;
  note?: string | null;
}

interface PreviewResult {
  action: string;
  persisted: boolean;
  file: { original_filename: string; size_bytes: number; sha256: string; duplicate_file: boolean; duplicate_of_upload_id: string | null };
  discovery: { discovery_source: string | null; discovery_url: string | null; discovery_url_status: string };
  canonical_source: { source_type: string; publication_name: string | null; proposed_verification_status: string | null; verification_state: string };
  extraction: Record<string, ExtractedField> | null;
  broker?: { name: string | null };
  stock?: { company_name: string | null; nse_symbol: string | null; status: string };
  rating?: { original: string | null; normalized: string | null };
  existing_match?: Record<string, any> | null;
  differences?: { field: string; report: string | null; stored: string | null }[];
  not_stated_in_report?: string[];
  warnings: string[];
}

const ACTION_TEXT: Record<string, string> = {
  NEW: 'New recommendation could be created',
  NEW_REVISION: 'Newer report — could supersede the current recommendation (history kept)',
  ATTACH_SOURCE: 'Matches an existing recommendation — attach this PDF as evidence only',
  EXACT_DUPLICATE: 'Already recorded with this PDF — nothing to do',
  DUPLICATE_FILE: 'Identical file already in this batch — ignored',
  CONFLICT_REVIEW_REQUIRED: 'Conflicts with a stored recommendation — review needed, nothing changes',
  UNKNOWN_STOCK: 'Stock is not in your universe — archive only',
  UNKNOWN_BROKER: 'Broker not identified — review only',
  REVIEW_REQUIRED: 'Some values are missing or unclear — review needed',
};

function actionClass(action: string): string {
  if (action === 'NEW' || action === 'NEW_REVISION' || action === 'ATTACH_SOURCE') return 'bg-green-50 text-green-800 border-green-200';
  if (action === 'EXACT_DUPLICATE' || action === 'DUPLICATE_FILE' || action === 'UNKNOWN_STOCK') return 'bg-gray-50 text-gray-800 border-gray-200';
  return 'bg-amber-50 text-amber-900 border-amber-200';
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function show(f: ExtractedField | undefined, empty = 'Not stated'): string {
  if (!f) return 'UNKNOWN';
  if (f.status === 'NOT_STATED') return empty;
  if (f.status !== 'KNOWN') return f.status;
  if (Array.isArray(f.value)) return f.value.length ? f.value.join(', ') : 'UNKNOWN';
  return String(f.value);
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="text-sm text-gray-900 break-words">{value}</dd>
    </div>
  );
}

function PreviewPanel({ p }: { p: PreviewResult }) {
  const ex = p.extraction || {};
  const cmp = show(ex.report_cmp, 'UNKNOWN') + (ex.cmp_as_of?.status === 'KNOWN' ? ` (as of ${ex.cmp_as_of.value})` : '');
  const target = show(ex.target, 'UNKNOWN') + (ex.previous_target?.status === 'KNOWN' ? ` (previous ${ex.previous_target.value})` : '');
  return (
    <section data-testid="pdf-preview" className="bg-white border border-gray-200 rounded-lg p-4 space-y-3 min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold text-gray-900">Preview</h2>
        <span data-testid="preview-action" className={`text-xs font-semibold px-2 py-1 rounded border ${actionClass(p.action)}`}>{p.action}</span>
      </div>
      <p className="text-sm text-gray-800 break-words">{ACTION_TEXT[p.action] || p.action}</p>
      <p className="text-xs text-amber-800 break-words">
        Preview only — nothing was saved or imported. Check every value against the visible PDF; the PDF is authoritative.
      </p>

      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
        <Row label="Broker (author)" value={p.broker?.name || 'UNKNOWN'} />
        <Row label="Company" value={p.stock?.company_name || 'UNKNOWN'} />
        <Row label="NSE symbol" value={p.stock?.nse_symbol || `Not in your universe (${p.stock?.status || 'UNKNOWN'})`} />
        <Row label="Report type" value={show(ex.report_type, 'UNKNOWN')} />
        <Row label="Report date" value={show(ex.report_date, 'UNKNOWN')} />
        <Row label="Rating" value={`${p.rating?.original || 'UNKNOWN'} → ${p.rating?.normalized || 'UNKNOWN'}`} />
        <Row label="Report CMP" value={cmp} />
        <Row label="Target" value={target} />
        <Row label="Entry range" value={show(ex.entry_low)} />
        <Row label="Stop loss" value={show(ex.stop_loss)} />
        <Row label="Time horizon" value={show(ex.time_horizon)} />
        <Row label="Analysts" value={show(ex.analysts, 'UNKNOWN')} />
        <Row label="Source" value={`${p.canonical_source.source_type} · ${p.canonical_source.publication_name || 'UNKNOWN'}`} />
        <Row label="Verification" value={`${p.canonical_source.proposed_verification_status || 'none'} (${p.canonical_source.verification_state})`} />
        <Row label="Discovered via" value={`${p.discovery.discovery_source || 'not recorded'} · URL ${p.discovery.discovery_url_status.toLowerCase()}`} />
        <Row label="File" value={`${p.file.original_filename} (${formatSize(p.file.size_bytes)})${p.file.duplicate_file ? ' · DUPLICATE_FILE' : ''}`} />
      </dl>
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wide text-gray-500">SHA-256</div>
        <div className="text-xs font-mono text-gray-800 break-all">{p.file.sha256}</div>
      </div>

      {p.existing_match && (
        <div className="text-xs text-gray-800 break-words">
          Existing recommendation #{p.existing_match.recommendation_id}: {p.existing_match.normalized_rating} on{' '}
          {p.existing_match.recommendation_date}, price {p.existing_match.recommended_price ?? 'N/A'}, target{' '}
          {p.existing_match.target_price ?? 'N/A'}
        </div>
      )}
      {p.differences && p.differences.length > 0 && (
        <ul className="text-xs text-red-800 list-disc pl-4 break-words" data-testid="preview-differences">
          {p.differences.map((d) => (
            <li key={d.field}>{d.field}: report {d.report ?? 'N/A'} vs stored {d.stored ?? 'N/A'}</li>
          ))}
        </ul>
      )}
      {p.warnings.length > 0 && (
        <ul className="text-xs text-gray-700 list-disc pl-4 space-y-0.5 break-words" data-testid="preview-warnings">
          {p.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
    </section>
  );
}

export default function BrokerUploads() {
  const [uploads, setUploads] = useState<UploadEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [brokerName, setBrokerName] = useState('');
  const [stockSymbol, setStockSymbol] = useState('');
  const [note, setNote] = useState('');
  const [discoverySource, setDiscoverySource] = useState('Trendlyne');
  const [discoveryUrl, setDiscoveryUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<PreviewResult | null>(null);

  const load = async () => {
    try {
      const res = await brokerUploadsApi.list();
      setUploads(res);
      setListError(null);
    } catch (err: any) {
      setListError(err?.response?.data?.detail || 'Failed to load uploaded PDFs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const runPreview = async () => {
    setSubmitError(null);
    setPreview(null);
    if (!file) {
      setSubmitError('Choose a PDF file to preview');
      return;
    }
    setPreviewing(true);
    try {
      const res: PreviewResult = await brokerUploadsApi.preview(
        file, stockSymbol.trim() || undefined, discoverySource.trim() || undefined, discoveryUrl.trim() || undefined,
      );
      setPreview(res);
      if (!brokerName.trim() && res.broker?.name) setBrokerName(res.broker.name);
    } catch (err: any) {
      setSubmitError(err?.response?.data?.detail || 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    if (!brokerName.trim() || !file) {
      setSubmitError('Broker name and a PDF file are required');
      return;
    }
    setSubmitting(true);
    try {
      await brokerUploadsApi.upload(
        file, brokerName.trim(), stockSymbol.trim() || undefined, note.trim() || undefined,
        discoverySource.trim() || undefined, discoveryUrl.trim() || undefined,
      );
      setBrokerName('');
      setStockSymbol('');
      setNote('');
      setDiscoveryUrl('');
      setFile(null);
      setPreview(null);
      const input = document.getElementById('broker-pdf-file') as HTMLInputElement | null;
      if (input) input.value = '';
      await load();
    } catch (err: any) {
      setSubmitError(err?.response?.data?.detail || 'Upload failed');
    } finally {
      setSubmitting(false);
    }
  };

  const input = 'mt-1 w-full min-w-0 min-h-11 border rounded p-2';

  return (
    <div className="max-w-xl mx-auto space-y-4 min-w-0">
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <BackLink fallback="/data" />
        <h1 className="text-xl font-bold text-gray-900">Upload Broker PDF</h1>
        <p className="text-xs text-gray-500 mt-1">
          Keep a broker-authored research PDF (Motilal Oswal, ICICI Securities, Axis Securities, and others — for
          example ones you found on Trendlyne). <strong>Preview PDF</strong> reads the report and shows the proposed
          values, duplicates and conflicts without saving or importing anything. <strong>Upload PDF</strong> only
          stores the file; an identical file is never stored twice. Recommendations are entered through{' '}
          <a href="/recommendations/new" className="text-blue-700 hover:underline">Enter a recommendation</a>{' '}
          after you check the values against the PDF.
        </p>
      </div>

      <form onSubmit={submit} className="bg-white border border-gray-200 rounded-lg p-4 space-y-3 min-w-0">
        <label className="text-sm block">
          PDF file (required)
          <input
            id="broker-pdf-file"
            type="file"
            accept="application/pdf"
            className="mt-1 w-full min-w-0 text-sm"
            onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); }}
          />
        </label>
        <label className="text-sm block">
          Broker name (required to upload)
          <input className={input} placeholder="e.g. Motilal Oswal" value={brokerName} onChange={(e) => setBrokerName(e.target.value)} />
        </label>
        <label className="text-sm block">
          Stock (optional)
          <input className={input} placeholder="e.g. RELIANCE" value={stockSymbol} onChange={(e) => setStockSymbol(e.target.value)} />
        </label>
        <label className="text-sm block">
          Discovered via (optional)
          <input className={input} placeholder="e.g. Trendlyne" value={discoverySource} onChange={(e) => setDiscoverySource(e.target.value)} />
        </label>
        <label className="text-sm block">
          Discovery page URL (optional — leave empty if unknown)
          <input className={input} placeholder="https://…" value={discoveryUrl} onChange={(e) => setDiscoveryUrl(e.target.value)} />
        </label>
        <label className="text-sm block">
          Note (optional)
          <input className={input} placeholder="e.g. Q1 results update" value={note} onChange={(e) => setNote(e.target.value)} />
        </label>

        {submitError && (
          <div className="bg-red-50 p-3 rounded-md text-red-600 text-xs border border-red-200 break-words">
            {submitError}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <button
            type="button"
            onClick={runPreview}
            disabled={previewing}
            className="min-h-11 w-full rounded-md border border-blue-600 text-blue-700 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {previewing ? 'Reading PDF…' : 'Preview PDF'}
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="min-h-11 w-full rounded-md bg-blue-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Uploading…' : 'Upload PDF'}
          </button>
        </div>
      </form>

      {preview && <PreviewPanel p={preview} />}

      <div className="bg-white p-4 rounded-lg border border-gray-200 min-w-0">
        <h2 className="font-semibold text-gray-900">Uploaded PDFs</h2>
        {loading && <div className="text-sm text-gray-500 mt-2">Loading…</div>}
        {listError && (
          <div className="mt-2 bg-red-50 p-3 rounded-md text-red-600 text-xs border border-red-200 break-words">
            {listError}
          </div>
        )}
        {!loading && uploads.length === 0 && (
          <div className="text-sm text-gray-500 mt-2">No PDFs uploaded yet.</div>
        )}
        <div className="mt-2 divide-y divide-gray-100">
          {uploads.map((u) => (
            <div key={u.upload_id} className="py-2 text-sm min-w-0">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium text-gray-900 break-words">
                  {u.broker_name}{u.stock_symbol ? ` · ${u.stock_symbol}` : ''}
                </span>
                <span className="text-[11px] text-gray-500">{new Date(u.uploaded_at).toLocaleString()}</span>
              </div>
              <div className="text-[11px] text-gray-500 mt-0.5 break-words">
                {u.original_filename} ({formatSize(u.size_bytes)}){u.discovery_source ? ` · via ${u.discovery_source}` : ''}{u.note ? ` — ${u.note}` : ''}
              </div>
              <a
                href={brokerUploadsApi.fileUrl(u.upload_id)}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-blue-700 hover:underline"
              >
                View PDF
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
