import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { evidenceApi } from '../api';
import { ShieldCheck } from 'lucide-react';
import { CLASSIFICATION_MEANING, asOfDate, criterionResult, displayValue, statusBadgeClass } from './candidateStatus';

interface CriterionSummary {
  criterion?: string;
  evidence_value?: string | null;
  operator?: string | null;
  threshold?: string | null;
  result?: string | null;
  reason?: string | null;
}

interface CandidateRow {
  stock_id: number;
  nse_symbol: string;
  company_name: string;
  evaluation_id?: number;
  status: string;
  classification_meaning?: string | null;
  decisive_reason?: string | null;
  evaluation_date?: string | null;
  latest_close?: string | null;
  technical?: Record<string, string | null>;
  fundamental_state?: string;
  revenue?: string | null;
  revenue_status?: string | null;
  close_gt_sma50?: CriterionSummary | null;
  sma50_gt_sma200?: CriterionSummary | null;
  entry?: string | null;
  target?: string | null;
  stop?: string | null;
  rr_ratio?: string | null;
  rr_available?: boolean;
}

const STATUS_ORDER = ['FINAL_CANDIDATE', 'WATCH', 'REJECTED', 'INSUFFICIENT_DATA'] as const;
const STATUS_RANK: Record<string, number> = Object.fromEntries(STATUS_ORDER.map((s, i) => [s, i]));

export default function FinalCandidates() {
  const navigate = useNavigate();
  const [items, setItems] = useState<CandidateRow[]>([]);
  const [asOfByStock, setAsOfByStock] = useState<Record<number, string | null>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([evidenceApi.getCandidates(), evidenceApi.getMarketData()])
      .then(([res, market]) => {
        setItems(res.items || []);
        const map: Record<number, string | null> = {};
        for (const row of market.items || []) {
          map[row.stock_id] = asOfDate(row.latest_trading_date);
        }
        setAsOfByStock(map);
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load candidate evaluations'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4 min-w-0">
      <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
          <ShieldCheck className="text-blue-600 w-5 h-5 shrink-0" />
          <span className="min-w-0 break-words">Candidates</span>
        </h1>
        <p className="text-xs text-gray-500 mt-1 break-words">
          Latest stored Phase 5 evaluation per stock. FINAL_CANDIDATE means the trend screen passed — not a BUY.
          RR is evidence only and does not change classification.
        </p>
        <p className="text-xs text-amber-800 mt-2 break-words">
          Not a guaranteed BUY. Not a trading recommendation. No guaranteed profitability.
        </p>
        <dl className="mt-3 space-y-1 text-xs text-gray-700">
          {STATUS_ORDER.map((status) => (
            <div key={status} className="flex gap-2 min-w-0">
              <dt className={`shrink-0 font-semibold px-1.5 py-0.5 rounded ${statusBadgeClass(status)}`}>{status}</dt>
              <dd className="min-w-0 break-words">{CLASSIFICATION_MEANING[status]}</dd>
            </div>
          ))}
        </dl>
      </div>

      {loading && <div className="text-sm text-gray-500">Loading evaluations...</div>}
      {error && <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200">{error}</div>}
      {!loading && !error && items.length === 0 && (
        <div className="bg-white p-8 text-center rounded-lg border border-gray-200 text-gray-500">
          No candidate evaluations are stored yet.
        </div>
      )}

      <div className="grid grid-cols-1 gap-3">
        {[...items]
          .sort((a, b) => {
            // Sort by recommendation strength (FINAL_CANDIDATE first, matching
            // the legend order above), not alphabetically by symbol. Unknown
            // statuses sort last; symbol is only a tiebreaker within a status.
            const rankA = STATUS_RANK[a.status] ?? STATUS_ORDER.length;
            const rankB = STATUS_RANK[b.status] ?? STATUS_ORDER.length;
            if (rankA !== rankB) return rankA - rankB;
            return a.nse_symbol.localeCompare(b.nse_symbol);
          })
          .map((c) => (
          <button
            key={c.stock_id}
            type="button"
            onClick={() => navigate(`/evidence/${c.stock_id}`)}
            className="text-left bg-white p-4 rounded-lg shadow-sm border border-gray-200 min-h-[44px] min-w-0"
          >
            <div className="flex justify-between gap-2 min-w-0">
              <div className="min-w-0">
                <div className="font-bold text-gray-900 break-words">{c.nse_symbol}</div>
                <div className="text-xs text-gray-600 break-words">{c.company_name}</div>
              </div>
              <span className={`shrink-0 text-xs font-semibold px-2 py-1 rounded ${statusBadgeClass(c.status)}`}>
                {c.status}
              </span>
            </div>
            <p className="text-xs text-gray-700 mt-2 break-words">
              {c.decisive_reason || c.classification_meaning || CLASSIFICATION_MEANING[c.status] || c.status}
            </p>
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs min-w-0">
              <div className="min-w-0">
                <span className="text-gray-500 block">Last stored close</span>
                <span className="break-words">{displayValue(c.latest_close)}</span>
                <span className="text-gray-500 block">As of {asOfByStock[c.stock_id] || 'N/A'}</span>
              </div>
              <div className="min-w-0"><span className="text-gray-500 block">SMA50</span><span className="break-words">{displayValue(c.technical?.SMA50)}</span></div>
              <div className="min-w-0"><span className="text-gray-500 block">SMA200</span><span className="break-words">{displayValue(c.technical?.SMA200)}</span></div>
              <div className="min-w-0"><span className="text-gray-500 block">Revenue</span><span className="break-words">{displayValue(c.revenue)} ({c.revenue_status || 'UNKNOWN'})</span></div>
              <div className="min-w-0"><span className="text-gray-500 block">close &gt; SMA50</span>{criterionResult(c.close_gt_sma50)}</div>
              <div className="min-w-0"><span className="text-gray-500 block">SMA50 &gt; SMA200</span>{criterionResult(c.sma50_gt_sma200)}</div>
              <div className="min-w-0"><span className="text-gray-500 block">RR ratio</span><span className="break-words">{c.rr_available ? displayValue(c.rr_ratio) : 'N/A'}</span></div>
              <div className="min-w-0"><span className="text-gray-500 block">Eval date</span>{c.evaluation_date ? c.evaluation_date.slice(0, 10) : 'N/A'}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
