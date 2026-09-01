import { expect, test, type Page } from '@playwright/test';

/**
 * Browser lifecycle against a disposable DB copy only.
 * Skip unless TRADE_LIFECYCLE_E2E=1 so a default Playwright run cannot
 * write journal rows into production.
 */
test.skip(!process.env.TRADE_LIFECYCLE_E2E, 'Requires TRADE_LIFECYCLE_E2E=1 and a disposable backend');

const viewports = [
  { label: '320', width: 320, height: 800 },
  { label: '375', width: 375, height: 812 },
  { label: '390', width: 390, height: 844 },
  { label: '768', width: 768, height: 1024 },
  { label: '1024', width: 1024, height: 768 },
];

async function overflowAudit(page: Page) {
  return page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    return {
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      viewport,
    };
  });
}

async function pickFinalCandidate(request: Parameters<typeof test>[0] extends never ? never : { get: (url: string) => Promise<{ json: () => Promise<any> }> }) {
  const listed = await request.get('/api/evidence/candidates');
  const items = (await listed.json()).items || [];
  const row = items.find((r: { status: string; rr_available?: boolean }) => r.status === 'FINAL_CANDIDATE' && r.rr_available)
    || items.find((r: { status: string }) => r.status === 'FINAL_CANDIDATE');
  if (!row) throw new Error('No FINAL_CANDIDATE found for disposable workflow');
  return row as { stock_id: number; nse_symbol: string; evaluation_id: number };
}

async function fillDatetime(page: Page, selector: string, value: string) {
  const locator = page.locator(selector);
  await locator.fill(value);
  const current = await locator.inputValue();
  if (!current) {
    await locator.evaluate((el, v) => {
      const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
      proto?.set?.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, value);
  }
}

test.describe('Trade journal lifecycle (disposable)', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('PLANNED → OPEN → CLOSED with manual prices and persisted sources', async ({ page, request }) => {
    const candidate = await pickFinalCandidate(request);

    await page.goto(`/evidence/${candidate.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByRole('heading', { name: 'Candidate Detail / Evidence' })).toBeVisible();
    await page.getByRole('link', { name: 'Plan Trade' }).click();
    await expect(page.getByRole('heading', { name: /Plan Trade/ })).toBeVisible();
    await page.locator('#plan-risk').fill('500');
    await page.locator('#calc-position-size').click();
    await expect(page.getByText(/Hint qty:/).or(page.getByText(/Error:/))).toBeVisible({ timeout: 10_000 });
    await page.locator('#save-planned-trade').click();
    await expect(page.getByRole('heading', { name: 'Trade Journal' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(candidate.nse_symbol).first()).toBeVisible();
    await expect(page.getByText('PLANNED').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Record Entry' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel Plan' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Record Exit' })).toHaveCount(0);

    await page.getByRole('button', { name: 'Record Entry' }).first().click();
    await expect(page.getByRole('heading', { name: 'Record Entry' })).toBeVisible();
    await page.locator('#open-entry-price').fill('101.25');
    await fillDatetime(page, '#open-entry-date', '2026-08-20T10:30');
    await page.locator('#open-price-source').fill('Manual observation');
    await page.locator('#open-quantity').fill('10');
    await page.locator('#open-trade-submit').click();
    await expect(page.getByRole('heading', { name: 'Record Entry' })).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByText('OPEN').first()).toBeVisible();
    await expect(page.getByTestId('entry-price-source')).toHaveText('Manual observation');

    await page.reload({ waitUntil: 'load' });
    await expect(page.getByText('OPEN').first()).toBeVisible();
    await expect(page.getByTestId('entry-price-source')).toHaveText('Manual observation');
    await expect(page.getByRole('button', { name: 'Record Exit' }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Record Entry' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Cancel Plan' })).toHaveCount(0);

    await page.getByRole('button', { name: 'Record Exit' }).first().click();
    await expect(page.getByRole('heading', { name: 'Record Exit' })).toBeVisible();
    await page.locator('#close-exit-price').fill('120.50');
    await fillDatetime(page, '#close-exit-date', '2026-08-21T15:00');
    await page.locator('#close-price-source').fill('Broker app');
    await page.locator('#close-trade-submit').click();
    await expect(page.getByRole('heading', { name: 'Record Exit' })).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByText('CLOSED').first()).toBeVisible();
    await expect(page.getByTestId('exit-price-source')).toHaveText('Broker app');
    await expect(page.getByText(/Closed — no further actions/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Record Entry' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Record Exit' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Cancel Plan' })).toHaveCount(0);

    await page.reload({ waitUntil: 'load' });
    await expect(page.getByText('CLOSED').first()).toBeVisible();
    await expect(page.getByTestId('entry-price-source')).toHaveText('Manual observation');
    await expect(page.getByTestId('exit-price-source')).toHaveText('Broker app');
    await expect(page.getByRole('button', { name: 'Record Entry' })).toHaveCount(0);
    await expect(page.getByRole('link', { name: /View evidence/ })).toBeVisible();
  });

  test('PLANNED → CANCELLED preserves the journal row', async ({ page, request }) => {
    const candidate = await pickFinalCandidate(request);
    await page.goto(`/trades/plan/${candidate.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByRole('heading', { name: /Plan Trade/ })).toBeVisible();
    await page.locator('#plan-risk').fill('400');
    await page.locator('#calc-position-size').click();
    await page.locator('#save-planned-trade').click();
    await expect(page.getByRole('heading', { name: 'Trade Journal' })).toBeVisible({ timeout: 10_000 });

    const plannedCard = page.locator('div.bg-white.rounded-xl').filter({ hasText: 'PLANNED' }).first();
    await expect(plannedCard.getByRole('button', { name: 'Cancel Plan' })).toBeVisible();
    await plannedCard.getByRole('button', { name: 'Cancel Plan' }).click();
    await expect(page.getByRole('heading', { name: 'Cancel Plan' })).toBeVisible();
    await page.locator('#cancel-trade-confirm').click();
    await expect(page.getByRole('heading', { name: 'Cancel Plan' })).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByText('CANCELLED').first()).toBeVisible();
    await expect(page.getByText(/Cancelled — no further actions/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Record Entry' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Cancel Plan' })).toHaveCount(0);

    await page.reload({ waitUntil: 'load' });
    await expect(page.getByText('CANCELLED').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Record Entry' })).toHaveCount(0);
  });
});

for (const viewport of viewports) {
  test.describe(`Trade journal overflow ${viewport.label}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test('journal page does not overflow', async ({ page }) => {
      await page.goto('/trades', { waitUntil: 'load' });
      await expect(page.getByRole('heading', { name: 'Trade Journal' })).toBeVisible();
      const audit = await overflowAudit(page);
      expect(audit.documentWidth, `${viewport.label} document overflow`).toBeLessThanOrEqual(viewport.width + 1);
      expect(audit.bodyWidth, `${viewport.label} body overflow`).toBeLessThanOrEqual(viewport.width + 1);
    });
  });
}
