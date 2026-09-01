import { expect, test, type Page } from '@playwright/test';

const viewports = [
  { label: '320', width: 320, height: 800 },
  { label: '375', width: 375, height: 812 },
  { label: '390', width: 390, height: 844 },
  { label: '768', width: 768, height: 1024 },
  { label: '1024', width: 1024, height: 768 },
];

async function overflowAudit(page: Page) {
  return page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
}

test.describe('Back navigation', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('Final Candidates → Evidence → Back', async ({ page, request }) => {
    const listed = await request.get('/api/evidence/candidates');
    const items = (await listed.json()).items || [];
    const row = items.find((r: { nse_symbol: string }) => r.nse_symbol === 'ADANIENT') || items[0];
    expect(row).toBeTruthy();

    await page.goto('/final-candidates', { waitUntil: 'load' });
    await expect(page.getByRole('heading', { name: 'Candidates' })).toBeVisible();
    await page.getByRole('button', { name: new RegExp(row.nse_symbol) }).click();
    await expect(page.getByRole('heading', { name: 'Candidate Detail / Evidence' })).toBeVisible();
    await page.getByTestId('back-link').click();
    await expect(page.getByRole('heading', { name: 'Candidates' })).toBeVisible();
  });

  test('Evidence → Plan Trade → Back', async ({ page, request }) => {
    const listed = await request.get('/api/evidence/candidates');
    const items = (await listed.json()).items || [];
    const row = items.find((r: { nse_symbol: string }) => r.nse_symbol === 'CIPLA')
      || items.find((r: { status: string }) => r.status === 'FINAL_CANDIDATE')
      || items[0];
    expect(row).toBeTruthy();

    await page.goto(`/evidence/${row.stock_id}`, { waitUntil: 'load' });
    await expect(page.getByRole('heading', { name: 'Candidate Detail / Evidence' })).toBeVisible();
    await page.getByRole('link', { name: 'Plan Trade' }).click();
    await expect(page.getByRole('heading', { name: /Plan Trade/ })).toBeVisible();
    await page.getByTestId('back-link').click();
    await expect(page.getByRole('heading', { name: 'Candidate Detail / Evidence' })).toBeVisible();
  });

  test('Broker opinion → Consensus detail → Back', async ({ page }) => {
    await page.goto('/broker-opinion', { waitUntil: 'load' });
    await expect(page.getByText('Broker Opinion Universe')).toBeVisible();
    const card = page.locator('main .cursor-pointer').first();
    await expect(card).toBeVisible();
    await card.click();
    await expect(page.getByTestId('back-link')).toBeVisible();
    await page.getByTestId('back-link').click();
    await expect(page.getByText('Broker Opinion Universe')).toBeVisible();
  });

  test('direct/deep-link evidence fallback is Candidates', async ({ page }) => {
    await page.goto('/evidence/9', { waitUntil: 'load' });
    await expect(page.getByTestId('back-link')).toBeVisible();
    await page.getByTestId('back-link').click();
    await expect(page.getByRole('heading', { name: 'Candidates' })).toBeVisible();
  });

  test('direct/deep-link consensus fallback is Broker Opinion Universe', async ({ page }) => {
    await page.goto('/consensus/4', { waitUntil: 'load' });
    await expect(page.getByTestId('back-link')).toBeVisible();
    await page.getByTestId('back-link').click();
    await expect(page.getByText('Broker Opinion Universe')).toBeVisible();
  });
});

for (const viewport of viewports) {
  test.describe(`Back control overflow ${viewport.label}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test('evidence and consensus Back stay within viewport', async ({ page }) => {
      await page.goto('/evidence/9', { waitUntil: 'load' });
      await expect(page.getByTestId('back-link')).toBeVisible();
      const evidenceAudit = await overflowAudit(page);
      expect(evidenceAudit.documentWidth, `${viewport.label} evidence overflow`).toBeLessThanOrEqual(viewport.width + 1);

      await page.goto('/consensus/4', { waitUntil: 'load' });
      await expect(page.getByTestId('back-link')).toBeVisible();
      const box = await page.getByTestId('back-link').boundingBox();
      expect(box).toBeTruthy();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      const consensusAudit = await overflowAudit(page);
      expect(consensusAudit.documentWidth, `${viewport.label} consensus overflow`).toBeLessThanOrEqual(viewport.width + 1);
    });
  });
}
