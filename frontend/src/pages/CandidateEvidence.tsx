import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { evidenceApi } from '../api';
import BackLink from '../components/BackLink';
import { CLASSIFICATION_MEANING, asOfDate, criterionResult, displayValue, statusBadgeClass } from './candidateStatus';

function num(v: unknown): number | null {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function vsAverage(label: string, close: unknown, average: unknown) {
  const c = num(close);
  const a = num(average);
  if (c == null || a == null) return `This stock: ${label} is not stored.`;
  if (c > a) return `This stock: last stored close is above ${label}.`;
  if (c < a) return `This stock: last stored close is below ${label}.`;
  return `This stock: last stored close equals ${label}.`;
}

function IndicatorNote({
  title,
  value,
  what,
  meaning,
  phase5,
}: {
  title: string;
  value: unknown;
  what: string;
  meaning: string;
  phase5: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-gray-500">{title}</div>
      <div className="text-sm font-medium text-gray-900 break-words">{displayValue(value as string | number | null)}</div>
      <p className="text-[11px] text-gray-600 mt-1 break-words">{what}</p>
      <p className="text-[11px] text-gray-600 break-words">{meaning}</p>
      <p className="text-[11px] font-medium text-gray-800 break-words">{phase5}</p>
    </div>
  );
}

export default function CandidateEvidence() {
  const { stockId } = useParams();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!stockId) return;
    evidenceApi.getStockEvidence(Number(stockId))
      .then(setData)
      .catch((err) => setError(err?.response?.data?.detail || 'Failed to load evidence'))
      .finally(() => setLoading(false));
  }, [stockId]);

  if (loading) {
    return (
      <div className="space-y-2 min-w-0">
        <BackLink fallback="/final-candidates" />
        <div className="text-sm text-gray-500">Loading evidence...</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="space-y-2 min-w-0">
        <BackLink fallback="/final-candidates" />
        <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200">{error}</div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="space-y-2 min-w-0">
        <BackLink fallback="/final-candidates" />
        <div className="text-sm text-gray-500">No evidence payload.</div>
      </div>
    );
  }

  const tech = data.technical?.indicators || {};
  const rr = data.risk_reward;
  const classification = data.candidate?.classification || 'NONE';
  const hasEval = Boolean(data.candidate?.evaluation_id);
  const revenue = (data.fundamentals || []).find((m: { metric_name: string }) => m.metric_name === 'revenue');
  const rrAvailable = Boolean(rr && rr.rr_ratio);
  const close = data.technical?.latest_close;
  const closeAsOf = asOfDate(data.technical?.latest_trading_date);

  return (
    <div className="space-y-4 min-w-0">
      <BackLink fallback="/final-candidates" />
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <div className="flex flex-wrap justify-between items-start gap-2 min-w-0">
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-gray-900 break-words">Candidate Detail / Evidence</h1>
            <p className="text-sm text-gray-700 mt-1 break-words">{data.stock?.nse_symbol} - {data.stock?.company_name}</p>
          </div>
          {hasEval ? (
            <Link to={`/trades/plan/${stockId}`} className="shrink-0 px-3 py-2 bg-green-600 text-white text-sm font-medium rounded hover:bg-green-700 min-h-[44px] inline-flex items-center">
              Plan Trade
            </Link>
          ) : (
            <span className="shrink-0 px-3 py-2 bg-gray-200 text-gray-600 text-sm font-medium rounded min-h-[44px] inline-flex items-center">
              Plan unavailable
            </span>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className={`text-xs font-semibold px-2 py-1 rounded ${statusBadgeClass(classification)}`}>{classification}</span>
          <span className="text-xs text-gray-500">Eval {data.candidate?.evaluation_id ?? 'N/A'} — {data.candidate?.evaluation_date || 'N/A'}</span>
        </div>
        <p className="text-xs text-gray-700 mt-2 break-words">
          {data.candidate?.classification_meaning || CLASSIFICATION_MEANING[classification] || classification}
        </p>
        <p className="text-xs text-gray-800 mt-1 break-words">
          Reason: {data.candidate?.decisive_reason || 'N/A'}
        </p>
        <p className="text-xs text-gray-800 mt-2 break-words">
          FINAL_CANDIDATE = passes the current Phase 5 trend screen. It is not a BUY instruction.
        </p>
        {!hasEval && (
          <p className="text-xs text-red-800 mt-2 break-words">
            Plan Trade is unavailable until a Phase 5 evaluation is stored.
          </p>
        )}
        {hasEval && classification === 'WATCH' && (
          <p className="text-xs text-amber-800 mt-2 break-words">
            WATCH warning: trend confirmation did not pass. You may still plan a small real trade; the app does not decide BUY/SELL.
          </p>
        )}
        {hasEval && classification === 'REJECTED' && (
          <p className="text-xs text-red-800 mt-2 break-words">
            REJECTED warning: a required Phase 5 trend-screen check failed. You may still plan if you choose; this is not a BUY.
          </p>
        )}
        <p className="text-xs text-amber-800 mt-2 break-words">
          Not a guaranteed BUY. Not a trading recommendation. No guaranteed profitability.
        </p>
      </div>

      <section className="bg-white p-4 rounded-lg border border-gray-200 min-w-0">
        <h2 className="font-semibold text-gray-900 mb-1">1. Phase 5 decision evidence</h2>
        <p className="text-[11px] text-gray-600 mb-3 break-words">
          These stored checks decide FINAL_CANDIDATE / WATCH / REJECTED. Broker opinion is not used here.
        </p>
        <div className="grid grid-cols-2 gap-3 text-xs min-w-0 mb-3">
          <div className="min-w-0">
            <span className="text-gray-500 block">Last stored close</span>
            <span className="text-sm font-medium text-gray-900 break-words">{displayValue(close)}</span>
            <span className="text-gray-500 block">As of {closeAsOf || 'N/A'}</span>
          </div>
          <div className="min-w-0">
            <span className="text-gray-500 block">Sessions / SMA200 ready</span>
            <span className="text-sm font-medium text-gray-900">
              {displayValue(data.technical?.sessions)} / {data.technical?.sma200_ready ? 'YES' : 'NO'}
            </span>
            <p className="text-[11px] text-gray-600 mt-1">Phase 5 uses this: needs SMA200 history (≥200 sessions) and known SMA/ATR/revenue.</p>
          </div>
          <div className="min-w-0">
            <span className="text-gray-500 block">close &gt; SMA50</span>
            <span className="text-sm font-medium text-gray-900">{criterionResult(data.close_gt_sma50)}</span>
            <p className="text-[11px] text-gray-600 mt-1">Required Phase 5 trend check.</p>
          </div>
          <div className="min-w-0">
            <span className="text-gray-500 block">SMA50 &gt; SMA200</span>
            <span className="text-sm font-medium text-gray-900">{criterionResult(data.sma50_gt_sma200)}</span>
            <p className="text-[11px] text-gray-600 mt-1">Phase 5 confirmation. Fail usually means WATCH, not REJECTED.</p>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <IndicatorNote
            title="SMA50"
            value={tech.SMA50}
            what="Average close over the last 50 stored sessions."
            meaning={vsAverage('SMA50', close, tech.SMA50)}
            phase5="Phase 5 uses this: must be known, and last stored close must be above it."
          />
          <IndicatorNote
            title="SMA200"
            value={tech.SMA200}
            what="Average close over the last 200 stored sessions (longer trend)."
            meaning={vsAverage('SMA200', close, tech.SMA200)}
            phase5="Phase 5 uses this: must be known. SMA50 above SMA200 is confirmation only."
          />
          <IndicatorNote
            title="SMA20"
            value={tech.SMA20}
            what="Average close over the last 20 stored sessions (shorter trend)."
            meaning={vsAverage('SMA20', close, tech.SMA20)}
            phase5="Phase 5 uses this only as a known value, not a crossover rule."
          />
          <IndicatorNote
            title="ATR14"
            value={tech.ATR14}
            what="Typical daily price range over 14 sessions (volatility)."
            meaning={num(tech.ATR14) != null ? `This stock: typical range is ${displayValue(tech.ATR14)}.` : 'This stock: ATR is not stored.'}
            phase5="Phase 5 uses this only as a known value. It does not apply an ATR threshold."
          />
        </div>
        <div className="mt-4 pt-3 border-t border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900 mb-2">Revenue (Phase 5)</h3>
          {revenue ? (
            <div className="space-y-2">
              <div>
                <div className="text-xs text-gray-500">Revenue (Latest)</div>
                <div className="text-sm font-medium text-gray-900 break-words">
                  {displayValue(revenue.metric_value)} ({revenue.status || 'UNKNOWN'})
                </div>
                <p className="text-[11px] text-gray-600 mt-1">Phase 5 uses this: revenue must be known and positive.</p>
              </div>
              {data.fundamental_provenance?.source_line_item && (
                <div>
                  <div className="text-xs text-gray-500">Source line item</div>
                  <div className="text-sm font-medium text-gray-900 break-words">
                    {data.fundamental_provenance.source_line_item}
                  </div>
                </div>
              )}
              {data.fundamental_entity_type && (
                <div>
                  <div className="text-xs text-gray-500">Entity type</div>
                  <div className="text-sm font-medium text-gray-900 break-words">
                    {data.fundamental_entity_type}
                  </div>
                </div>
              )}
              <div>
                <div className="text-xs text-gray-500">Period</div>
                <div className="text-sm font-medium text-gray-900 break-words">
                  {revenue.period_ending || 'N/A'}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">No core fundamentals collected.</p>
          )}
        </div>
      </section>

      <section className="bg-white p-4 rounded-lg border border-gray-200">
        <h2 className="font-semibold text-gray-900 mb-1">2. Supporting technical evidence</h2>
        <p className="text-[11px] text-gray-600 mb-3 break-words">Shown for learning and traceability. Not Phase 5 pass/fail gates.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <IndicatorNote
            title="RSI14"
            value={tech.RSI14}
            what="A 0–100 momentum reading from recent closes."
            meaning={num(tech.RSI14) != null ? `This stock: RSI14 is ${displayValue(tech.RSI14)}.` : 'This stock: RSI is not stored.'}
            phase5="Phase 5 does not use RSI."
          />
          <IndicatorNote
            title="MACD"
            value={tech.MACD}
            what="Difference between two moving averages of close; used with its signal line."
            meaning={num(tech.MACD) != null ? `This stock: MACD is ${displayValue(tech.MACD)}.` : 'This stock: MACD is not stored.'}
            phase5="Phase 5 does not use MACD."
          />
          <IndicatorNote
            title="MACD signal"
            value={tech.MACD_signal}
            what="A slower average of MACD, used as context for MACD."
            meaning={`This stock: ${displayValue(tech.MACD_signal)}.`}
            phase5="Phase 5 does not use MACD signal."
          />
          <IndicatorNote
            title="MACD histogram"
            value={tech.MACD_hist}
            what="MACD minus its signal line."
            meaning={`This stock: ${displayValue(tech.MACD_hist)}.`}
            phase5="Phase 5 does not use MACD histogram."
          />
          <IndicatorNote
            title="ATR %"
            value={tech.ATR_percent}
            what="ATR as a percent of last stored close."
            meaning={`This stock: ${displayValue(tech.ATR_percent)}.`}
            phase5="Phase 5 does not use ATR % as a gate."
          />
          <IndicatorNote
            title="ROC20"
            value={tech.ROC20}
            what="Percent change in close over 20 sessions."
            meaning={`This stock: ${displayValue(tech.ROC20)}.`}
            phase5="Phase 5 does not use ROC20."
          />
          <IndicatorNote
            title="Breakout20"
            value={tech.Breakout20_status}
            what="Whether last stored close is above a 20-session high."
            meaning={`This stock: ${displayValue(tech.Breakout20_status)}.`}
            phase5="Phase 5 does not use Breakout20."
          />
          <IndicatorNote
            title="Liquidity20"
            value={tech.Liquidity20}
            what="Recent average traded value from stored sessions."
            meaning={`This stock: ${displayValue(tech.Liquidity20)}.`}
            phase5="Phase 5 does not use Liquidity20 as a gate."
          />
        </div>
      </section>

      <section className="bg-white p-4 rounded-lg border border-gray-200">
        <h2 className="font-semibold text-gray-900 mb-1">3. Risk / Reward</h2>
        <p className="text-[11px] text-gray-600 mb-3 break-words">
          Informational geometry from stored highs/lows. Not a Phase 5 rule and not an order.
        </p>
        {rrAvailable ? (
          <div className="grid grid-cols-2 gap-4">
            <IndicatorNote
              title="R/R Ratio"
              value={rr.rr_ratio}
              what="Reward per share divided by risk per share using stored support/resistance."
              meaning={`This stock: stored R/R is ${displayValue(rr.rr_ratio)}.`}
              phase5="Phase 5 does not use R/R."
            />
            <div>
              <div className="text-xs text-gray-500">Target</div>
              <div className="text-sm font-medium text-gray-900 break-words">{displayValue(rr.target)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Stop Loss</div>
              <div className="text-sm font-medium text-gray-900 break-words">{displayValue(rr.stop_loss ?? rr.stop)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Entry Reference</div>
              <div className="text-sm font-medium text-gray-900 break-words">{displayValue(rr.entry_reference ?? rr.entry)}</div>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-gray-500">RR N/A</p>
        )}
      </section>

      <section className="bg-white p-4 rounded-lg border border-gray-200">
        <h2 className="font-semibold text-gray-900">4. Broker opinion</h2>
        <p className="text-[11px] text-gray-600 mt-1 break-words">Display-only. Never used to classify candidates or to decide BUY/SELL.</p>
        {data.consensus?.status === 'CONSENSUS_AVAILABLE' && (
          <Link to={`/consensus/${stockId}`} className="text-xs font-medium text-blue-600 hover:underline">
            View Broker Consensus
          </Link>
        )}
        {data.consensus?.status === 'CONSENSUS_AVAILABLE' ? (
          <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-gray-500">Bullish Brokers</div>
              <div className="text-sm font-medium text-gray-900">
                {data.consensus.metrics?.bullish_broker_count ?? 0}/{data.consensus.metrics?.unique_broker_count ?? 0}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Avg Target</div>
              <div className="text-sm font-medium text-gray-900">
                {data.consensus.metrics?.avg_target != null ? `${data.consensus.metrics.avg_target} INR` : 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Freshness</div>
              <div className="text-sm font-medium text-gray-900">{data.consensus.metrics?.freshness_summary || 'N/A'}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Status</div>
              <div className="text-sm font-medium text-gray-900">Display-only evidence</div>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-gray-500">No reliable broker consensus available.</p>
        )}
      </section>
    </div>
  );
}
