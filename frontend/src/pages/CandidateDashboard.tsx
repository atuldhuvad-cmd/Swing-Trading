import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { consensusApi } from '../api';
import { Filter, ArrowUpDown, ChevronRight, TrendingUp, Users, Clock } from 'lucide-react';
import BackLink from '../components/BackLink';

interface CandidateSummary {
  stock_id: number;
  nse_symbol: string;
  company_name: string;
  sector?: string;
  cmp?: number;
  unique_broker_count: number;
  bullish_broker_count: number;
  bullish_percentage: number;
  avg_target?: number;
  median_target?: number;
  avg_target_upside_pct?: number;
  median_target_upside_pct?: number;
  target_coverage_pct: number;
  rec_count_30d: number;
  avg_age_days?: number;
  freshness_summary: string;
  latest_rec_date?: string;
}

export default function CandidateDashboard() {
  const navigate = useNavigate();
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters state
  const [minBrokers, setMinBrokers] = useState<number>(1);
  const [minUpside, setMinUpside] = useState<string>('');
  const [minBullishPct, setMinBullishPct] = useState<string>('');
  const [maxAgeDays, setMaxAgeDays] = useState<string>('');
  const [verificationStatus, setVerificationStatus] = useState<string>('ALL');
  const [sortBy, setSortBy] = useState<string>('broker_count');
  const [sortOrder, setSortOrder] = useState<string>('desc');

  const [filterDrawerOpen, setFilterDrawerOpen] = useState(false);

  const fetchCandidates = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, any> = {
        min_brokers: minBrokers,
        verification_status: verificationStatus,
        sort_by: sortBy,
        sort_order: sortOrder,
      };
      if (minUpside !== '') params.min_upside = parseFloat(minUpside);
      if (minBullishPct !== '') params.min_bullish_pct = parseFloat(minBullishPct);
      if (maxAgeDays !== '') params.max_age_days = parseInt(maxAgeDays, 10);

      const res = await consensusApi.getCandidates(params);
      setCandidates(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load candidates');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidates();
  }, [minBrokers, minUpside, minBullishPct, maxAgeDays, verificationStatus, sortBy, sortOrder]);

  const getFreshnessBadge = (summary: string, avgAge?: number) => {
    if (summary === 'FRESH') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
          <Clock className="w-3 h-3 mr-1" /> Fresh ({avgAge !== undefined ? `${avgAge}d` : ''})
        </span>
      );
    } else if (summary === 'RECENT') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-teal-100 text-teal-800">
          <Clock className="w-3 h-3 mr-1" /> Recent ({avgAge !== undefined ? `${avgAge}d` : ''})
        </span>
      );
    } else if (summary === 'MODERATE') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
          <Clock className="w-3 h-3 mr-1" /> Moderate ({avgAge !== undefined ? `${avgAge}d` : ''})
        </span>
      );
    } else if (summary === 'STALE') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800">
          <Clock className="w-3 h-3 mr-1" /> Stale ({avgAge !== undefined ? `${avgAge}d` : ''})
        </span>
      );
    } else if (summary === 'AGED') {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
          <Clock className="w-3 h-3 mr-1" /> Aged ({avgAge !== undefined ? `${avgAge}d` : ''})
        </span>
      );
    }
    return <span className="text-xs text-gray-400">N/A</span>;
  };

  return (
    <div className="space-y-4">
      <BackLink fallback="/data" />
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <div>
          <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Users className="text-blue-600 w-5 h-5" /> Broker Opinion Universe
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Transparent broker consensus metrics ({total} stocks)
          </p>
        </div>
        <button
          onClick={() => setFilterDrawerOpen(!filterDrawerOpen)}
          className="inline-flex items-center justify-center px-3 py-1.5 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
        >
          <Filter className="w-4 h-4 mr-1 text-blue-600" /> Filters & Sort
        </button>
      </div>

      {/* Filter Controls (Collapsible Drawer / Bar) */}
      {filterDrawerOpen && (
        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-700">Min Brokers</label>
            <select
              value={minBrokers}
              onChange={(e) => setMinBrokers(Number(e.target.value))}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm text-sm p-1.5 border"
            >
              <option value={1}>Min 1 Broker</option>
              <option value={2}>Min 2 Brokers</option>
              <option value={3}>Min 3 Brokers</option>
              <option value={5}>Min 5 Brokers</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700">Min Upside %</label>
            <input
              type="number"
              placeholder="e.g. 15"
              value={minUpside}
              onChange={(e) => setMinUpside(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm text-sm p-1.5 border"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700">Min Bullish %</label>
            <input
              type="number"
              placeholder="e.g. 70"
              value={minBullishPct}
              onChange={(e) => setMinBullishPct(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm text-sm p-1.5 border"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700">Max Age (Days)</label>
            <input
              type="number"
              placeholder="e.g. 60"
              value={maxAgeDays}
              onChange={(e) => setMaxAgeDays(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm text-sm p-1.5 border"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700">Verification Filter</label>
            <select
              value={verificationStatus}
              onChange={(e) => setVerificationStatus(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm text-sm p-1.5 border"
            >
              <option value="ALL">All Evidence Statuses</option>
              <option value="VERIFIED_ONLY">Verified Only (Primary/Secondary)</option>
              <option value="VERIFIED_PRIMARY">Verified Primary Only</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700">Sort By</label>
            <div className="flex gap-1 mt-1">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="block w-full rounded-md border-gray-300 shadow-sm text-sm p-1.5 border"
              >
                <option value="broker_count">Broker Count</option>
                <option value="avg_upside">Avg Target Upside %</option>
                <option value="median_upside">Median Target Upside %</option>
                <option value="recent_activity">Recent Activity (30d)</option>
                <option value="symbol">Symbol</option>
              </select>
              <button
                onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                className="px-2 py-1.5 border border-gray-300 rounded-md bg-gray-50 text-gray-600 hover:bg-gray-100"
                title="Toggle sort direction"
              >
                <ArrowUpDown className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main Candidate Grid / Cards */}
      {loading ? (
        <div className="text-center py-8 text-gray-500 text-sm">Loading broker consensus...</div>
      ) : error ? (
        <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200">{error}</div>
      ) : candidates.length === 0 ? (
        <div className="bg-white p-8 text-center rounded-lg border border-gray-200 text-gray-500">
          No stocks match the selected criteria.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {candidates.map((c) => (
            <div
              key={c.stock_id}
              onClick={() => navigate(`/consensus/${c.stock_id}`)}
              className="bg-white p-4 rounded-lg shadow-sm border border-gray-200 hover:border-blue-300 hover:shadow transition-all cursor-pointer"
            >
              {/* Card Top Header */}
              <div className="flex justify-between items-start mb-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-base text-gray-900">{c.nse_symbol}</span>
                    {c.sector && <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">{c.sector}</span>}
                  </div>
                  <div className="text-xs text-gray-600">{c.company_name}</div>
                </div>

                <div className="text-right">
                  <div className="text-xs text-gray-500">Broker/consensus CMP</div>
                  <div className="font-bold text-sm text-gray-900">
                    {c.cmp !== null && c.cmp !== undefined ? `₹${c.cmp.toLocaleString()}` : 'N/A'}
                  </div>
                </div>
              </div>

              {/* Badges Bar */}
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                  <Users className="w-3 h-3 mr-1" /> {c.unique_broker_count} {c.unique_broker_count === 1 ? 'Broker' : 'Brokers'}
                </span>

                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-green-50 text-green-700 border border-green-200">
                  <TrendingUp className="w-3 h-3 mr-1" /> {c.bullish_percentage}% Bullish ({c.bullish_broker_count}/{c.unique_broker_count})
                </span>

                {getFreshnessBadge(c.freshness_summary, c.avg_age_days)}
              </div>

              {/* Metrics Breakdown Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-gray-100 text-xs">
                <div>
                  <span className="text-gray-500 block">Avg Target</span>
                  <span className="font-medium text-gray-800">{c.avg_target !== null && c.avg_target !== undefined ? `₹${c.avg_target}` : 'N/A'}</span>
                  {c.avg_target_upside_pct !== null && c.avg_target_upside_pct !== undefined && (
                    <span className={`block font-semibold ${c.avg_target_upside_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {c.avg_target_upside_pct >= 0 ? '+' : ''}{c.avg_target_upside_pct}%
                    </span>
                  )}
                </div>

                <div>
                  <span className="text-gray-500 block">Median Target</span>
                  <span className="font-medium text-gray-800">{c.median_target !== null && c.median_target !== undefined ? `₹${c.median_target}` : 'N/A'}</span>
                  {c.median_target_upside_pct !== null && c.median_target_upside_pct !== undefined && (
                    <span className={`block font-semibold ${c.median_target_upside_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {c.median_target_upside_pct >= 0 ? '+' : ''}{c.median_target_upside_pct}%
                    </span>
                  )}
                </div>

                <div>
                  <span className="text-gray-500 block">Target Coverage</span>
                  <span className="font-medium text-gray-800">{c.target_coverage_pct}%</span>
                </div>

                <div>
                  <span className="text-gray-500 block">Rec Activity (30d)</span>
                  <span className="font-medium text-gray-800">{c.rec_count_30d} recs</span>
                </div>
              </div>

              {/* Card Footer Link */}
              <div className="mt-3 flex justify-end items-center text-xs text-blue-600 font-medium hover:underline">
                View Full Consensus Details <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
