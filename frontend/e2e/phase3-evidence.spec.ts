import { expect, test } from '@playwright/test';

const PHASE5_FP = '146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe';

test.describe('Phase 5 production evidence UI', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('Candidate Evaluation matches latest Phase 5 API and shows all statuses', async ({ page, request }) => {
    const api = await request.get('/api/evidence/candidates');
    expect(api.ok()).toBeTruthy();
    const items = (await api.json()).items || [];
    const counts: Record<string, number> = {};
    for (const row of items) {
      counts[row.status] = (counts[row.status] || 0) + 1;
    }
    expect(items.every((row: { evaluation_id: number }) => row.evaluation_id >= 24)).toBeTruthy();
    expect(items.every((row: { config_fingerprint: string }) => row.config_fingerprint === PHASE5_FP)).toBeTruthy();
    expect(counts.FINAL_CANDIDATE || 0).toBe(8);
    expect(counts.WATCH || 0).toBe(4);
    expect(counts.REJECTED || 0).toBe(8);
    expect(counts.INSUFFICIENT_DATA || 0).toBe(0);
    expect(items.filter((row: { rr_available?: boolean }) => row.rr_available).length).toBe(16);
    expect(items.some((row: { rr_ratio?: string | null }) => row.rr_ratio === '0.6052')).toBeFalsy();

    const rejected = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'ADANIENT');
    const watch = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'BAJAJFINSV');
    const finalRow = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'ASIANPAINT');
    const bel = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'BEL');
    expect(rejected?.status).toBe('REJECTED');
    expect(watch?.status).toBe('WATCH');
    expect(finalRow?.status).toBe('FINAL_CANDIDATE');
    expect(bel?.rr_available).toBeFalsy();

    await page.goto('/final-candidates', { waitUntil: 'load' });
    await expect(page.getByRole('heading', { name: 'Candidates' })).toBeVisible();
    await expect(page.getByText('Not a guaranteed BUY', { exact: false })).toBeVisible();
    await expect(page.getByText('Not a trading recommendation', { exact: false })).toBeVisible();
    await expect(page.getByText('No guaranteed profitability', { exact: false })).toBeVisible();
    await expect(page.getByText('Passes current Phase 5 trend screen.', { exact: false }).first()).toBeVisible();
    await expect(page.getByText('Primary trend criterion passes, trend confirmation fails.', { exact: false }).first()).toBeVisible();
    await expect(page.getByText('Primary mandatory trend criterion fails.', { exact: false }).first()).toBeVisible();
    await expect(page.getByText('Mandatory evidence unavailable.', { exact: false }).first()).toBeVisible();
    await expect(page.getByText('ADANIENT')).toBeVisible();
    await expect(page.getByText('REJECTED').first()).toBeVisible();
    await expect(page.getByText('WATCH').first()).toBeVisible();
    await expect(page.getByText('FINAL_CANDIDATE').first()).toBeVisible();
    await expect(page.getByText('INSUFFICIENT_DATA').first()).toBeVisible();
    await expect(page.getByRole('button', { name: /ADANIENT/ }).getByText(rejected.decisive_reason, { exact: false })).toBeVisible();
    await expect(page.getByRole('button', { name: /BAJAJFINSV/ }).getByText(watch.decisive_reason, { exact: false })).toBeVisible();
    await expect(page.getByText('close > SMA50').first()).toBeVisible();
    await expect(page.getByText('SMA50 > SMA200').first()).toBeVisible();
  });

  test('Candidate detail shows latest close, revenue, criteria, and RR evidence', async ({ page, request }) => {
    const listed = await request.get('/api/evidence/candidates');
    const items = (await listed.json()).items || [];
    const adanient = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'ADANIENT');
    const asian = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'ASIANPAINT');
    const bajajfinsv = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'BAJAJFINSV');
    const bel = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'BEL');
    expect(adanient && asian && bajajfinsv && bel).toBeTruthy();

    const body = await (await request.get(`/api/evidence/stocks/${adanient.stock_id}`)).json();
    expect(body.candidate?.evaluation_id).toBe(adanient.evaluation_id);
    expect(body.candidate?.classification).toBe('REJECTED');
    const revenue = (body.fundamentals || []).find((m: { metric_name: string }) => m.metric_name === 'revenue');
    expect(revenue?.status).toBe('KNOWN');

    await page.goto(`/evidence/${adanient.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('Candidate Detail / Evidence')).toBeVisible();
    await expect(page.getByText('ADANIENT')).toBeVisible();
    await expect(page.getByText('REJECTED').first()).toBeVisible();
    await expect(page.getByText('Last stored close').first()).toBeVisible();
    await expect(page.getByText(String(body.technical.latest_close), { exact: false }).first()).toBeVisible();
    await expect(page.getByText('Revenue (Latest)', { exact: false })).toBeVisible();
    await expect(page.getByText(`${revenue.metric_value} (KNOWN)`, { exact: false }).first()).toBeVisible();
    await expect(page.getByText('close > SMA50').first()).toBeVisible();
    await expect(page.getByText('SMA50 > SMA200').first()).toBeVisible();
    await expect(page.getByText(body.candidate.decisive_reason, { exact: false }).first()).toBeVisible();
    await expect(page.getByText('Not a guaranteed BUY', { exact: false })).toBeVisible();

    await page.goto(`/evidence/${asian.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('FINAL_CANDIDATE').first()).toBeVisible();
    await expect(page.getByText('Passes current Phase 5 trend screen.', { exact: false }).first()).toBeVisible();

    await page.goto(`/evidence/${bajajfinsv.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('WATCH').first()).toBeVisible();
    await expect(page.getByText('Primary trend criterion passes, trend confirmation fails.', { exact: false }).first()).toBeVisible();

    await page.goto(`/evidence/${bel.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('WATCH').first()).toBeVisible();
    await expect(page.getByText('RR N/A', { exact: false })).toBeVisible();
    await expect(page.getByText('0.6052')).toHaveCount(0);
  });

  test('Invalid stock shows error state', async ({ page }) => {
    await page.goto('/evidence/999999', { waitUntil: 'load' });
    await expect(page.getByText('Stock not found', { exact: false })).toBeVisible();
  });

  test('Market data shows Batch A sessions and SMA200 ready', async ({ page, request }) => {
    const response = await request.get('/api/evidence/market-data');
    expect(response.ok()).toBeTruthy();
    const row = (await response.json()).items.find((item: { nse_symbol: string }) => item.nse_symbol === 'ADANIENT');
    expect(row.session_count).toBeGreaterThanOrEqual(247);
    expect(row.sma200_ready).toBe(true);
    await page.goto('/market-data', { waitUntil: 'load' });
    await expect(page.getByText('Market Data Status')).toBeVisible();
    await expect(page.getByText('ADANIENT')).toBeVisible();
    const card = page.getByText('ADANIENT', { exact: true }).locator('..');
    await expect(card.getByText('Session count', { exact: true }).locator('..')).toHaveText(`Session count${row.session_count}`);
    await expect(page.getByText('YES').first()).toBeVisible();
    await expect(card.getByText('Latest trading date', { exact: true }).locator('..')).toHaveText(`Latest trading date${String(row.latest_trading_date).slice(0, 10)}`);
  });
});
