import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import CandidateEvidence from './CandidateEvidence';
import TradePlanForm from './TradePlanForm';
import { evidenceApi } from '../api';

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    evidenceApi: { ...actual.evidenceApi, getStockEvidence: vi.fn() },
    tradesApi: { ...actual.tradesApi, createTrade: vi.fn(), calculatePositionSize: vi.fn() },
  };
});

afterEach(cleanup);

function evidence(classification: string) {
  return {
    stock: { nse_symbol: 'TCS', company_name: 'Tata Consultancy Services Limited' },
    candidate: {
      evaluation_id: 70,
      classification,
      decisive_reason: 'Mandatory evidence unavailable: SMA20_known',
      evaluation_date: '2026-09-22T20:00:31',
    },
    criteria: [],
    technical: { sessions: 18, indicators: {}, latest_close: '2105.0', latest_trading_date: '2026-09-22T00:00:00' },
    fundamentals: [],
    risk_reward: null,
    consensus: { status: 'NO_CONSENSUS' },
  };
}

const CAUTION = /INSUFFICIENT_DATA caution/;

describe('INSUFFICIENT_DATA caution', () => {
  it('evidence page keeps Plan Trade and shows the caution', async () => {
    vi.mocked(evidenceApi.getStockEvidence).mockResolvedValue(evidence('INSUFFICIENT_DATA'));
    render(
      <MemoryRouter initialEntries={['/evidence/3']}>
        <Routes><Route path="/evidence/:stockId" element={<CandidateEvidence />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(CAUTION)).toBeDefined();
    expect(screen.getByRole('link', { name: 'Plan Trade' })).toBeDefined();
  });

  it('evidence page shows no caution for other classifications', async () => {
    vi.mocked(evidenceApi.getStockEvidence).mockResolvedValue(evidence('FINAL_CANDIDATE'));
    render(
      <MemoryRouter initialEntries={['/evidence/3']}>
        <Routes><Route path="/evidence/:stockId" element={<CandidateEvidence />} /></Routes>
      </MemoryRouter>,
    );
    await screen.findByText(/Candidate Detail/);
    expect(screen.queryByText(CAUTION)).toBeNull();
  });

  it('plan form shows the caution, keeps saving enabled, and does not prefill quantity', async () => {
    vi.mocked(evidenceApi.getStockEvidence).mockResolvedValue(evidence('INSUFFICIENT_DATA'));
    const { container } = render(
      <MemoryRouter initialEntries={['/trades/plan/3']}>
        <Routes><Route path="/trades/plan/:stockId" element={<TradePlanForm />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(CAUTION)).toBeDefined();
    expect((container.querySelector('#save-planned-trade') as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText(/never applied as your trade size/i)).toBeDefined();
    expect(screen.queryByText(/guaranteed BUY recommendation/i)).toBeNull();
  });
});
