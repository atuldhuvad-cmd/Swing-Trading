import { expect, test, type Page, type Request, type Response } from '@playwright/test';

const PHASE5_FP = '146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe';
const INSURANCE_LINE = "Total Income (Policyholders' Account)";
const BATCH_B: Record<string, string> = {
  CIPLA: 'FINAL_CANDIDATE',
  COALINDIA: 'REJECTED',
  DRREDDY: 'REJECTED',
  EICHERMOT: 'FINAL_CANDIDATE',
  ETERNAL: 'FINAL_CANDIDATE',
  GRASIM: 'FINAL_CANDIDATE',
  HCLTECH: 'WATCH',
  HDFCBANK: 'REJECTED',
  HDFCLIFE: 'REJECTED',
  HINDALCO: 'FINAL_CANDIDATE',
};
const RR_PREFIX: Record<string, string> = {
  CIPLA: '0.4639',
  COALINDIA: '2.0070',
  DRREDDY: '0.4162',
  GRASIM: '0.9558',
  HDFCBANK: '5.3229',
  HDFCLIFE: '2.8142',
  HINDALCO: '0.8121',
};
const RR_NA = ['EICHERMOT', 'ETERNAL', 'HCLTECH'];
const viewports = [
  { label: '320px', width: 320, height: 800 },
  { label: '375px', width: 375, height: 812 },
  { label: '390px', width: 390, height: 844 },
  { label: '768px', width: 768, height: 1024 },
  { label: '1024px', width: 1024, height: 768 },
];

function attachAudit(page: Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  const httpErrors: { url: string; status: number }[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => pageErrors.push(String(err)));
  page.on('requestfailed', (req: Request) => {
    failedRequests.push(`${req.method()} ${req.url()} ${req.failure()?.errorText || ''}`);
  });
  page.on('response', (res: Response) => {
    if (res.status() >= 400) httpErrors.push({ url: res.url(), status: res.status() });
  });
  return {
    snapshot: () => ({
      consoleErrors: [...consoleErrors],
      pageErrors: [...pageErrors],
      failedRequests: [...failedRequests],
      httpErrors: [...httpErrors],
    }),
  };
}

async function noPageOverflow(page: Page, label: string) {
  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(overflow.documentWidth, `${label} overflow`).toBeLessThanOrEqual(overflow.viewport);
}

test.describe('Phase 5 Batch B evidence UI', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('API latest evaluations match Batch B production classifications', async ({ request }) => {
    const listed = await request.get('/api/evidence/candidates');
    expect(listed.ok()).toBeTruthy();
    const items = (await listed.json()).items || [];
    const bySym = Object.fromEntries(items.map((row: { nse_symbol: string }) => [row.nse_symbol, row]));
    const batchCounts: Record<string, number> = {};
    for (const [symbol, status] of Object.entries(BATCH_B)) {
      const row = bySym[symbol];
      expect(row, symbol).toBeTruthy();
      expect(row.status).toBe(status);
      expect(row.config_fingerprint).toBe(PHASE5_FP);
      expect(row.evaluation_id).toBeGreaterThanOrEqual(34);
      batchCounts[row.status] = (batchCounts[row.status] || 0) + 1;
      const detail = await (await request.get(`/api/evidence/stocks/${row.stock_id}`)).json();
      expect(detail.candidate?.evaluation_id).toBe(row.evaluation_id);
      expect(detail.candidate?.classification).toBe(status);
      expect(detail.candidate?.decisive_reason).toBeTruthy();
      expect(detail.close_gt_sma50).toBeTruthy();
      expect(detail.sma50_gt_sma200).toBeTruthy();
      const revenue = (detail.fundamentals || []).find((m: { metric_name: string }) => m.metric_name === 'revenue');
      expect(revenue?.status).toBe('KNOWN');
      if (symbol in RR_PREFIX) {
        expect(row.rr_available).toBeTruthy();
        expect(String(detail.risk_reward?.rr_ratio || '')).toContain(RR_PREFIX[symbol].slice(0, 6));
      }
      if (RR_NA.includes(symbol)) {
        expect(row.rr_available).toBeFalsy();
        expect(detail.risk_reward?.rr_ratio == null).toBeTruthy();
      }
    }
    expect(batchCounts.FINAL_CANDIDATE).toBe(5);
    expect(batchCounts.WATCH).toBe(1);
    expect(batchCounts.REJECTED).toBe(4);
    expect(batchCounts.INSUFFICIENT_DATA || 0).toBe(0);

    const missing = await request.get('/api/evidence/stocks/999999');
    expect(missing.status()).toBe(404);
  });

  test('Final Candidates shows Batch B statuses, disclaimer, and does not hide WATCH/REJECTED', async ({ page, request }) => {
    const items = ((await (await request.get('/api/evidence/candidates')).json()).items || []) as Array<{
      nse_symbol: string;
      status: string;
      rr_available?: boolean;
      rr_ratio?: string | null;
      decisive_reason?: string | null;
    }>;
    const bySym = Object.fromEntries(items.map((row) => [row.nse_symbol, row]));

    await page.goto('/final-candidates', { waitUntil: 'load' });
    await expect(page.getByRole('heading', { name: 'Candidates' })).toBeVisible();
    await expect(page.getByText('Not a guaranteed BUY', { exact: false })).toBeVisible();
    await expect(page.getByText('Not a trading recommendation', { exact: false })).toBeVisible();
    await expect(page.getByText('No guaranteed profitability', { exact: false })).toBeVisible();
    await expect(page.getByText('RR is evidence only and does not change classification', { exact: false })).toBeVisible();
    await expect(page.getByText('WATCH').first()).toBeVisible();
    await expect(page.getByText('REJECTED').first()).toBeVisible();
    await expect(page.getByText('FINAL_CANDIDATE').first()).toBeVisible();
    await expect(page.getByText('INSUFFICIENT_DATA').first()).toBeVisible();

    for (const symbol of Object.keys(BATCH_B)) {
      const card = page.getByRole('button', { name: new RegExp(symbol) });
      await expect(card).toBeVisible();
      await expect(card.getByText(BATCH_B[symbol], { exact: true })).toBeVisible();
      if (symbol in RR_PREFIX) {
        await expect(card).toContainText(RR_PREFIX[symbol].slice(0, 4));
      }
      if (RR_NA.includes(symbol)) {
        await expect(card.getByText('N/A').first()).toBeVisible();
        await expect(card).not.toContainText('0.6052');
      }
      if (bySym[symbol]?.decisive_reason) {
        await expect(card.getByText(bySym[symbol].decisive_reason as string, { exact: false })).toBeVisible();
      }
    }
    await expect(page.locator('main')).not.toContainText('guaranteed BUY recommendation');
  });

  test('Evidence detail for all Batch B stocks, including HDFCLIFE insurance provenance', async ({ page, request }) => {
    const items = ((await (await request.get('/api/evidence/candidates')).json()).items || []) as Array<{
      nse_symbol: string;
      stock_id: number;
      status: string;
    }>;
    const bySym = Object.fromEntries(items.map((row) => [row.nse_symbol, row]));

    for (const symbol of Object.keys(BATCH_B)) {
      const row = bySym[symbol];
      const detail = await (await request.get(`/api/evidence/stocks/${row.stock_id}`)).json();
      await page.goto(`/evidence/${row.stock_id}`, { waitUntil: 'load' });
      await expect(page.getByText('Candidate Detail / Evidence')).toBeVisible();
      await expect(page.getByText(symbol).first()).toBeVisible();
      await expect(page.getByText(BATCH_B[symbol], { exact: true }).first()).toBeVisible();
      await expect(page.getByText('Not a guaranteed BUY', { exact: false })).toBeVisible();
      await expect(page.getByText('close > SMA50').first()).toBeVisible();
      await expect(page.getByText('SMA50 > SMA200').first()).toBeVisible();
      await expect(page.getByText(detail.candidate.decisive_reason, { exact: false }).first()).toBeVisible();
      for (const metric of ['SMA50', 'SMA200']) {
        const value = detail.technical.indicators[metric];
        expect(value).not.toBeNull();
        await expect(page.getByText(String(value), { exact: false }).first()).toBeVisible();
      }
      if (symbol in RR_PREFIX) {
        await expect(page.getByText(RR_PREFIX[symbol], { exact: false }).first()).toBeVisible();
      }
      if (RR_NA.includes(symbol)) {
        await expect(page.getByText('RR N/A', { exact: false })).toBeVisible();
        await expect(page.getByText('0.6052')).toHaveCount(0);
      }
    }

    const hdfc = bySym.HDFCLIFE;
    const hdfcDetail = await (await request.get(`/api/evidence/stocks/${hdfc.stock_id}`)).json();
    expect(hdfcDetail.fundamental_entity_type).toBe('INSURANCE');
    expect(hdfcDetail.fundamental_provenance?.source_line_item).toBe(INSURANCE_LINE);
    const revenue = (hdfcDetail.fundamentals || []).find((m: { metric_name: string }) => m.metric_name === 'revenue');
    expect(String(revenue?.metric_value || '')).toContain('98770.38');
    expect(revenue?.status).toBe('KNOWN');

    await page.goto(`/evidence/${hdfc.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('Candidate Detail / Evidence')).toBeVisible();
    await expect(page.getByText(INSURANCE_LINE, { exact: false })).toBeVisible();
    const mainText = await page.locator('main').innerText();
    expect(mainText).toContain(INSURANCE_LINE);
    expect(mainText).toContain('98770.38');
    expect(mainText).toContain('KNOWN');
    expect(mainText).not.toContain('Revenue from Operations');
    expect(mainText.replace(INSURANCE_LINE, '')).not.toMatch(/\bTotal Income\b/);
  });

  test('Market data preserves Batch B history and matches current API coverage', async ({ page, request }) => {
    const market = ((await (await request.get('/api/evidence/market-data')).json()).items || []) as Array<{
      nse_symbol: string;
      session_count: number;
      sma200_ready: boolean;
      latest_trading_date?: string | null;
    }>;
    for (const symbol of Object.keys(BATCH_B)) {
      const row = market.find((item) => item.nse_symbol === symbol);
      expect(row?.session_count).toBeGreaterThanOrEqual(247);
      expect(row?.sma200_ready).toBeTruthy();
      expect(String(row?.latest_trading_date || '').slice(0, 10) >= '2026-08-13').toBe(true);
    }
    const bharti = market.find((item) => item.nse_symbol === 'BHARTIARTL');
    expect(bharti?.session_count).toBeGreaterThanOrEqual(246);
    expect(String(bharti?.latest_trading_date || '').slice(0, 10) >= '2026-08-12').toBe(true);

    await page.goto('/market-data', { waitUntil: 'load' });
    await expect(page.getByText('Market Data Status')).toBeVisible();
    for (const symbol of Object.keys(BATCH_B)) {
      await expect(page.getByText(symbol, { exact: true }).first()).toBeVisible();
      const current = market.find((item) => item.nse_symbol === symbol)!;
      const card = page.getByText(symbol, { exact: true }).locator('..');
      await expect(card.getByText('Session count', { exact: true }).locator('..')).toHaveText(`Session count${current.session_count}`);
      await expect(card.getByText('Latest trading date', { exact: true }).locator('..')).toHaveText(`Latest trading date${String(current.latest_trading_date).slice(0, 10)}`);
    }
    await expect(page.getByText('ADANIENT')).toBeVisible();
    await expect(page.getByText('YES').first()).toBeVisible();
  });
});

test.describe('Phase 5 Batch B responsive and console audit', () => {
  for (const viewport of viewports) {
    test.describe(viewport.label, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height } });

      for (const route of [
        { name: 'Final Candidates', path: '/final-candidates' },
        { name: 'Market Data', path: '/market-data' },
        { name: 'HDFCLIFE evidence', path: '/evidence/27' },
        { name: 'CIPLA evidence', path: '/evidence/19' },
        { name: 'HCLTECH evidence', path: '/evidence/25' },
      ]) {
        test(`${route.name}`, async ({ page }) => {
          const audit = attachAudit(page);
          await page.goto(route.path, { waitUntil: 'load' });
          await page.waitForTimeout(800);
          const snap = audit.snapshot();
          expect(snap.consoleErrors, `${route.name} console.error`).toEqual([]);
          expect(snap.pageErrors, `${route.name} uncaught`).toEqual([]);
          expect(snap.failedRequests, `${route.name} failed requests`).toEqual([]);
          expect(snap.httpErrors, `${route.name} unexpected HTTP`).toEqual([]);
          await noPageOverflow(page, route.name);
          await expect(page.locator('nav a')).toHaveCount(4);
        });
      }
    });
  }
});
