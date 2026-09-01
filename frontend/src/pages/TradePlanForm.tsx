import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { tradesApi, evidenceApi } from '../api';
import BackLink, { hasInAppHistory } from '../components/BackLink';

export default function TradePlanForm() {
  const { stockId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const [form, setForm] = useState({
    planned_entry_price: '',
    planned_stop_price: '',
    planned_target_price: '',
    risk_amount: '',
    quantity: '',
    trade_notes: ''
  });
  const [positionResult, setPositionResult] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stockId) return;
    evidenceApi.getStockEvidence(Number(stockId))
      .then(res => {
        setData(res);
        if (res.risk_reward) {
          setForm(f => ({
            ...f,
            planned_entry_price: res.risk_reward.entry_reference || res.risk_reward.entry || '',
            planned_stop_price: res.risk_reward.stop_loss || res.risk_reward.stop || '',
            planned_target_price: res.risk_reward.target || '',
          }));
        }
      })
      .finally(() => setLoading(false));
  }, [stockId]);

  const handleCalc = async () => {
    setError(null);
    if (!form.planned_entry_price || !form.planned_stop_price || !form.risk_amount) {
      setError('Please fill Entry, Stop, and Risk Capital to calculate position size.');
      return;
    }
    try {
      const res = await tradesApi.calculatePositionSize({
        entry_price: Number(form.planned_entry_price),
        stop_price: Number(form.planned_stop_price),
        max_risk_amount: Number(form.risk_amount)
      });
      setPositionResult(res);
    } catch {
      setError('Position-size calculation failed. Check the backend and try again.');
    }
  };

  const handleSave = async () => {
    if (submitting) return;
    setError(null);
    try {
      setSubmitting(true);
      const qty = form.quantity.trim() ? Number(form.quantity) : null;
      await tradesApi.createTrade({
        stock_id: Number(stockId),
        candidate_evaluation_id: data?.candidate?.evaluation_id,
        risk_reward_result_id: data?.risk_reward?.result_id,
        status: 'PLANNED',
        side: 'LONG',
        planned_entry_price: form.planned_entry_price ? Number(form.planned_entry_price) : null,
        planned_stop_price: form.planned_stop_price ? Number(form.planned_stop_price) : null,
        planned_target_price: form.planned_target_price ? Number(form.planned_target_price) : null,
        quantity: qty != null && qty > 0 ? qty : null,
        trade_notes: form.trade_notes
      });
      navigate('/trades');
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to save planned trade.');
      setSubmitting(false);
    }
  };

  const evidenceFallback = stockId ? `/evidence/${stockId}` : '/final-candidates';
  const classification = data?.candidate?.classification || 'NONE';
  const hasEval = Boolean(data?.candidate?.evaluation_id);

  if (loading) {
    return (
      <div className="space-y-2 min-w-0">
        <BackLink fallback={evidenceFallback} />
        <div className="text-sm text-gray-500">Loading...</div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl bg-white p-4 sm:p-6 rounded border space-y-4 min-w-0">
      <BackLink fallback={evidenceFallback} />
      <h1 className="text-xl font-bold break-words">Plan Trade: {data?.stock?.nse_symbol}</h1>
      <p className="text-xs text-amber-800">Personal plan only — not an order, and not a trading recommendation.</p>
      <p className="text-xs text-gray-700 break-words">
        You enter the quantity. The position-size number is information only and is never applied as your trade size.
      </p>

      {!hasEval && (
        <p className="text-sm text-red-800 bg-red-50 border border-red-200 rounded p-3">
          Plan Trade is unavailable until a Phase 5 evaluation is stored.
        </p>
      )}
      {hasEval && classification === 'WATCH' && (
        <p className="text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded p-3">
          WATCH warning: trend confirmation did not pass. You may still save a plan; the app does not decide BUY/SELL.
        </p>
      )}
      {hasEval && classification === 'REJECTED' && (
        <p className="text-sm text-red-900 bg-red-50 border border-red-200 rounded p-3">
          REJECTED warning: a required Phase 5 trend-screen check failed. You may still save a plan if you choose; this is not a BUY.
        </p>
      )}
      
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 min-w-0">
        <div className="min-w-0">
          <label htmlFor="plan-entry" className="block text-sm font-medium text-gray-700">Planned Entry Price</label>
          <input id="plan-entry" type="number" className="mt-1 block w-full min-w-0 rounded border-gray-300 px-3 py-2 border" value={form.planned_entry_price} onChange={e => setForm({...form, planned_entry_price: e.target.value})} />
        </div>
        <div className="min-w-0">
          <label htmlFor="plan-stop" className="block text-sm font-medium text-gray-700">Planned Stop Loss</label>
          <input id="plan-stop" type="number" className="mt-1 block w-full min-w-0 rounded border-gray-300 px-3 py-2 border" value={form.planned_stop_price} onChange={e => setForm({...form, planned_stop_price: e.target.value})} />
        </div>
        <div className="min-w-0">
          <label htmlFor="plan-target" className="block text-sm font-medium text-gray-700">Planned Target</label>
          <input id="plan-target" type="number" className="mt-1 block w-full min-w-0 rounded border-gray-300 px-3 py-2 border" value={form.planned_target_price} onChange={e => setForm({...form, planned_target_price: e.target.value})} />
        </div>
        <div className="min-w-0">
          <label htmlFor="plan-risk" className="block text-sm font-medium text-gray-700">Max Risk Capital (for size hint)</label>
          <input id="plan-risk" type="number" className="mt-1 block w-full min-w-0 rounded border-gray-300 px-3 py-2 border bg-yellow-50" placeholder="e.g. 500" value={form.risk_amount} onChange={e => setForm({...form, risk_amount: e.target.value})} />
        </div>
        <div className="min-w-0 sm:col-span-2">
          <label htmlFor="plan-quantity" className="block text-sm font-medium text-gray-700">Quantity you intend to trade</label>
          <input id="plan-quantity" type="number" min="1" step="1" className="mt-1 block w-full min-w-0 rounded border-gray-300 px-3 py-2 border" placeholder="Leave blank unless you choose a size" value={form.quantity} onChange={e => setForm({...form, quantity: e.target.value})} />
        </div>
      </div>

      <button id="calc-position-size" onClick={handleCalc} className="bg-gray-200 text-gray-800 px-4 py-2 rounded text-sm font-medium hover:bg-gray-300 min-h-[44px]">
        Calculate Position Size (informational)
      </button>

      {positionResult && (
        <div className="bg-gray-50 p-4 border rounded mt-2">
          {positionResult.status === 'CALCULATED' ? (
            <div className="space-y-2">
              <p className="text-xs text-gray-700">Informational only — not copied into quantity.</p>
              <div className="flex flex-wrap gap-4 font-mono text-sm min-w-0">
                <div><span className="text-gray-500">Hint qty:</span> {positionResult.quantity}</div>
                <div><span className="text-gray-500">Risk/Share:</span> {positionResult.per_share_risk}</div>
                <div><span className="text-gray-500">Total Cap:</span> {positionResult.total_capital}</div>
              </div>
            </div>
          ) : (
            <div className="text-red-600 text-sm">Error: {positionResult.reason}</div>
          )}
        </div>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-700">Trade Notes</label>
        <textarea className="mt-1 block w-full rounded border-gray-300 px-3 py-2 border" rows={3} value={form.trade_notes} onChange={e => setForm({...form, trade_notes: e.target.value})}></textarea>
      </div>

      {error && (
        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3 break-words">{error}</p>
      )}

      <div className="pt-4 flex flex-wrap gap-2">
        <button id="save-planned-trade" disabled={submitting || !hasEval} onClick={handleSave} className="bg-blue-600 text-white px-4 py-2 rounded font-medium hover:bg-blue-700 disabled:opacity-50 min-h-[44px]">
          {submitting ? 'Saving…' : 'Save Planned Trade'}
        </button>
        <button onClick={() => (hasInAppHistory() ? navigate(-1) : navigate(evidenceFallback))} className="text-gray-600 px-4 py-2 min-h-[44px]">Cancel</button>
      </div>
    </div>
  );
}
