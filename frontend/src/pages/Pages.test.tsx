import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Home from './Home';
import DataHub from './DataHub';
import MasterData from './MasterData';
import RecommendationEntry from './RecommendationEntry';
import CandidateDashboard from './CandidateDashboard';
import FinalCandidates from './FinalCandidates';
import MarketDataStatus from './MarketDataStatus';
import CandidateEvidence from './CandidateEvidence';
import FundamentalImport from './FundamentalImport';
import TradeJournal from './TradeJournal';
import { OpenTradeModal, CloseTradeModal, CancelTradeModal } from './TradeLifecycleModals';
import { tradesApi, stocksApi } from '../api';

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    tradesApi: {
      getTrades: vi.fn().mockResolvedValue([]),
      updateTrade: vi.fn().mockResolvedValue({}),
      createTrade: vi.fn(),
      getTrade: vi.fn(),
      calculatePositionSize: vi.fn(),
    },
    stocksApi: {
      getStocks: vi.fn().mockResolvedValue([]),
    },
  };
});

afterEach(cleanup);

// ─── Existing page tests ───────────────────────────────────────────────────

describe('Frontend Pages', () => {
  it('Master Data renders brokers and stocks', () => {
    render(<MemoryRouter><MasterData /></MemoryRouter>);
    expect(screen.getByText('Master Data')).toBeDefined();
    expect(screen.getByText(/Brokers/)).toBeDefined();
    expect(screen.getByText(/Stocks/)).toBeDefined();
  });

  it('Recommendation Entry renders fields', () => {
    render(<MemoryRouter><RecommendationEntry /></MemoryRouter>);
    expect(screen.getByText('New Recommendation')).toBeDefined();
    expect(screen.getByText('Stock')).toBeDefined();
    expect(screen.getByText('Broker')).toBeDefined();
    expect(screen.getByText('Rating')).toBeDefined();
  });

  it('Required field validation for recommendation entry', async () => {
    render(<MemoryRouter><RecommendationEntry /></MemoryRouter>);
    
    const saveButton = screen.getByRole('button', { name: /Save Recommendation/i });
    fireEvent.click(saveButton);
    
    // Should show error for required fields
    const error = await screen.findByText('Please fill all required fields');
    expect(error).toBeDefined();
  });

  it('Candidate Dashboard renders universe header and filters button', async () => {
    render(<MemoryRouter><CandidateDashboard /></MemoryRouter>);
    expect(screen.getByText('Broker Opinion Universe')).toBeDefined();
    expect(screen.getByText(/Filters & Sort/i)).toBeDefined();
  });

  it('Home dashboard header renders', () => {
    render(<MemoryRouter><Home /></MemoryRouter>);
    expect(screen.getByText('Home')).toBeDefined();
    expect(screen.getByText(/does not decide BUY or SELL/i)).toBeDefined();
  });

  it('Data hub groups maintenance screens', () => {
    render(<MemoryRouter><DataHub /></MemoryRouter>);
    expect(screen.getByText('Data')).toBeDefined();
    expect(screen.getByText('Market Data')).toBeDefined();
    expect(screen.getByText('Fundamentals')).toBeDefined();
    expect(screen.getByText('Broker Reports')).toBeDefined();
    expect(screen.getByText('Data Health')).toBeDefined();
  });

  it('Candidates empty state renders', () => {
    render(<MemoryRouter><FinalCandidates /></MemoryRouter>);
    expect(screen.getByText('Candidates')).toBeDefined();
    expect(screen.getByText('FINAL_CANDIDATE')).toBeDefined();
    expect(screen.getByText('WATCH')).toBeDefined();
    expect(screen.getByText('REJECTED')).toBeDefined();
    expect(screen.getByText('INSUFFICIENT_DATA')).toBeDefined();
    expect(screen.getByText(/Not a guaranteed BUY/i)).toBeDefined();
  });

  it('Market Data Status header renders', () => {
    render(<MemoryRouter><MarketDataStatus /></MemoryRouter>);
    expect(screen.getByText('Market Data Status')).toBeDefined();
    expect(screen.getByText('Manual fundamental import')).toBeDefined();
  });

  it('Fundamental Import page renders without inventing values', () => {
    render(<MemoryRouter><FundamentalImport /></MemoryRouter>);
    expect(screen.getByText('Fundamental Import')).toBeDefined();
    expect(screen.getByText(/never PASS/i)).toBeDefined();
  });

  it('Candidate evidence loading state renders', () => {
    render(<MemoryRouter initialEntries={['/evidence/1']}><CandidateEvidence /></MemoryRouter>);
    expect(screen.getByText(/Loading evidence/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /Back/ })).toBeDefined();
  });
});

// ─── Trade Journal page ────────────────────────────────────────────────────

describe('TradeJournal page', () => {
  it('renders loading state immediately', () => {
    render(<MemoryRouter><TradeJournal /></MemoryRouter>);
    expect(screen.getByText(/Loading trades/i)).toBeDefined();
  });

  it('renders Trade Journal heading', () => {
    render(<MemoryRouter><TradeJournal /></MemoryRouter>);
    expect(screen.getByText('Trade Journal')).toBeDefined();
  });

  it('renders New Plan link', () => {
    render(<MemoryRouter><TradeJournal /></MemoryRouter>);
    expect(screen.getByText('New Plan')).toBeDefined();
  });

  it('renders personal-use disclaimer', () => {
    render(<MemoryRouter><TradeJournal /></MemoryRouter>);
    expect(screen.getByText(/Personal execution journal only/i)).toBeDefined();
  });
});

describe('TradeJournal lifecycle actions by status', () => {
  const stock = { stock_id: 19, nse_symbol: 'CIPLA', company_name: 'Cipla Ltd.' };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(stocksApi.getStocks).mockResolvedValue([stock]);
    vi.mocked(tradesApi.getTrades).mockResolvedValue([]);
  });

  it('PLANNED shows Record Entry and Cancel Plan', async () => {
    vi.mocked(tradesApi.getTrades).mockResolvedValue([
      { trade_id: 11, stock_id: 19, status: 'PLANNED', planned_entry_price: '100', quantity: 10 },
    ]);
    render(<MemoryRouter><TradeJournal /></MemoryRouter>);
    expect(await screen.findByRole('button', { name: 'Record Entry' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Cancel Plan' })).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Record Exit' })).toBeNull();
  });

  it('OPEN shows Record Exit and not Cancel Plan', async () => {
    vi.mocked(tradesApi.getTrades).mockResolvedValue([
      { trade_id: 12, stock_id: 19, status: 'OPEN', entry_price: '100.5', entry_price_source: 'Manual observation', quantity: 10 },
    ]);
    render(<MemoryRouter><TradeJournal /></MemoryRouter>);
    expect(await screen.findByRole('button', { name: 'Record Exit' })).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Record Entry' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cancel Plan' })).toBeNull();
  });

  it('CLOSED has no invalid lifecycle action', async () => {
    vi.mocked(tradesApi.getTrades).mockResolvedValue([
      { trade_id: 13, stock_id: 19, status: 'CLOSED', gross_pnl: '100', entry_price_source: 'Manual observation', exit_price_source: 'Broker app' },
    ]);
    render(<MemoryRouter><TradeJournal /></MemoryRouter>);
    expect(await screen.findByTestId('closed-review')).toBeDefined();
    expect(screen.getByTestId('terminal-label')).toBeDefined();
    expect(screen.getByText(/Closed — no further actions/)).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Record Entry' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Record Exit' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cancel Plan' })).toBeNull();
    expect(screen.getByTestId('entry-price-source').textContent).toBe('Manual observation');
    expect(screen.getByTestId('exit-price-source').textContent).toBe('Broker app');
  });

  it('CANCELLED has no invalid lifecycle action', async () => {
    vi.mocked(tradesApi.getTrades).mockResolvedValue([
      { trade_id: 14, stock_id: 19, status: 'CANCELLED' },
    ]);
    render(<MemoryRouter><TradeJournal /></MemoryRouter>);
    expect(await screen.findByText(/Cancelled — no further actions/)).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Record Entry' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Record Exit' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Cancel Plan' })).toBeNull();
  });
});

// ─── OpenTradeModal ────────────────────────────────────────────────────────

describe('OpenTradeModal', () => {
  const mockTrade = {
    trade_id: 1,
    stock_id: 1,
    status: 'PLANNED',
    planned_entry_price: '100.00',
    planned_stop_price: '90.00',
    planned_target_price: '120.00',
    quantity: 50,
  };
  const mockStock = { nse_symbol: 'TESTCO', company_name: 'Test Company' };
  const onClose = vi.fn();
  const onSuccess = vi.fn();

  beforeEach(() => {
    onClose.mockClear();
    onSuccess.mockClear();
    vi.mocked(tradesApi.updateTrade).mockClear();
  });

  it('renders Record Entry heading', () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: 'Record Entry' })).toBeDefined();
  });

  it('renders stock name in header', () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/TESTCO/)).toBeDefined();
  });

  it('renders all required fields', () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText(/Price you saw in the broker app/i)).toBeDefined();
    expect(screen.getByLabelText(/Entry Date/i)).toBeDefined();
    expect(screen.getByLabelText(/Price Source/i)).toBeDefined();
    expect(screen.getByLabelText(/Quantity/i)).toBeDefined();
  });

  it('does not prefill quantity from planned size', () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect((screen.getByLabelText(/^Quantity/i) as HTMLInputElement).value).toBe('');
    expect(screen.getByText(/Planned qty \(not auto-applied\): 50/)).toBeDefined();
  });

  it('shows planned reference section with broker-app wording', () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Planned reference/i)).toBeDefined();
    expect(screen.getAllByText(/price you saw in the broker app/i).length).toBeGreaterThan(0);
  });

  it('shows validation error when entry price is missing', async () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Record Entry/i }));
    const err = await screen.findByText(/Actual entry price is required/i);
    expect(err).toBeDefined();
  });

  it('calls onClose when Cancel is clicked', () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('OPEN payload matches backend contract', async () => {
    vi.mocked(tradesApi.updateTrade).mockResolvedValue({ status: 'OPEN' });
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/Price you saw in the broker app/i), { target: { value: '101.25' } });
    fireEvent.change(screen.getByLabelText(/Entry Date/i), { target: { value: '2026-08-20T10:30' } });
    fireEvent.change(screen.getByLabelText(/Price Source/i), { target: { value: 'Manual observation' } });
    fireEvent.change(screen.getByLabelText(/Quantity/i), { target: { value: '50' } });
    fireEvent.click(document.querySelector('#open-trade-submit')!);
    await vi.waitFor(() => expect(tradesApi.updateTrade).toHaveBeenCalled());
    expect(vi.mocked(tradesApi.updateTrade).mock.calls[0][0]).toBe(1);
    expect(vi.mocked(tradesApi.updateTrade).mock.calls[0][1]).toEqual({
      status: 'OPEN',
      entry_price: 101.25,
      entry_date: '2026-08-20T10:30:00',
      entry_price_source: 'Manual observation',
      quantity: 50,
    });
  });

  it('requires entry date before submit', async () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/Price you saw in the broker app/i), { target: { value: '101.25' } });
    fireEvent.change(screen.getByLabelText(/Price Source/i), { target: { value: 'Manual observation' } });
    fireEvent.click(document.querySelector('#open-trade-submit')!);
    expect(await screen.findByText(/Entry date and time are required/i)).toBeDefined();
    expect(tradesApi.updateTrade).not.toHaveBeenCalled();
  });

  it('requires entry price source before submit', async () => {
    render(
      <MemoryRouter>
        <OpenTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/Price you saw in the broker app/i), { target: { value: '101.25' } });
    fireEvent.change(screen.getByLabelText(/Entry Date/i), { target: { value: '2026-08-20T10:30' } });
    fireEvent.click(document.querySelector('#open-trade-submit')!);
    expect(await screen.findByText(/Price source is required/i)).toBeDefined();
    expect(tradesApi.updateTrade).not.toHaveBeenCalled();
  });
});

// ─── CloseTradeModal ───────────────────────────────────────────────────────

describe('CloseTradeModal', () => {
  const mockTrade = {
    trade_id: 2,
    stock_id: 1,
    status: 'OPEN',
    entry_price: '100.50',
    entry_date: '2026-08-19T10:00:00',
    entry_price_source: 'Manual observation',
    quantity: 50,
    planned_stop_price: '90.00',
    planned_target_price: '120.00',
  };
  const mockStock = { nse_symbol: 'TESTCO', company_name: 'Test Company' };
  const onClose = vi.fn();
  const onSuccess = vi.fn();

  beforeEach(() => {
    onClose.mockClear();
    onSuccess.mockClear();
    vi.mocked(tradesApi.updateTrade).mockClear();
  });

  it('renders Close Trade heading', () => {
    render(
      <MemoryRouter>
        <CloseTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { name: 'Record Exit' })).toBeDefined();
  });

  it('renders all required fields', () => {
    render(
      <MemoryRouter>
        <CloseTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByLabelText(/Price you saw in the broker app/i)).toBeDefined();
    expect(screen.getByLabelText(/Exit Date/i)).toBeDefined();
    expect(screen.getByLabelText(/Price Source/i)).toBeDefined();
  });

  it('shows open position reference', () => {
    render(
      <MemoryRouter>
        <CloseTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Open position reference/i)).toBeDefined();
  });

  it('shows PnL-by-system warning', () => {
    render(
      <MemoryRouter>
        <CloseTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/calculated by the system/i)).toBeDefined();
  });

  it('shows validation error when exit price is missing', async () => {
    render(
      <MemoryRouter>
        <CloseTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.click(document.querySelector('#close-trade-submit')!);
    const err = await screen.findByText(/Actual exit price is required/i);
    expect(err).toBeDefined();
  });

  it('CLOSE payload matches backend contract', async () => {
    vi.mocked(tradesApi.updateTrade).mockResolvedValue({ status: 'CLOSED', gross_pnl: '1000' });
    render(
      <MemoryRouter>
        <CloseTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/Price you saw in the broker app/i), { target: { value: '120.5' } });
    fireEvent.change(screen.getByLabelText(/Exit Date/i), { target: { value: '2026-08-21T15:00' } });
    fireEvent.change(screen.getByLabelText(/Price Source/i), { target: { value: 'Broker app' } });
    fireEvent.click(document.querySelector('#close-trade-submit')!);
    await vi.waitFor(() => expect(tradesApi.updateTrade).toHaveBeenCalled());
    expect(vi.mocked(tradesApi.updateTrade).mock.calls[0][1]).toEqual({
      status: 'CLOSED',
      exit_price: 120.5,
      exit_date: '2026-08-21T15:00:00',
      exit_price_source: 'Broker app',
    });
  });

  it('requires exit date and source before submit', async () => {
    render(
      <MemoryRouter>
        <CloseTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/Price you saw in the broker app/i), { target: { value: '120.5' } });
    fireEvent.click(document.querySelector('#close-trade-submit')!);
    expect(await screen.findByText(/Exit date and time are required/i)).toBeDefined();
    fireEvent.change(screen.getByLabelText(/Exit Date/i), { target: { value: '2026-08-21T15:00' } });
    fireEvent.click(document.querySelector('#close-trade-submit')!);
    expect(await screen.findByText(/Price source is required/i)).toBeDefined();
    expect(tradesApi.updateTrade).not.toHaveBeenCalled();
  });
});

// ─── CancelTradeModal ──────────────────────────────────────────────────────

describe('CancelTradeModal', () => {
  const mockTrade = { trade_id: 3, stock_id: 1, status: 'PLANNED' };
  const mockStock = { nse_symbol: 'TESTCO' };
  const onClose = vi.fn();
  const onSuccess = vi.fn();

  beforeEach(() => {
    onClose.mockClear();
    onSuccess.mockClear();
    vi.mocked(tradesApi.updateTrade).mockClear();
  });

  it('renders Cancel Plan heading', () => {
    render(
      <MemoryRouter>
        <CancelTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByText('Cancel Plan')).toBeDefined();
  });

  it('shows stock symbol in confirmation message', () => {
    render(
      <MemoryRouter>
        <CancelTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/TESTCO/)).toBeDefined();
  });

  it('renders Confirm button and Keep Plan button', () => {
    render(
      <MemoryRouter>
        <CancelTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: /Confirm.*Cancel Plan/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Keep Plan/i })).toBeDefined();
  });

  it('calls onClose when Keep Plan is clicked', () => {
    render(
      <MemoryRouter>
        <CancelTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Keep Plan/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('mentions record is preserved (no delete)', () => {
    render(
      <MemoryRouter>
        <CancelTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/preserved/i)).toBeDefined();
  });

  it('CANCEL payload matches backend contract', async () => {
    vi.mocked(tradesApi.updateTrade).mockResolvedValue({ status: 'CANCELLED' });
    render(
      <MemoryRouter>
        <CancelTradeModal trade={mockTrade} stock={mockStock} onClose={onClose} onSuccess={onSuccess} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Confirm.*Cancel Plan/i }));
    await vi.waitFor(() => expect(tradesApi.updateTrade).toHaveBeenCalled());
    expect(vi.mocked(tradesApi.updateTrade).mock.calls[0]).toEqual([3, { status: 'CANCELLED' }]);
  });
});

describe('toBackendDatetime', () => {
  it('adds seconds to datetime-local values', async () => {
    const { toBackendDatetime, formatApiError } = await import('./TradeLifecycleModals');
    expect(toBackendDatetime('2026-08-20T10:30')).toBe('2026-08-20T10:30:00');
    expect(toBackendDatetime('2026-08-20T10:30:00')).toBe('2026-08-20T10:30:00');
    expect(toBackendDatetime('')).toBe('');
    expect(formatApiError({}, 'fallback')).toBe('Network error. Check that the backend is running.');
    expect(formatApiError({ response: { data: { detail: 'OPEN trades require entry_price_source' } } }, 'fallback'))
      .toBe('OPEN trades require entry_price_source');
  });
});
