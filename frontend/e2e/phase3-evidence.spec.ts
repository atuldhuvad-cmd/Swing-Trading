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
    expect(items.length).toBe(27);
    expect(counts.FINAL_CANDIDATE || 0).toBe(3);
    expect(counts.WATCH || 0).toBe(4);
    expect(counts.REJECTED || 0).toBe(13);
    expect(counts.INSUFFICIENT_DATA || 0).toBe(7);
    expect(items.filter((row: { rr_available?: boolean }) => row.rr_available).length).toBe(17);
    expect(items.some((row: { rr_ratio?: string | null }) => row.rr_ratio === '0.6052')).toBeFalsy();

    const rejected = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'ADANIENT');
    const watch = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'HCLTECH');
    const finalRow = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'ADANIPORTS');
    const rrNa = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'DRREDDY');
    expect(rejected?.status).toBe('REJECTED');
    expect(watch?.status).toBe('WATCH');
    expect(finalRow?.status).toBe('FINAL_CANDIDATE');
    expect(rrNa?.status).toBe('WATCH');
    expect(rrNa?.rr_available).toBeFalsy();

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
    await expect(page.getByRole('button', { name: /HCLTECH/ }).getByText(watch.decisive_reason, { exact: false })).toBeVisible();
    await expect(page.getByText('close > SMA50').first()).toBeVisible();
    await expect(page.getByText('SMA50 > SMA200').first()).toBeVisible();
  });

  test('Candidate detail shows latest close, revenue, criteria, and RR evidence', async ({ page, request }) => {
    const listed = await request.get('/api/evidence/candidates');
    const items = (await listed.json()).items || [];
    const adanient = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'ADANIENT');
    const finalRow = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'ADANIPORTS');
    const watch = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'HCLTECH');
    const rrNa = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'DRREDDY');
    const missing = items.find((row: { nse_symbol: string }) => row.nse_symbol === 'INDIGO');
    expect(adanient && finalRow && watch && rrNa && missing).toBeTruthy();

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

    await page.goto(`/evidence/${finalRow.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('FINAL_CANDIDATE').first()).toBeVisible();
    await expect(page.getByText('Passes current Phase 5 trend screen.', { exact: false }).first()).toBeVisible();

    await page.goto(`/evidence/${watch.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('WATCH').first()).toBeVisible();
    await expect(page.getByText('Primary trend criterion passes, trend confirmation fails.', { exact: false }).first()).toBeVisible();

    await page.goto(`/evidence/${rrNa.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('WATCH').first()).toBeVisible();
    await expect(page.getByText('RR N/A', { exact: false })).toBeVisible();
    await expect(page.getByText('0.6052')).toHaveCount(0);

    await page.goto(`/evidence/${missing.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByText('INSUFFICIENT_DATA').first()).toBeVisible();
    await expect(page.getByText('Mandatory evidence unavailable.', { exact: false }).first()).toBeVisible();
    await expect(page.getByText('No core fundamentals collected', { exact: false })).toBeVisible();
    await expect(page.getByText('RR N/A', { exact: false })).toBeVisible();
    await expect(page.getByTestId('insufficient-data-caution')).toBeVisible();
    await expect(page.getByRole('link', { name: 'Plan Trade' })).toBeVisible();

    await page.goto(`/trades/plan/${missing.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByTestId('insufficient-data-caution')).toBeVisible();
    await expect(page.locator('#save-planned-trade')).toBeEnabled();
    await expect(page.getByText('never applied as your trade size', { exact: false })).toBeVisible();
    await expect(page.locator('main')).not.toContainText('guaranteed BUY recommendation');

    await page.goto(`/evidence/${finalRow.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByTestId('insufficient-data-caution')).toHaveCount(0);
  });

  test('Criteria and reasons appear in the same order in list and detail', async ({ page, request }) => {
    const items = (await (await request.get('/api/evidence/candidates')).json()).items || [];
    const insufficient = items.filter((row: { status: string }) => row.status === 'INSUFFICIENT_DATA');
    expect(insufficient.length).toBe(7);
    for (const row of items) {
      const detail = await (await request.get(`/api/evidence/stocks/${row.stock_id}`)).json();
      const names = (rows: Array<{ criterion: string; result: string; reason: string | null }>) =>
        rows.map((c) => `${c.criterion}|${c.result}|${c.reason}`);
      expect(detail.candidate.evaluation_id, row.nse_symbol).toBe(row.evaluation_id);
      expect(names(detail.criteria), row.nse_symbol).toEqual(names(row.criteria));
      expect(detail.candidate.decisive_reason, row.nse_symbol).toBe(row.decisive_reason);
    }

    await page.goto('/final-candidates', { waitUntil: 'load' });
    for (const row of insufficient) {
      const card = page.getByRole('button', { name: new RegExp(`\\b${row.nse_symbol}\\b`) });
      await expect(card.getByText(row.decisive_reason, { exact: false })).toBeVisible();
    }
    for (const row of insufficient) {
      await page.goto(`/evidence/${row.stock_id}`, { waitUntil: 'load' });
      await expect(page.getByText(`Reason: ${row.decisive_reason}`, { exact: false })).toBeVisible();
    }
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
