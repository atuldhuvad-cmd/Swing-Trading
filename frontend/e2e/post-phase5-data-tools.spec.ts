import { expect, test } from '@playwright/test';

const widths = [320, 375, 390, 768, 1024];

function auditRuntime(page: import('@playwright/test').Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedRequests: string[] = [];
  const unexpectedResponses: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('requestfailed', (request) => failedRequests.push(`${request.method()} ${request.url()}`));
  page.on('response', (response) => {
    if (response.status() >= 400) unexpectedResponses.push(`${response.status()} ${response.url()}`);
  });
  return { consoleErrors, pageErrors, failedRequests, unexpectedResponses };
}

test.describe('post-Phase-5 data tools', () => {
  test('Data Sync shows safe job behavior without running a job', async ({ page }) => {
    const runtime = auditRuntime(page);
    await page.goto('/data-sync');
    await expect(page.getByRole('heading', { name: 'Data Sync' })).toBeVisible();
    await expect(page.getByText('NSE OHLCV + Bhavcopy')).toBeVisible();
    await expect(page.getByText('Quarterly fundamentals filings')).toBeVisible();
    await expect(page.getByText('ICICI Direct broker recommendations')).toBeVisible();
    await expect(page.getByText('I understand this will back up')).toBeVisible();
    const buttons = page.getByRole('button', { name: 'Run now' });
    await expect(buttons.first()).toBeDisabled();
    expect(runtime).toEqual({ consoleErrors: [], pageErrors: [], failedRequests: [], unexpectedResponses: [] });
  });

  test('Broker Uploads loads and validates before upload', async ({ page }) => {
    const runtime = auditRuntime(page);
    await page.goto('/broker-uploads');
    await expect(page.getByRole('heading', { name: 'Upload Broker PDF' })).toBeVisible();
    await page.getByRole('button', { name: 'Upload PDF' }).click();
    await expect(page.getByText('Broker name and a PDF file are required')).toBeVisible();
    expect(runtime).toEqual({ consoleErrors: [], pageErrors: [], failedRequests: [], unexpectedResponses: [] });
  });

  for (const width of widths) {
    test(`${width}px has no page-level overflow on new routes`, async ({ page }) => {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      for (const path of ['/data-sync', '/broker-uploads']) {
        await page.goto(path);
        await expect(page.locator('main h1')).toBeVisible();
        await expect(page.getByText('Loading…')).toHaveCount(0);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await expect(page.locator('nav')).toBeVisible();
      }
    });
  }
});
