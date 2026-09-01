import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import BackLink from '../components/BackLink';
import { evidenceApi } from '../api';

interface MarketRow {
  stock_id: number;
  nse_symbol: string;
  company_name: string;
  latest_trading_date?: string | null;
  session_count: number;
  sma200_ready: boolean;
  latest_import_status?: string | null;
  latest_import_filename?: string | null;
}

export default function MarketDataStatus() {
  const [items, setItems] = useState<MarketRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    evidenceApi.getMarketData()
      .then((res) => setItems(res.items || []))
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load market data status'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4 min-w-0">
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <BackLink fallback="/data" />
        <h1 className="text-xl font-bold text-gray-900">Market Data Status</h1>
        <p className="text-xs text-gray-500 mt-1">Session coverage and SMA200 readiness from stored daily OHLCV.</p>
        <Link to="/fundamentals/import" className="inline-flex items-center mt-3 min-h-[44px] text-sm text-blue-700">
          Manual fundamental import
        </Link>
      </div>
      {loading && <div className="text-sm text-gray-500">Loading market data...</div>}
      {error && <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200">{error}</div>}
      {!loading && !error && items.length === 0 && (
        <div className="bg-white p-8 text-center rounded-lg border text-gray-500">No stocks in master data.</div>
      )}
      <div className="grid grid-cols-1 gap-3">
        {items.map((row) => (
          <div key={row.stock_id} className="bg-white p-4 rounded-lg border border-gray-200">
            <div className="font-bold">{row.nse_symbol}</div>
            <div className="text-xs text-gray-600 break-words">{row.company_name}</div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <div><span className="text-gray-500 block">Latest trading date</span>{row.latest_trading_date ? String(row.latest_trading_date).slice(0, 10) : 'N/A'}</div>
              <div><span className="text-gray-500 block">Session count</span>{row.session_count}</div>
              <div><span className="text-gray-500 block">SMA200 ready</span>{row.sma200_ready ? 'YES' : 'NO'}</div>
              <div className="min-w-0"><span className="text-gray-500 block">Latest import</span><span className="break-words">{row.latest_import_status || 'N/A'}</span></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
