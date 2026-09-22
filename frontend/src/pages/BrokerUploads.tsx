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
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function BrokerUploads() {
  const [uploads, setUploads] = useState<UploadEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [brokerName, setBrokerName] = useState('');
  const [stockSymbol, setStockSymbol] = useState('');
  const [note, setNote] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

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

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    if (!brokerName.trim() || !file) {
      setSubmitError('Broker name and a PDF file are required');
      return;
    }
    setSubmitting(true);
    try {
      await brokerUploadsApi.upload(file, brokerName.trim(), stockSymbol.trim() || undefined, note.trim() || undefined);
      setBrokerName('');
      setStockSymbol('');
      setNote('');
      setFile(null);
      const input = document.getElementById('broker-pdf-file') as HTMLInputElement | null;
      if (input) input.value = '';
      await load();
    } catch (err: any) {
      setSubmitError(err?.response?.data?.detail || 'Upload failed');
    } finally {
      setSubmitting(false);
    }
  };

  const input = 'mt-1 w-full min-h-11 border rounded p-2';

  return (
    <div className="max-w-xl mx-auto space-y-4 min-w-0">
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <BackLink fallback="/data" />
        <h1 className="text-xl font-bold text-gray-900">Upload Broker PDF</h1>
        <p className="text-xs text-gray-500 mt-1">
          Save a recommendation report PDF from any brokerage here (Motilal Oswal, HDFC Securities, 5paisa,
          Sharekhan, etc.). This only stores the file — it does not read or import it. Once uploaded, open the
          PDF, then type the actual facts into{' '}
          <a href="/recommendations/new" className="text-blue-700 hover:underline">Enter a recommendation</a>{' '}
          as usual, citing this PDF as the source.
        </p>
      </div>

      <form onSubmit={submit} className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
        <label className="text-sm block">
          Broker name (required)
          <input
            className={input}
            placeholder="e.g. Motilal Oswal"
            value={brokerName}
            onChange={(e) => setBrokerName(e.target.value)}
          />
        </label>
        <label className="text-sm block">
          Stock (optional)
          <input
            className={input}
            placeholder="e.g. RELIANCE"
            value={stockSymbol}
            onChange={(e) => setStockSymbol(e.target.value)}
          />
        </label>
        <label className="text-sm block">
          Note (optional)
          <input
            className={input}
            placeholder="e.g. Buy call, 3-month horizon"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <label className="text-sm block">
          PDF file (required)
          <input
            id="broker-pdf-file"
            type="file"
            accept="application/pdf"
            className="mt-1 w-full text-sm"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>

        {submitError && (
          <div className="bg-red-50 p-3 rounded-md text-red-600 text-xs border border-red-200 break-words">
            {submitError}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="min-h-11 w-full rounded-md bg-blue-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? 'Uploading…' : 'Upload PDF'}
        </button>
      </form>

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
                {u.original_filename} ({formatSize(u.size_bytes)}){u.note ? ` — ${u.note}` : ''}
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
