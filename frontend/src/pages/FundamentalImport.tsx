import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fundamentalsApi } from '../api';
import BackLink from '../components/BackLink';

export default function FundamentalImport() {
  const [catalog, setCatalog] = useState<any>(null);
  const [entityType, setEntityType] = useState('ORDINARY');
  const [form, setForm] = useState({
    nse_symbol: '',
    as_of_date: '',
    financial_period: '',
    period_type: 'ANNUAL',
    source_name: '',
    source_reference: '',
    statement_scope: 'CONSOLIDATED',
    source_line_item: 'Revenue from Operations',
    original_unit: 'INR_CRORE',
  });
  const [metricState, setMetricState] = useState<Record<string, { status: string; metric_value: string }>>({});
  const [preview, setPreview] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fundamentalsApi.getCatalog().then(setCatalog).catch((e) => setError(e?.response?.data?.detail || 'Failed to load catalog'));
  }, []);

  useEffect(() => {
    if (!catalog) return;
    const metricKey = catalog.entity_metric_key?.[entityType] ?? entityType.toLowerCase();
    const next: Record<string, { status: string; metric_value: string }> = {};
    for (const m of catalog.metrics) {
      next[m.metric_name] = {
        status: m[metricKey] ? 'UNKNOWN' : 'NOT_APPLICABLE',
        metric_value: '',
      };
    }
    setMetricState(next);
    setPreview(null);
    setResult(null);
  }, [catalog, entityType]);

  useEffect(() => {
    if (!catalog) return;
    const line = catalog.canonical_source_line?.[entityType];
    if (line) setForm((prev) => ({ ...prev, source_line_item: line }));
  }, [catalog, entityType]);

  const payload = () => ({
    nse_symbol: form.nse_symbol.trim().toUpperCase(),
    entity_type: entityType,
    as_of_date: form.as_of_date,
    financial_period: form.financial_period,
    period_type: form.period_type,
    source_name: form.source_name,
    source_reference: form.source_reference || null,
    statement_scope: form.statement_scope,
    source_line_item: form.source_line_item,
    original_unit: form.original_unit || null,
    metrics: Object.entries(metricState).map(([metric_name, v]) => ({
      metric_name,
      status: v.status,
      metric_value: v.status === 'KNOWN' ? v.metric_value : null,
    })),
  });

  const runPreview = async () => {
    setError(null);
    setResult(null);
    try {
      setPreview(await fundamentalsApi.preview(payload()));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Preview failed');
    }
  };

  const runConfirm = async () => {
    if (!preview) return;
    setError(null);
    try {
      setResult(await fundamentalsApi.confirm({ payload_sha256: preview.payload_sha256, payload: payload() }));
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Confirm failed');
    }
  };

  return (
    <div className="space-y-4 min-w-0">
      <BackLink fallback="/market-data" />
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <h1 className="text-xl font-bold text-gray-900">Fundamental Import</h1>
        <p className="text-xs text-gray-500 mt-1">
          Manual genuine-source entry only. Preview is non-persistent. Missing metrics stay UNKNOWN or NOT_APPLICABLE — never PASS.
        </p>
        <p className="text-xs text-gray-500 mt-1">
          Candidate rule currently requires: <strong>revenue</strong>. Do not invent numbers.
        </p>
      </div>

      {catalog?.canonical_source_line && (
        <div className="bg-white p-4 rounded-lg border border-gray-200 text-xs">
          <h2 className="font-semibold text-sm mb-2">Canonical revenue policy</h2>
          <ul className="space-y-1">
            {Object.entries(catalog.canonical_source_line as Record<string, string>).map(([type, line]) => (
              <li
                key={type}
                className={type === entityType ? 'text-gray-900 font-medium' : 'text-gray-500'}
              >
                <span className="inline-block min-w-[92px]">{type}</span>
                Revenue = {line} · Unit = ₹ crore · Preferred scope = Consolidated
              </li>
            ))}
          </ul>
          <p className="text-gray-500 mt-2">
            Standalone is allowed only when consolidated statements genuinely do not exist, and the
            scope must be recorded explicitly.
          </p>
        </div>
      )}

      {error && <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200 break-words">{error}</div>}

      <div className="bg-white p-4 rounded-lg border border-gray-200 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
        <label className="min-w-0">NSE symbol
          <input className="mt-1 w-full border rounded p-2 min-h-[44px]" value={form.nse_symbol} onChange={(e) => setForm({ ...form, nse_symbol: e.target.value })} />
        </label>
        <label>Entity type
          <select className="mt-1 w-full border rounded p-2 min-h-[44px]" value={entityType} onChange={(e) => setEntityType(e.target.value)}>
            {(catalog?.entity_types ?? ['ORDINARY', 'BANK', 'NBFC', 'INSURANCE']).map((t: string) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>As-of / reporting date
          <input type="date" className="mt-1 w-full border rounded p-2 min-h-[44px]" value={form.as_of_date} onChange={(e) => setForm({ ...form, as_of_date: e.target.value })} />
        </label>
        <label>Financial period
          <input className="mt-1 w-full border rounded p-2 min-h-[44px]" placeholder="FY2026" value={form.financial_period} onChange={(e) => setForm({ ...form, financial_period: e.target.value })} />
        </label>
        <label>Period type
          <select className="mt-1 w-full border rounded p-2 min-h-[44px]" value={form.period_type} onChange={(e) => setForm({ ...form, period_type: e.target.value })}>
            <option>ANNUAL</option>
            <option>QUARTERLY</option>
            <option>HALF_YEARLY</option>
            <option>TTM</option>
          </select>
        </label>
        <label>Source name
          <input className="mt-1 w-full border rounded p-2 min-h-[44px]" value={form.source_name} onChange={(e) => setForm({ ...form, source_name: e.target.value })} />
        </label>
        <label>Original reported unit
          <select className="mt-1 w-full border rounded p-2 min-h-[44px]" value={form.original_unit} onChange={(e) => setForm({ ...form, original_unit: e.target.value })}>
            <option value="INR_CRORE">INR_CRORE</option>
            <option value="INR_MILLION">INR_MILLION</option>
            <option value="INR_LAKH">INR_LAKH</option>
          </select>
        </label>
        <label>Statement scope
          <select className="mt-1 w-full border rounded p-2 min-h-[44px]" value={form.statement_scope} onChange={(e) => setForm({ ...form, statement_scope: e.target.value })}>
            <option>CONSOLIDATED</option>
            <option>STANDALONE</option>
          </select>
        </label>
        <label className="sm:col-span-2">Canonical source line item
          <input className="mt-1 w-full border rounded p-2 min-h-[44px]" value={form.source_line_item} onChange={(e) => setForm({ ...form, source_line_item: e.target.value })} />
        </label>
        <label className="sm:col-span-2">Source reference (URL or document id)
          <input className="mt-1 w-full border rounded p-2 min-h-[44px]" value={form.source_reference} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} />
        </label>
      </div>

      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <h2 className="font-semibold mb-2">Metrics</h2>
        <div className="space-y-3">
          {catalog?.metrics?.map((m: any) => (
            <div key={m.metric_name} className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs border-b border-gray-100 pb-2">
              <div className="min-w-0">
                <div className="font-medium break-words">{m.label}</div>
                <div className="text-gray-500">{m.metric_name}{m.required_by_candidate_rule ? ' · required' : ''}</div>
              </div>
              <select
                className="border rounded p-2 min-h-[44px]"
                value={metricState[m.metric_name]?.status || 'UNKNOWN'}
                onChange={(e) => setMetricState({
                  ...metricState,
                  [m.metric_name]: { ...metricState[m.metric_name], status: e.target.value },
                })}
              >
                <option>KNOWN</option>
                <option>UNKNOWN</option>
                <option>NOT_APPLICABLE</option>
                <option>STALE</option>
                <option>UNSUPPORTED</option>
              </select>
              <input
                className="border rounded p-2 min-h-[44px]"
                placeholder="Value if KNOWN"
                value={metricState[m.metric_name]?.metric_value || ''}
                onChange={(e) => setMetricState({
                  ...metricState,
                  [m.metric_name]: { ...metricState[m.metric_name], metric_value: e.target.value },
                })}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={runPreview} className="min-h-[44px] px-4 rounded bg-blue-600 text-white">Preview</button>
        <button type="button" onClick={runConfirm} disabled={!preview} className="min-h-[44px] px-4 rounded bg-gray-800 text-white disabled:opacity-40">Confirm import</button>
        <Link to="/market-data" className="min-h-[44px] px-4 rounded border inline-flex items-center">Back to market data</Link>
      </div>

      {preview && (
        <div className="bg-white p-4 rounded-lg border border-gray-200 text-xs space-y-1">
          <h2 className="font-semibold text-sm">Preview (not persisted)</h2>
          <div>Action: {preview.action}</div>
          <div className="break-words">{preview.message}</div>
          <div>{preview.stock?.nse_symbol} — {preview.stock?.company_name}</div>
          <div>Scope: {preview.statement_scope} · Line: {preview.source_line_item} · Original unit: {preview.original_unit || '—'} · Normalized: INR_CRORE</div>
          {preview.stale_warning && <div className="text-amber-700">{preview.stale_warning}</div>}
          {preview.metrics?.map((m: any) => (
            <div key={m.metric_name}>{m.metric_name}: {m.metric_value ?? '—'} ({m.status})</div>
          ))}
        </div>
      )}

      {result && (
        <div className="bg-green-50 p-4 rounded-lg border border-green-200 text-xs">
          Confirm result: {result.status} · snapshot {result.snapshot_id ?? 'none'} · persisted {String(result.persisted)}
        </div>
      )}
    </div>
  );
}
