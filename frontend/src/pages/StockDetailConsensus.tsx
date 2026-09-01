import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { consensusApi } from '../api';
import BackLink from '../components/BackLink';
import { Users, TrendingUp, ShieldCheck, ExternalLink, Award, ChevronDown, ChevronUp } from 'lucide-react';

interface SourceReference {
  source_reference_id: number;
  source_type_id: number;
  publication_name?: string;
  url?: string;
  source_date?: string;
  verification_status: string;
  reliability_score?: number;
  verification_notes?: string;
}

interface Contributor {
  recommendation_id: number;
  broker_id: number;
  broker_canonical_name: string;
  broker_display_name: string;
  stream_name?: string;
  recommendation_date: string;
  original_rating: string;
  normalized_rating: string;
  recommended_price?: number;
  entry_price_low?: number;
  entry_price_high?: number;
  target_price?: number;
  stop_loss?: number;
  time_horizon_text?: string;
  analyst_name?: string;
  lifecycle_status: string;
  age_days: number;
  freshness_category: string;
  verification_status: string;
  sources: SourceReference[];
}

interface StockConsensus {
  stock_id: number;
  nse_symbol: string;
  bse_symbol?: string;
  company_name: string;
  isin?: string;
  sector?: string;
  industry?: string;
  market_cap_category?: string;
  listing_status: string;
  cmp?: number;
  cmp_updated_at?: string;
  metrics: {
    unique_broker_count: number;
    bullish_broker_count: number;
    bullish_percentage: number;
    total_target_count: number;
    target_coverage_pct: number;
    min_target?: number;
    max_target?: number;
    avg_target?: number;
    median_target?: number;
    cmp?: number;
    avg_target_upside_pct?: number;
    median_target_upside_pct?: number;
    avg_age_days?: number;
    freshness_summary: string;
    rec_count_7d: number;
    rec_count_14d: number;
    rec_count_30d: number;
  };
  rating_breakdown: Array<{ rating: string; count: number; percentage: number }>;
  contributors: Contributor[];
}

export default function StockDetailConsensus() {
  const { stockId } = useParams<{ stockId: string }>();

  const [consensus, setConsensus] = useState<StockConsensus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRecId, setExpandedRecId] = useState<number | null>(null);

  useEffect(() => {
    if (!stockId) return;
    const fetchConsensus = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await consensusApi.getStockConsensus(parseInt(stockId, 10));
        setConsensus(res);
      } catch (err: any) {
        setError(err?.response?.data?.detail || 'Failed to load stock consensus');
      } finally {
        setLoading(false);
      }
    };
    fetchConsensus();
  }, [stockId]);

  if (loading) {
    return (
      <div className="space-y-2 min-w-0">
        <BackLink fallback="/broker-opinion" />
        <div className="text-center py-12 text-gray-500">Loading stock consensus...</div>
      </div>
    );
  }

  if (error || !consensus) {
    return (
      <div className="space-y-4 min-w-0">
        <BackLink fallback="/broker-opinion" />
        <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200">
          {error || 'Stock consensus data unavailable.'}
        </div>
      </div>
    );
  }

  const m = consensus.metrics;

  return (
    <div className="space-y-4 min-w-0">
      <BackLink fallback="/broker-opinion" />

      {/* Stock Header Card */}
      <div className="bg-white p-4 sm:p-6 rounded-lg shadow-sm border border-gray-200">
        <div className="flex flex-col sm:flex-row justify-between items-start gap-2">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-gray-900">{consensus.nse_symbol}</h1>
              {consensus.bse_symbol && <span className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">BSE: {consensus.bse_symbol}</span>}
              <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded font-semibold">{consensus.listing_status}</span>
              <Link to={`/evidence/${consensus.stock_id}`} className="text-xs font-medium text-blue-600 hover:underline ml-2 flex items-center">
                Phase 5 Evidence <ExternalLink className="w-3 h-3 ml-1" />
              </Link>
            </div>
            <h2 className="text-sm font-medium text-gray-600 mt-0.5">{consensus.company_name}</h2>
            <div className="flex flex-wrap gap-2 text-xs text-gray-500 mt-2">
              {consensus.sector && <span>Sector: <strong className="text-gray-700">{consensus.sector}</strong></span>}
              {consensus.industry && <span>• Industry: <strong className="text-gray-700">{consensus.industry}</strong></span>}
              {consensus.isin && <span>• ISIN: <strong className="text-gray-700">{consensus.isin}</strong></span>}
            </div>
          </div>

          <div className="bg-blue-50 p-3 rounded-lg border border-blue-100 text-right min-w-[140px]">
            <div className="text-xs text-blue-600 font-medium">Broker/consensus CMP</div>
            <div className="text-xl font-bold text-blue-900 mt-0.5">
              {consensus.cmp !== null && consensus.cmp !== undefined ? `₹${consensus.cmp.toLocaleString()}` : 'N/A'}
            </div>
            {consensus.cmp_updated_at && (
              <div className="text-[10px] text-blue-400 mt-0.5">
                Updated: {new Date(consensus.cmp_updated_at).toLocaleDateString()}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Consensus Metrics Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
          <div className="text-xs text-gray-500 flex items-center gap-1">
            <Users className="w-3.5 h-3.5 text-blue-500" /> Unique Brokers
          </div>
          <div className="text-xl font-bold text-gray-900 mt-1">{m.unique_broker_count}</div>
          <div className="text-xs text-green-600 font-medium mt-0.5">
            {m.bullish_percentage}% Bullish ({m.bullish_broker_count}/{m.unique_broker_count})
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
          <div className="text-xs text-gray-500">Avg / Median Target</div>
          <div className="text-lg font-bold text-gray-900 mt-1">
            {m.avg_target !== null && m.avg_target !== undefined ? `₹${m.avg_target}` : 'N/A'} / {m.median_target !== null && m.median_target !== undefined ? `₹${m.median_target}` : 'N/A'}
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            Range: ₹{m.min_target ?? 'N/A'} - ₹{m.max_target ?? 'N/A'}
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
          <div className="text-xs text-gray-500 flex items-center gap-1">
            <TrendingUp className="w-3.5 h-3.5 text-green-500" /> Target Upside %
          </div>
          <div className="text-lg font-bold text-green-600 mt-1">
            Avg: {m.avg_target_upside_pct !== null && m.avg_target_upside_pct !== undefined ? `${m.avg_target_upside_pct}%` : 'N/A'}
          </div>
          <div className="text-xs text-green-700 mt-0.5">
            Median: {m.median_target_upside_pct !== null && m.median_target_upside_pct !== undefined ? `${m.median_target_upside_pct}%` : 'N/A'}
          </div>
        </div>

        <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
          <div className="text-xs text-gray-500">Target Coverage & Rec Activity</div>
          <div className="text-lg font-bold text-gray-900 mt-1">{m.target_coverage_pct}%</div>
          <div className="text-xs text-gray-500 mt-0.5">
            Recs in 30d: {m.rec_count_30d} (7d: {m.rec_count_7d})
          </div>
        </div>
      </div>

      {/* Rating Distribution Breakdown */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <h3 className="text-sm font-bold text-gray-900 mb-2">Rating Distribution Breakdown</h3>
        <div className="flex flex-wrap gap-2">
          {consensus.rating_breakdown.map((r) => (
            <div key={r.rating} className="bg-gray-50 px-3 py-1.5 rounded-md border border-gray-200 text-xs">
              <span className="font-semibold text-gray-800">{r.rating}: </span>
              <span className="text-gray-600">{r.count} ({r.percentage}%)</span>
            </div>
          ))}
        </div>
      </div>

      {/* Broker Contributor List & Traceability */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <h3 className="text-base font-bold text-gray-900 mb-3 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-blue-600" /> Broker Contributors ({consensus.contributors.length})
        </h3>

        {consensus.contributors.length === 0 ? (
          <div className="text-sm text-gray-500 py-4 text-center">No active broker recommendations found for this stock.</div>
        ) : (
          <div className="space-y-3">
            {consensus.contributors.map((c) => {
              const isExpanded = expandedRecId === c.recommendation_id;
              return (
                <div key={c.recommendation_id} className="border border-gray-200 rounded-lg p-3 hover:border-gray-300 transition-colors">
                  <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-2">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-sm text-gray-900">{c.broker_display_name}</span>
                        <span className="text-xs px-2 py-0.5 rounded font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                          {c.normalized_rating}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                          c.freshness_category === 'FRESH' ? 'bg-green-100 text-green-800' :
                          c.freshness_category === 'RECENT' ? 'bg-teal-100 text-teal-800' :
                          c.freshness_category === 'MODERATE' ? 'bg-yellow-100 text-yellow-800' :
                          c.freshness_category === 'STALE' ? 'bg-orange-100 text-orange-800' :
                          'bg-gray-100 text-gray-700'}`}>
                          {c.freshness_category} ({c.age_days}d)
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                          c.verification_status === 'VERIFIED_PRIMARY' ? 'bg-green-50 text-green-700 border border-green-200' :
                          c.verification_status === 'VERIFIED_SECONDARY' ? 'bg-blue-50 text-blue-700 border border-blue-200' :
                          c.verification_status === 'PROVISIONAL' ? 'bg-yellow-50 text-yellow-700 border border-yellow-200' :
                          'bg-gray-50 text-gray-500 border border-gray-200'}`}>
                          {c.verification_status.replace('_', ' ')}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1 space-y-0.5">
                        <div>
                          Original: <span className="font-medium text-gray-700">{c.original_rating}</span>
                          {' • '}Analyst: {c.analyst_name || 'N/A'}
                          {' • '}Date: {new Date(c.recommendation_date).toLocaleDateString()}
                        </div>
                        {c.stream_name && (
                          <div>Stream: <span className="font-medium text-gray-700">{c.stream_name}</span></div>
                        )}
                        {c.time_horizon_text && (
                          <div>Horizon: <span className="font-medium text-gray-700">{c.time_horizon_text}</span></div>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-4 text-xs">
                      <div>
                        <span className="text-gray-500 block">Target</span>
                        <span className="font-bold text-gray-900">{c.target_price !== null && c.target_price !== undefined ? `₹${c.target_price}` : 'N/A'}</span>
                      </div>
                      <div>
                        <span className="text-gray-500 block">Stop Loss</span>
                        <span className="font-medium text-red-600">{c.stop_loss !== null && c.stop_loss !== undefined ? `₹${c.stop_loss}` : 'N/A'}</span>
                      </div>
                      <button
                        onClick={() => setExpandedRecId(isExpanded ? null : c.recommendation_id)}
                        className="p-1 border border-gray-200 rounded hover:bg-gray-50 text-gray-600"
                        title="Toggle Evidence Sources"
                      >
                        {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Expandable Evidence Traceability Details */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-gray-100 bg-gray-50 p-3 rounded-md text-xs space-y-2">
                      <div className="font-semibold text-gray-700 flex items-center gap-1">
                        <Award className="w-4 h-4 text-blue-500" /> Attached Evidence Sources ({c.sources.length})
                      </div>
                      {c.sources.length === 0 ? (
                        <div className="text-gray-400 italic">No source references attached to this recommendation.</div>
                      ) : (
                        <div className="space-y-1.5">
                          {c.sources.map((src) => (
                            <div key={src.source_reference_id} className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 min-w-0 bg-white p-2 rounded border border-gray-200">
                              <div className="min-w-0 break-words">
                                <span className="font-medium text-gray-800">{src.publication_name || 'Publication'}</span>
                                {src.source_date && <span className="text-gray-500 ml-2">• Date: {new Date(src.source_date).toLocaleDateString()}</span>}
                                <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-blue-50 text-blue-700 font-semibold">{src.verification_status}</span>
                              </div>
                              {src.url && (
                                <a
                                  href={src.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 hover:underline inline-flex items-center gap-0.5 break-all"
                                >
                                  View Link <ExternalLink className="w-3 h-3" />
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
