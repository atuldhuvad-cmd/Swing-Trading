import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BookOpen, Plus } from 'lucide-react';
import { tradesApi, stocksApi } from '../api';
import { OpenTradeModal, CloseTradeModal, CancelTradeModal } from './TradeLifecycleModals';

// ─── Helpers ───────────────────────────────────────────────────────────────

function fmtPrice(v: unknown): string | null {
  if (v == null || v === '') return null;
  const n = Number(v);
  if (!isFinite(n)) return null;
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(v: string | null | undefined): string | null {
  if (!v) return null;
  return v.slice(0, 16).replace('T', ' ');
}

function statusBadgeCls(status: string): string {
  const map: Record<string, string> = {
    PLANNED: 'bg-yellow-100 text-yellow-800',
    OPEN: 'bg-green-100 text-green-800',
    CLOSED: 'bg-gray-200 text-gray-700',
    CANCELLED: 'bg-red-100 text-red-700',
  };
  return map[status] ?? 'bg-gray-100 text-gray-700';
}

function cardBorderCls(status: string): string {
  const map: Record<string, string> = {
    PLANNED: 'border-yellow-200',
    OPEN: 'border-green-300',
    CLOSED: 'border-gray-200',
    CANCELLED: 'border-red-100',
  };
  return map[status] ?? 'border-gray-200';
}

// ─── InfoRow: a single labelled data point ─────────────────────────────────

function InfoRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value == null || value === '') return null;
  return (
    <div className="text-xs min-w-0">
      <span className="text-gray-500">{label}: </span>
      <span className="text-gray-800 font-medium break-words">{value}</span>
    </div>
  );
}

// ─── Modal union type ──────────────────────────────────────────────────────

type ModalState =
  | { type: 'open'; trade: any }
  | { type: 'close'; trade: any }
  | { type: 'cancel'; trade: any }
  | null;

// ─── TradeJournal ──────────────────────────────────────────────────────────

export default function TradeJournal() {
  const [trades, setTrades] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [stocks, setStocks] = useState<Record<number, any>>({});
  const [modal, setModal] = useState<ModalState>(null);

  const loadData = () => {
    setLoading(true);
    Promise.all([tradesApi.getTrades(), stocksApi.getStocks()])
      .then(([tRes, sRes]) => {
        setTrades(tRes);
        const stockList: any[] = Array.isArray(sRes) ? sRes : (sRes?.items ?? []);
        setStocks(
          stockList.reduce((acc: Record<number, any>, s: any) => {
            acc[s.stock_id] = s;
            return acc;
          }, {}),
        );
      })
      .catch(err => console.error('TradeJournal load error:', err))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadData(); }, []);

  const handleSuccess = () => {
    setModal(null);
    loadData();
  };

  return (
    <div className="space-y-4 min-w-0">
      {/* Page header */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2 min-w-0">
          <BookOpen size={22} className="shrink-0 text-blue-600" />
          <span className="min-w-0 break-words">Trade Journal</span>
        </h1>
        <Link
          to="/final-candidates"
          id="new-trade-plan-link"
          className="shrink-0 flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition min-h-[44px]"
        >
          <Plus size={16} />
          <span>New Plan</span>
        </Link>
      </div>

      <p className="text-xs text-amber-800">
        Personal execution journal only. Not a trading recommendation.
      </p>

      {/* Loading */}
      {loading && (
        <div className="text-sm text-gray-500 text-center py-10">Loading trades…</div>
      )}

      {/* Empty state */}
      {!loading && trades.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-500 text-sm space-y-2">
          <p>No trades in journal yet.</p>
          <Link
            to="/final-candidates"
            className="text-blue-600 hover:underline text-sm"
          >
            Browse candidates to plan a trade →
          </Link>
        </div>
      )}

      {/* Trade cards */}
      <div className="space-y-3">
        {trades.map(t => {
          const stock = stocks[t.stock_id] ?? null;
          const isTerminal = t.status === 'CLOSED' || t.status === 'CANCELLED';
          const hasPnl = t.gross_pnl != null;
          const pnlNum = hasPnl ? Number(t.gross_pnl) : 0;
          const netPnlNum = t.net_pnl != null ? Number(t.net_pnl) : null;

          return (
            <div
              key={t.trade_id}
              className={`bg-white rounded-xl border p-4 space-y-3 min-w-0 ${cardBorderCls(t.status)}`}
            >
              {/* ── Header ── */}
              <div className="flex items-start justify-between gap-2 min-w-0">
                <div className="min-w-0">
                  <div className="font-bold text-gray-900 break-words text-base">
                    {stock?.nse_symbol ?? `Stock #${t.stock_id}`}
                  </div>
                  {stock?.company_name && (
                    <div className="text-xs text-gray-500 break-words mt-0.5">
                      {stock.company_name}
                    </div>
                  )}
                </div>
                <span
                  className={`shrink-0 text-xs font-semibold px-2.5 py-1 rounded-full ${statusBadgeCls(t.status)}`}
                >
                  {t.status}
                </span>
              </div>

              {/* ── Planned prices / quantity ── */}
              {(t.planned_entry_price != null ||
                t.planned_stop_price != null ||
                t.planned_target_price != null ||
                t.quantity != null) && (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1.5 min-w-0">
                  <InfoRow label="Planned entry" value={fmtPrice(t.planned_entry_price)} />
                  <InfoRow label="Planned stop" value={fmtPrice(t.planned_stop_price)} />
                  <InfoRow label="Planned target" value={fmtPrice(t.planned_target_price)} />
                  {t.status === 'PLANNED' && <InfoRow label="Qty" value={t.quantity} />}
                </div>
              )}

              {/* ── Execution data (entry) ── */}
              {(t.entry_price != null ||
                t.entry_date != null ||
                t.entry_price_source) && (
                <div className="border-t border-gray-100 pt-2 space-y-1 min-w-0">
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1 min-w-0">
                    <InfoRow label="Entry price" value={fmtPrice(t.entry_price)} />
                    <InfoRow label="Entry date" value={fmtDate(t.entry_date)} />
                    <InfoRow label="Qty" value={t.quantity} />
                  </div>
                  {t.entry_price_source && (
                    <div className="text-xs min-w-0">
                      <span className="text-gray-500">Entry source: </span>
                      <span
                        className="text-gray-800 font-medium break-words"
                        data-testid="entry-price-source"
                      >
                        {t.entry_price_source}
                      </span>
                    </div>
                  )}
                  {t.entry_note && (
                    <div className="text-xs text-gray-500 break-words italic">{t.entry_note}</div>
                  )}
                </div>
              )}

              {/* ── Execution data (exit) ── */}
              {(t.exit_price != null ||
                t.exit_date != null ||
                t.exit_price_source) && (
                <div className="border-t border-gray-100 pt-2 space-y-1 min-w-0">
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1 min-w-0">
                    <InfoRow label="Exit price" value={fmtPrice(t.exit_price)} />
                    <InfoRow label="Exit date" value={fmtDate(t.exit_date)} />
                  </div>
                  {t.exit_price_source && (
                    <div className="text-xs min-w-0">
                      <span className="text-gray-500">Exit source: </span>
                      <span
                        className="text-gray-800 font-medium break-words"
                        data-testid="exit-price-source"
                      >
                        {t.exit_price_source}
                      </span>
                    </div>
                  )}
                  {t.exit_note && (
                    <div className="text-xs text-gray-500 break-words italic">{t.exit_note}</div>
                  )}
                </div>
              )}

              {t.status === 'CLOSED' && (
                <div className="border-t border-gray-100 pt-2 space-y-1 min-w-0" data-testid="closed-review">
                  <div className="text-xs font-semibold text-gray-800">Review</div>
                  <InfoRow label="Planned entry" value={fmtPrice(t.planned_entry_price)} />
                  <InfoRow label="Actual entry" value={fmtPrice(t.entry_price)} />
                  <InfoRow label="Planned target" value={fmtPrice(t.planned_target_price)} />
                  <InfoRow label="Actual exit" value={fmtPrice(t.exit_price)} />
                  <InfoRow label="Quantity" value={t.quantity} />
                  {hasPnl && <InfoRow label="Gross P&L (backend)" value={fmtPrice(t.gross_pnl)} />}
                  {netPnlNum != null && <InfoRow label="Net P&L (backend)" value={fmtPrice(t.net_pnl)} />}
                  {t.exit_note && (
                    <div className="text-xs min-w-0">
                      <span className="text-gray-500">Why I exited: </span>
                      <span className="text-gray-800 break-words">{t.exit_note}</span>
                    </div>
                  )}
                </div>
              )}

              {hasPnl && t.status !== 'CLOSED' && (
                <div className="border-t border-gray-100 pt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm min-w-0">
                  <div>
                    <span className="text-xs text-gray-500">Gross P&amp;L: </span>
                    <span
                      className={`font-bold ${pnlNum > 0 ? 'text-green-600' : pnlNum < 0 ? 'text-red-600' : 'text-gray-700'}`}
                    >
                      {fmtPrice(t.gross_pnl)}
                    </span>
                  </div>
                  {netPnlNum != null && (
                    <div>
                      <span className="text-xs text-gray-500">Net P&amp;L: </span>
                      <span
                        className={`font-bold ${netPnlNum > 0 ? 'text-green-600' : netPnlNum < 0 ? 'text-red-600' : 'text-gray-700'}`}
                      >
                        {fmtPrice(t.net_pnl)}
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* ── Evidence linkage ── */}
              {(t.candidate_evaluation_id || t.risk_reward_result_id) && (
                <div className="border-t border-gray-100 pt-2 flex flex-wrap gap-x-3 gap-y-0.5 items-center min-w-0">
                  {t.candidate_evaluation_id && (
                    <span className="text-xs text-gray-400">Eval #{t.candidate_evaluation_id}</span>
                  )}
                  {t.risk_reward_result_id && (
                    <span className="text-xs text-gray-400">R/R #{t.risk_reward_result_id}</span>
                  )}
                  {t.candidate_evaluation_id && (
                    <Link
                      to={`/evidence/${t.stock_id}`}
                      className="text-xs text-blue-500 hover:underline break-words"
                    >
                      View evidence →
                    </Link>
                  )}
                </div>
              )}

              {/* ── Trade notes ── */}
              {t.trade_notes && (
                <div className="border-t border-gray-100 pt-2 text-xs text-gray-500 break-words">
                  {t.status === 'CLOSED' ? 'Notes / what I learned: ' : ''}
                  {t.trade_notes}
                </div>
              )}

              {/* ── Lifecycle actions ── */}
              {!isTerminal && (
                <div className="border-t border-gray-100 pt-3 flex flex-wrap gap-2">
                  {t.status === 'PLANNED' && (
                    <>
                      <button
                        id={`open-trade-btn-${t.trade_id}`}
                        onClick={() => setModal({ type: 'open', trade: t })}
                        className="px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-lg hover:bg-green-700 transition min-h-[44px]"
                      >
                        Record Entry
                      </button>
                      <button
                        id={`cancel-trade-btn-${t.trade_id}`}
                        onClick={() => setModal({ type: 'cancel', trade: t })}
                        className="px-4 py-2 bg-white border border-red-300 text-red-600 text-sm font-semibold rounded-lg hover:bg-red-50 transition min-h-[44px]"
                      >
                        Cancel Plan
                      </button>
                    </>
                  )}
                  {t.status === 'OPEN' && (
                    <button
                      id={`close-trade-btn-${t.trade_id}`}
                      onClick={() => setModal({ type: 'close', trade: t })}
                      className="px-4 py-2 bg-gray-700 text-white text-sm font-semibold rounded-lg hover:bg-gray-800 transition min-h-[44px]"
                    >
                      Record Exit
                    </button>
                  )}
                </div>
              )}

              {/* ── Terminal state label ── */}
              {isTerminal && (
                <div className="border-t border-gray-100 pt-2">
                  <span
                    className={`text-xs font-medium ${
                      t.status === 'CLOSED' ? 'text-gray-400' : 'text-red-400'
                    }`}
                    data-testid="terminal-label"
                  >
                    ● {t.status === 'CLOSED' ? 'Closed — no further actions' : 'Cancelled — no further actions'}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Lifecycle Modals ── */}
      {modal?.type === 'open' && (
        <OpenTradeModal
          trade={modal.trade}
          stock={stocks[modal.trade.stock_id] ?? null}
          onClose={() => setModal(null)}
          onSuccess={handleSuccess}
        />
      )}
      {modal?.type === 'close' && (
        <CloseTradeModal
          trade={modal.trade}
          stock={stocks[modal.trade.stock_id] ?? null}
          onClose={() => setModal(null)}
          onSuccess={handleSuccess}
        />
      )}
      {modal?.type === 'cancel' && (
        <CancelTradeModal
          trade={modal.trade}
          stock={stocks[modal.trade.stock_id] ?? null}
          onClose={() => setModal(null)}
          onSuccess={handleSuccess}
        />
      )}
    </div>
  );
}
