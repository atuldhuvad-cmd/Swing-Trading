import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { evidenceApi, tradesApi } from '../api';
import { asOfDate } from './candidateStatus';

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [latestMarketDate, setLatestMarketDate] = useState<string | null>(null);
  const [staleCount, setStaleCount] = useState(0);
  const [stockCount, setStockCount] = useState(0);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [planned, setPlanned] = useState(0);
  const [open, setOpen] = useState(0);

  useEffect(() => {
    Promise.all([evidenceApi.getMarketData(), evidenceApi.getCandidates(), tradesApi.getTrades()])
      .then(([market, candidates, trades]) => {
        const rows = market.items || [];
        setStockCount(rows.length);
        const dates = rows
          .map((r: { latest_trading_date?: string | null }) => asOfDate(r.latest_trading_date))
          .filter((d: string | null): d is string => Boolean(d))
          .sort();
        setLatestMarketDate(dates.length ? dates[dates.length - 1] : null);
        setStaleCount(rows.filter((r: { sma200_ready?: boolean }) => !r.sma200_ready).length);
        const mix: Record<string, number> = {};
        for (const row of candidates.items || []) {
          mix[row.status] = (mix[row.status] || 0) + 1;
        }
        setCounts(mix);
        const list = Array.isArray(trades) ? trades : [];
        setPlanned(list.filter((t: { status: string }) => t.status === 'PLANNED').length);
        setOpen(list.filter((t: { status: string }) => t.status === 'OPEN').length);
      })
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load home'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4 min-w-0">
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <h1 className="text-xl font-bold text-gray-900">Home</h1>
        <p className="text-xs text-gray-700 mt-2 break-words">
          This app shows stored research evidence so you can decide. It does not decide BUY or SELL.
        </p>
      </div>

      {loading && <div className="text-sm text-gray-500">Loading home…</div>}
      {error && <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200">{error}</div>}

      {!loading && !error && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white p-4 rounded-lg border border-gray-200 min-w-0">
              <div className="text-xs text-gray-500">Last stored market-data date</div>
              <div className="text-lg font-semibold text-gray-900 break-words">{latestMarketDate || 'N/A'}</div>
              <p className="text-[11px] text-gray-600 mt-1 break-words">Stored OHLCV only. Not a live price.</p>
            </div>
            <div className="bg-white p-4 rounded-lg border border-gray-200 min-w-0">
              <div className="text-xs text-gray-500">Data readiness</div>
              <div className="text-lg font-semibold text-gray-900">{stockCount} stocks</div>
              <p className="text-[11px] text-gray-600 mt-1 break-words">
                {staleCount} not SMA200-ready. Review Data if coverage looks old.
              </p>
            </div>
          </div>

          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h2 className="font-semibold text-gray-900">Phase 5 classifications</h2>
            <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              {['FINAL_CANDIDATE', 'WATCH', 'REJECTED', 'INSUFFICIENT_DATA'].map((status) => (
                <div key={status} className="min-w-0">
                  <span className="text-gray-500 block break-words">{status}</span>
                  <span className="text-base font-semibold text-gray-900">{counts[status] || 0}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <div className="text-xs text-gray-500">Planned trades</div>
              <div className="text-lg font-semibold text-gray-900">{planned}</div>
            </div>
            <div className="bg-white p-4 rounded-lg border border-gray-200">
              <div className="text-xs text-gray-500">Open trades</div>
              <div className="text-lg font-semibold text-gray-900">{open}</div>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Link to="/final-candidates" className="min-h-[44px] inline-flex items-center justify-center px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg">
              Review Candidates
            </Link>
            <Link to="/trades" className="min-h-[44px] inline-flex items-center justify-center px-4 py-2 bg-white border border-gray-300 text-gray-800 text-sm font-medium rounded-lg">
              Record Execution / Trade Journal
            </Link>
            <Link to="/data" className="min-h-[44px] inline-flex items-center justify-center px-4 py-2 bg-white border border-gray-300 text-gray-800 text-sm font-medium rounded-lg">
              Update / Review Data
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
