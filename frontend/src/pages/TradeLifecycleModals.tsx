import { useRef, useState } from 'react';
import { X } from 'lucide-react';
import { tradesApi } from '../api';

// ─── Shared types ──────────────────────────────────────────────────────────

interface Trade {
  trade_id: number;
  stock_id: number;
  status: string;
  quantity?: number | null;
  planned_entry_price?: number | string | null;
  planned_stop_price?: number | string | null;
  planned_target_price?: number | string | null;
  entry_price?: number | string | null;
  entry_date?: string | null;
  entry_price_source?: string | null;
  entry_note?: string | null;
  exit_price?: number | string | null;
  exit_date?: string | null;
  exit_price_source?: string | null;
  exit_note?: string | null;
  trade_notes?: string | null;
}

interface Stock {
  nse_symbol?: string;
  company_name?: string;
}

// ─── Shared helpers ────────────────────────────────────────────────────────

function fmtRef(v: number | string | null | undefined): string | null {
  if (v == null || v === '') return null;
  return `₹${Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDateRef(v: string | null | undefined): string | null {
  if (!v) return null;
  return v.slice(0, 16).replace('T', ' ');
}

/** datetime-local yields YYYY-MM-DDTHH:MM; backend expects a parseable datetime. */
export function toBackendDatetime(localValue: string): string {
  const trimmed = localValue.trim();
  if (!trimmed) return trimmed;
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(trimmed)) return `${trimmed}:00`;
  return trimmed;
}

export function formatApiError(e: unknown, fallback: string): string {
  const err = e as { response?: { data?: { detail?: unknown } } };
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: { msg?: string }) => (typeof d?.msg === 'string' ? d.msg : ''))
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  if (!err?.response) return 'Network error. Check that the backend is running.';
  return fallback;
}

interface ModalBackdropProps {
  onClose: () => void;
  children: React.ReactNode;
}

function ModalBackdrop({ onClose, children }: ModalBackdropProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-3 sm:p-4"
      style={{ background: 'rgba(0,0,0,0.55)' }}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-md max-h-[92vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

interface RefRowProps {
  label: string;
  value?: string | number | null;
}

function RefRow({ label, value }: RefRowProps) {
  if (value == null || value === '') return null;
  return (
    <div className="flex justify-between gap-2 py-0.5">
      <span className="text-gray-500 shrink-0">{label}</span>
      <span className="font-medium text-gray-900 text-right break-words">{value}</span>
    </div>
  );
}

interface FieldProps {
  id: string;
  label: string;
  required?: boolean;
  children: React.ReactNode;
}

function Field({ id, label, required, children }: FieldProps) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}

const inputCls =
  'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent';

// ─── OpenTradeModal ────────────────────────────────────────────────────────

export interface OpenTradeModalProps {
  trade: Trade;
  stock: Stock | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function OpenTradeModal({ trade, stock, onClose, onSuccess }: OpenTradeModalProps) {
  const [form, setForm] = useState({
    entry_price: '',
    entry_date: '',
    entry_price_source: '',
    quantity: '',
    entry_note: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async () => {
    if (submittingRef.current) return;
    setError(null);
    if (!form.entry_price || Number(form.entry_price) <= 0) {
      setError('Actual entry price is required and must be greater than 0.');
      return;
    }
    if (!form.entry_date) {
      setError('Entry date and time are required.');
      return;
    }
    if (!form.entry_price_source.trim()) {
      setError('Price source is required — describe where you observed this price.');
      return;
    }
    if (!form.quantity || Number(form.quantity) <= 0) {
      setError('Quantity is required and must be at least 1.');
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    try {
      await tradesApi.updateTrade(trade.trade_id, {
        status: 'OPEN',
        entry_price: Number(form.entry_price),
        entry_date: toBackendDatetime(form.entry_date),
        entry_price_source: form.entry_price_source.trim(),
        quantity: Number(form.quantity),
        ...(form.entry_note.trim() ? { entry_note: form.entry_note.trim() } : {}),
      });
      onSuccess();
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to open trade. Please check all fields.'));
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <ModalBackdrop onClose={onClose}>
      <div className="p-5 space-y-4">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Record Entry</h2>
            {stock?.nse_symbol && (
              <p className="text-sm text-gray-600 mt-0.5">
                {stock.nse_symbol}{stock.company_name ? ` — ${stock.company_name}` : ''}
              </p>
            )}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 transition" aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>

        {/* Planned reference — read-only, for context */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs space-y-0.5">
          <p className="font-semibold text-amber-800 mb-1.5">Planned reference (context only)</p>
          <RefRow label="Planned entry" value={fmtRef(trade.planned_entry_price)} />
          <RefRow label="Planned stop" value={fmtRef(trade.planned_stop_price)} />
          <RefRow label="Planned target" value={fmtRef(trade.planned_target_price)} />
          <p className="text-amber-700 pt-1.5 border-t border-amber-200 mt-1.5">
            Enter the price you saw in the broker app. Do not copy planned values here.
          </p>
          {trade.quantity != null && (
            <p className="text-amber-700">Planned qty (not auto-applied): {trade.quantity}. Type the quantity you actually traded.</p>
          )}
        </div>

        {/* Form */}
        <div className="space-y-3">
          <Field id="open-entry-price" label="Price you saw in the broker app" required>
            <input
              id="open-entry-price"
              type="number"
              step="0.01"
              min="0.01"
              className={inputCls}
              placeholder="e.g. 1245.50"
              value={form.entry_price}
              onChange={set('entry_price')}
              autoFocus
            />
          </Field>

          <Field id="open-entry-date" label="Entry Date & Time" required>
            <input
              id="open-entry-date"
              type="datetime-local"
              className={inputCls}
              value={form.entry_date}
              onChange={set('entry_date')}
            />
          </Field>

          <Field id="open-price-source" label="Price Source" required>
            <input
              id="open-price-source"
              type="text"
              className={inputCls}
              placeholder="e.g. Broker app, NSE website, Manual observation"
              maxLength={100}
              value={form.entry_price_source}
              onChange={set('entry_price_source')}
            />
          </Field>

          <Field id="open-quantity" label="Quantity" required>
            <input
              id="open-quantity"
              type="number"
              min="1"
              step="1"
              className={inputCls}
              placeholder="Number of shares"
              value={form.quantity}
              onChange={set('quantity')}
            />
          </Field>

          <Field id="open-entry-note" label="Entry Note (optional)">
            <textarea
              id="open-entry-note"
              className={inputCls}
              rows={2}
              placeholder="Optional note about the execution"
              value={form.entry_note}
              onChange={set('entry_note')}
            />
          </Field>
        </div>

        {error && (
          <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">{error}</p>
        )}

        <div className="flex gap-2 pt-1">
          <button
            id="open-trade-submit"
            disabled={submitting}
            onClick={handleSubmit}
            className="flex-1 bg-green-600 text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-green-700 disabled:opacity-50 transition min-h-[44px]"
          >
            {submitting ? 'Saving…' : 'Record Entry'}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition min-h-[44px]"
          >
            Cancel
          </button>
        </div>
      </div>
    </ModalBackdrop>
  );
}

// ─── CloseTradeModal ───────────────────────────────────────────────────────

export interface CloseTradeModalProps {
  trade: Trade;
  stock: Stock | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function CloseTradeModal({ trade, stock, onClose, onSuccess }: CloseTradeModalProps) {
  const [form, setForm] = useState({
    exit_price: '',
    exit_date: '',
    exit_price_source: '',
    exit_note: '',
    lesson: '',
    manual_charges: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async () => {
    if (submittingRef.current) return;
    setError(null);
    if (!form.exit_price || Number(form.exit_price) <= 0) {
      setError('Actual exit price is required and must be greater than 0.');
      return;
    }
    if (!form.exit_date) {
      setError('Exit date and time are required.');
      return;
    }
    if (!form.exit_price_source.trim()) {
      setError('Price source is required — describe where you observed this price.');
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const payload: Record<string, unknown> = {
        status: 'CLOSED',
        exit_price: Number(form.exit_price),
        exit_date: toBackendDatetime(form.exit_date),
        exit_price_source: form.exit_price_source.trim(),
        ...(form.exit_note.trim() ? { exit_note: form.exit_note.trim() } : {}),
      };
      const lesson = form.lesson.trim();
      if (lesson) {
        payload.trade_notes = trade.trade_notes
          ? `${trade.trade_notes}\n\nWhat I learned: ${lesson}`
          : lesson;
      }
      if (form.manual_charges !== '' && Number(form.manual_charges) >= 0) {
        payload.manual_charges = Number(form.manual_charges);
      }
      await tradesApi.updateTrade(trade.trade_id, payload);
      onSuccess();
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to close trade. Please check all fields.'));
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <ModalBackdrop onClose={onClose}>
      <div className="p-5 space-y-4">
        {/* Header */}
        <div className="flex justify-between items-start">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Record Exit</h2>
            {stock?.nse_symbol && (
              <p className="text-sm text-gray-600 mt-0.5">
                {stock.nse_symbol}{stock.company_name ? ` — ${stock.company_name}` : ''}
              </p>
            )}
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 transition" aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>

        {/* Open position reference */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs space-y-0.5">
          <p className="font-semibold text-blue-800 mb-1.5">Open position reference</p>
          <RefRow label="Entry price" value={fmtRef(trade.entry_price)} />
          <RefRow label="Entry date" value={fmtDateRef(trade.entry_date)} />
          <RefRow label="Entry source" value={trade.entry_price_source} />
          <RefRow label="Quantity" value={trade.quantity} />
          <RefRow label="Planned stop" value={fmtRef(trade.planned_stop_price)} />
          <RefRow label="Planned target" value={fmtRef(trade.planned_target_price)} />
          <p className="text-blue-700 pt-1.5 border-t border-blue-200 mt-1.5">
            Enter the price you saw in the broker app.
            P&amp;L will be calculated by the system — do not compute it manually.
          </p>
        </div>

        {/* Form */}
        <div className="space-y-3">
          <Field id="close-exit-price" label="Price you saw in the broker app" required>
            <input
              id="close-exit-price"
              type="number"
              step="0.01"
              min="0.01"
              className={inputCls}
              placeholder="e.g. 1320.00"
              value={form.exit_price}
              onChange={set('exit_price')}
              autoFocus
            />
          </Field>

          <Field id="close-exit-date" label="Exit Date & Time" required>
            <input
              id="close-exit-date"
              type="datetime-local"
              className={inputCls}
              value={form.exit_date}
              onChange={set('exit_date')}
            />
          </Field>

          <Field id="close-price-source" label="Price Source" required>
            <input
              id="close-price-source"
              type="text"
              className={inputCls}
              placeholder="e.g. Broker app, NSE website, Manual observation"
              maxLength={100}
              value={form.exit_price_source}
              onChange={set('exit_price_source')}
            />
          </Field>

          <Field id="close-manual-charges" label="Manual Charges / Brokerage (optional)">
            <input
              id="close-manual-charges"
              type="number"
              step="0.01"
              min="0"
              className={inputCls}
              placeholder="e.g. 25.50 — leave blank if unknown"
              value={form.manual_charges}
              onChange={set('manual_charges')}
            />
          </Field>

          <Field id="close-exit-note" label="Why I exited (optional)">
            <textarea
              id="close-exit-note"
              className={inputCls}
              rows={2}
              placeholder="Optional — stored on this trade"
              value={form.exit_note}
              onChange={set('exit_note')}
            />
          </Field>

          <Field id="close-lesson" label="What I learned (optional)">
            <textarea
              id="close-lesson"
              className={inputCls}
              rows={2}
              placeholder="Optional — stored in trade notes"
              value={form.lesson}
              onChange={set('lesson')}
            />
          </Field>
        </div>

        {error && (
          <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">{error}</p>
        )}

        <div className="flex gap-2 pt-1">
          <button
            id="close-trade-submit"
            disabled={submitting}
            onClick={handleSubmit}
            className="flex-1 bg-gray-700 text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-gray-800 disabled:opacity-50 transition min-h-[44px]"
          >
            {submitting ? 'Saving…' : 'Record Exit'}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition min-h-[44px]"
          >
            Cancel
          </button>
        </div>
      </div>
    </ModalBackdrop>
  );
}

// ─── CancelTradeModal ──────────────────────────────────────────────────────

export interface CancelTradeModalProps {
  trade: Trade;
  stock: Stock | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function CancelTradeModal({ trade, stock, onClose, onSuccess }: CancelTradeModalProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submittingRef = useRef(false);

  const handleConfirm = async () => {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      await tradesApi.updateTrade(trade.trade_id, { status: 'CANCELLED' });
      onSuccess();
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to cancel plan. Please try again.'));
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <ModalBackdrop onClose={onClose}>
      <div className="p-5 space-y-4">
        {/* Header */}
        <div className="flex justify-between items-start">
          <h2 className="text-lg font-bold text-gray-900">Cancel Plan</h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 transition" aria-label="Close dialog">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-2 text-sm text-gray-700">
          <p>
            Cancel the planned trade for{' '}
            <strong>{stock?.nse_symbol ?? `trade #${trade.trade_id}`}</strong>?
          </p>
          <p className="text-gray-500 text-xs">
            The journal record will be preserved with status CANCELLED. This
            action cannot be undone. No trade is deleted.
          </p>
        </div>

        {error && (
          <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">{error}</p>
        )}

        <div className="flex gap-2 pt-1">
          <button
            id="cancel-trade-confirm"
            disabled={submitting}
            onClick={handleConfirm}
            className="flex-1 bg-red-600 text-white py-2.5 rounded-lg text-sm font-semibold hover:bg-red-700 disabled:opacity-50 transition min-h-[44px]"
          >
            {submitting ? 'Cancelling…' : 'Confirm — Cancel Plan'}
          </button>
          <button
            id="cancel-trade-keep"
            onClick={onClose}
            className="px-4 py-2.5 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition min-h-[44px]"
          >
            Keep Plan
          </button>
        </div>
      </div>
    </ModalBackdrop>
  );
}
