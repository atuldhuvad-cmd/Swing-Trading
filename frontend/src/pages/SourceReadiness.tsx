import { useState, useEffect, type ReactNode } from 'react';
import { consensusApi } from '../api';
import { CheckCircle, AlertCircle, Lock, FileText, Globe, XCircle, ChevronDown, ChevronUp, Radio } from 'lucide-react';

interface StreamInfo {
  stream_id: number;
  stream_name: string;
  stream_type: string;
  frequency: string;
  source_url?: string;
  last_checked?: string;
  last_successful_update?: string;
}

interface SourceReadinessItem {
  canonical_name: string;
  display_name: string;
  broker_id?: number;
  active: boolean;
  enabled_for_new_ingestion: boolean;
  streams: StreamInfo[];
  recommendation_count: number;
  readiness_category: string;
  collection_method: string;
  reasoning: string;
  notes?: string;
}

const CATEGORY_CONFIG: Record<string, { label: string; icon: ReactNode; color: string; bgColor: string; borderColor: string }> = {
  PUBLIC_STABLE: {
    label: 'Public Stable',
    icon: <CheckCircle className="w-4 h-4" />,
    color: 'text-green-700',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-200',
  },
  PUBLIC_UNSTABLE: {
    label: 'Public Unstable',
    icon: <AlertCircle className="w-4 h-4" />,
    color: 'text-yellow-700',
    bgColor: 'bg-yellow-50',
    borderColor: 'border-yellow-200',
  },
  LOGIN_REQUIRED: {
    label: 'Login Required',
    icon: <Lock className="w-4 h-4" />,
    color: 'text-orange-700',
    bgColor: 'bg-orange-50',
    borderColor: 'border-orange-200',
  },
  DOCUMENT_MANUAL: {
    label: 'Document Manual',
    icon: <FileText className="w-4 h-4" />,
    color: 'text-blue-700',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-200',
  },
  SECONDARY_ONLY: {
    label: 'Secondary Only',
    icon: <Globe className="w-4 h-4" />,
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
    borderColor: 'border-purple-200',
  },
  UNSUITABLE: {
    label: 'Unsuitable',
    icon: <XCircle className="w-4 h-4" />,
    color: 'text-red-700',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-200',
  },
};

export default function SourceReadiness() {
  const [items, setItems] = useState<SourceReadinessItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    const fetch = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await consensusApi.getSourceReadiness();
        setItems(data);
      } catch (err: any) {
        setError(err?.response?.data?.detail || 'Failed to load source readiness data');
      } finally {
        setLoading(false);
      }
    };
    fetch();
  }, []);

  const getCategoryConfig = (cat: string) => CATEGORY_CONFIG[cat] || CATEGORY_CONFIG['UNSUITABLE'];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white p-4 rounded-lg shadow-sm border border-gray-200">
        <div className="flex items-center gap-2 mb-1">
          <Radio className="w-5 h-5 text-blue-600" />
          <h1 className="text-xl font-bold text-gray-900">Source Collection Readiness</h1>
        </div>
        <p className="text-xs text-gray-500">
          Stage 6 assessment of data collection readiness for the five pilot Indian broker/research providers.
          No automated scraping is implemented. All data is ingested manually or via user-provided documents.
        </p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => (
            <span key={key} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border ${cfg.bgColor} ${cfg.color} ${cfg.borderColor}`}>
              {cfg.icon} {cfg.label}
            </span>
          ))}
        </div>
      </div>

      {/* Disclaimer */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800">
        <strong>Important:</strong> This application does NOT implement automated web scraping or API key access to brokerage systems.
        All recommendations are ingested manually from user-provided documents.
        No broker API keys are required for Phase 1.
        Automated web fetching is NOT implemented in Stage 6.
      </div>

      {/* Pilot Providers */}
      {loading ? (
        <div className="text-center py-8 text-gray-500 text-sm">Loading source readiness data...</div>
      ) : error ? (
        <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200">{error}</div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const cfg = getCategoryConfig(item.readiness_category);
            const isExpanded = expandedId === item.canonical_name;
            return (
              <div
                key={item.canonical_name}
                className={`bg-white rounded-lg shadow-sm border ${cfg.borderColor} overflow-hidden`}
              >
                {/* Provider Header */}
                <div
                  className="p-4 cursor-pointer"
                  onClick={() => setExpandedId(isExpanded ? null : item.canonical_name)}
                  role="button"
                  aria-expanded={isExpanded}
                >
                  <div className="flex justify-between items-start gap-2">
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="font-bold text-gray-900 text-sm">{item.display_name}</span>
                        {item.canonical_name !== item.display_name && (
                          <span className="text-xs text-gray-400">({item.canonical_name})</span>
                        )}
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold border ${cfg.bgColor} ${cfg.color} ${cfg.borderColor}`}>
                          {cfg.icon} {cfg.label}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-3 text-xs text-gray-500">
                        <span>Broker ID: {item.broker_id ?? 'N/A'}</span>
                        <span>Active: {item.active ? 'Yes' : 'No'}</span>
                        <span>Ingestion Enabled: {item.enabled_for_new_ingestion ? 'Yes' : 'No'}</span>
                        <span>Recs Ingested: {item.recommendation_count}</span>
                        <span>Streams: {item.streams.length}</span>
                      </div>
                    </div>
                    <div className="text-gray-400 flex-shrink-0">
                      {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
                    </div>
                  </div>
                </div>

                {/* Expanded Detail */}
                {isExpanded && (
                  <div className="border-t border-gray-100 p-4 bg-gray-50 space-y-3 text-sm">
                    {/* Collection method */}
                    <div>
                      <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Collection Method</div>
                      <div className="text-xs text-gray-700 font-medium">{item.collection_method.replace(/_/g, ' ')}</div>
                    </div>

                    {/* Reasoning */}
                    <div>
                      <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Readiness Assessment</div>
                      <div className="text-xs text-gray-700 leading-relaxed">{item.reasoning}</div>
                    </div>

                    {/* Notes */}
                    {item.notes && (
                      <div>
                        <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">Notes</div>
                        <div className="text-xs text-gray-700">{item.notes}</div>
                      </div>
                    )}

                    {/* Streams */}
                    <div>
                      <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-1">
                        Recommendation Streams ({item.streams.length})
                      </div>
                      {item.streams.length === 0 ? (
                        <div className="text-xs text-gray-400 italic">No streams configured.</div>
                      ) : (
                        <div className="space-y-1.5">
                          {item.streams.map((s) => (
                            <div key={s.stream_id} className="bg-white p-2 rounded border border-gray-200 text-xs">
                              <div className="font-medium text-gray-800">{s.stream_name}</div>
                              <div className="text-gray-500">{s.stream_type} • {s.frequency}</div>
                              {s.source_url && (
                                <a href={s.source_url} target="_blank" rel="noopener noreferrer"
                                  className="text-blue-600 hover:underline text-[10px] break-all"
                                  onClick={(e) => e.stopPropagation()}>
                                  {s.source_url}
                                </a>
                              )}
                              {s.last_checked && <div className="text-gray-400">Last checked: {new Date(s.last_checked).toLocaleDateString()}</div>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
