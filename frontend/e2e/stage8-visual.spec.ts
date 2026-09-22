import { expect, test, type Page } from '@playwright/test';

const viewports = [
  { label: '320px', width: 320, height: 800 },
  { label: '375px', width: 375, height: 812 },
  { label: '390px', width: 390, height: 844 },
  { label: '768px', width: 768, height: 1024 },
  { label: '1024px', width: 1024, height: 768 },
];

const screens = [
  { name: 'Home', path: '/', heading: 'does not decide BUY or SELL' },
  { name: 'Candidates', path: '/final-candidates', heading: 'Candidates' },
  { name: 'Data hub', path: '/data', heading: 'Maintenance screens for stored market data' },
  { name: 'Candidate Dashboard', path: '/broker-opinion', heading: 'Broker Opinion Universe' },
  { name: 'Market Data Status', path: '/market-data', heading: 'Market Data Status' },
  { name: 'Stock Detail', path: '/consensus/4', heading: 'CARYSIL' },
  { name: 'Broker Recommendations', path: '/recommendations', heading: 'Broker Recommendations' },
  { name: 'Manual Recommendation Entry', path: '/recommendations/new', heading: 'New Recommendation' },
  { name: 'Import', path: '/imports/new', heading: 'Import Recommendations' },
  { name: 'Review Queue', path: '/review', heading: 'Review Queue' },
  { name: 'Master Data', path: '/master', heading: 'Master Data' },
  { name: 'Settings', path: '/settings', heading: 'Settings' },
  { name: 'Trade Journal', path: '/trades', heading: 'Trade Journal' },
];

async function renderedLayoutAudit(page: Page, screenName: string, viewportWidth: number) {
  const audit = await page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const visible = (element: Element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 1 && rect.height > 1;
    };
    const selector = 'main, nav, form, button, input, select, textarea, a, [role="dialog"]';
    const outside = [...document.querySelectorAll(selector)]
      .filter(visible)
      .filter((element) => element.closest('nav') === null)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          text: (element.textContent || '').trim().slice(0, 80),
          left: Math.round(rect.left * 10) / 10,
          right: Math.round(rect.right * 10) / 10,
        };
      })
      .filter((item) => item.left < -1 || item.right > viewport + 1);
    const dialogsOutside = [...document.querySelectorAll('[role="dialog"]')]
      .filter(visible)
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.left < -1 || rect.right > viewport + 1 || rect.top < -1 || rect.bottom > innerHeight + 1;
      }).length;
    return {
      documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth,
      viewport,
      outside,
      dialogsOutside,
    };
  });

  expect(audit.documentWidth, `${screenName}: document overflow`).toBeLessThanOrEqual(viewportWidth);
  expect(audit.bodyWidth, `${screenName}: body overflow`).toBeLessThanOrEqual(viewportWidth);
  expect(audit.outside, `${screenName}: important controls outside viewport`).toEqual([]);
  expect(audit.dialogsOutside, `${screenName}: dialog outside viewport`).toBe(0);
}

for (const viewport of viewports) {
  test.describe(viewport.label, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const screen of screens) {
      test(`${screen.name} is rendered within the viewport`, async ({ page }) => {
        if (screen.name === 'Import') {
          await page.route('**/api/imports/upload', (route) => route.fulfill({
            json: {
              batch_id: 999_999,
              filename: 'browser-only.csv',
              detected_headers: ['symbol', 'broker', 'date', 'rating', 'target'],
              preview_rows: [{ symbol: 'CARYSIL', broker: 'ICICI Direct', date: '2026-08-12', rating: 'BUY', target: '1410' }],
            },
          }));
          await page.route('**/api/imports/999999/mapping', (route) => route.fulfill({
            json: {
              batch_id: 999_999,
              total_rows: 1,
              valid_unique: 1,
              exact_duplicates: 0,
              probable_duplicates: 0,
              review_required: 0,
              rejected: 0,
              rows: [{
                row_number: 1,
                raw_data: {},
                mapped_data: { nse_symbol: 'CARYSIL', broker_name: 'ICICI Direct', recommendation_date: '2026-08-12' },
                action: 'UNIQUE',
                error_message: null,
              }],
            },
          }));
        }
        if (screen.name === 'Review Queue') {
          await page.route('**/api/review', (route) => route.fulfill({
            json: [{
              review_id: 999_999,
              reason: 'Browser-only layout validation',
              created_at: '2026-08-13T00:00:00',
              mapped_data: { nse_symbol: 'CARYSIL', broker_name: 'ICICI Direct', recommendation_date: '2026-08-12' },
              raw_data: { source_url: 'https://mailcontent.icicidirect.com/mailcontent/idirect_carysil_q1fy27.pdf' },
            }],
          }));
        }
        await page.goto(screen.path);
        await expect(page.getByText(screen.heading, { exact: false }).first()).toBeVisible();
        await expect(page.locator('nav')).toBeVisible();
        await expect(page.locator('nav a')).toHaveCount(4);

        if (screen.name === 'Candidate Dashboard') {
          const api = await page.request.get('/api/consensus/candidates?min_brokers=1');
          expect(api.ok()).toBeTruthy();
          const total = (await api.json()).total;
          await expect(page.getByText(`Transparent broker consensus metrics (${total} stocks)`, { exact: false })).toBeVisible();
          await page.getByRole('button', { name: /Filters & Sort/i }).click();
          await expect(page.getByText('Verification Filter')).toBeVisible();
        }

        if (screen.name === 'Stock Detail') {
          await expect(page.getByText('Broker/consensus CMP')).toBeVisible();
          await expect(page.getByText('N/A').first()).toBeVisible();
          const response = await page.request.get('/api/consensus/stocks/4');
          expect(response.ok()).toBeTruthy();
          const consensus = await response.json();
          if (consensus.contributors.length === 0) {
            await expect(page.getByText('No active broker recommendations found for this stock.')).toBeVisible();
          } else {
          await page.getByTitle('Toggle Evidence Sources').click();
          const evidenceLink = page.getByRole('link', { name: /View Link/i });
          await expect(evidenceLink).toBeVisible();
          const wrapping = await evidenceLink.evaluate((element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return { right: rect.right, overflowWrap: style.overflowWrap, wordBreak: style.wordBreak };
          });
          expect(wrapping.right).toBeLessThanOrEqual(viewport.width + 1);
          expect(['anywhere', 'break-word', 'break-all']).toContain(
            wrapping.wordBreak === 'break-all' ? 'break-all' : wrapping.overflowWrap,
          );
          }
        }

        if (screen.name === 'Broker Recommendations') {
          await expect(page.locator('main').getByText('ICICI Direct')).toHaveCount(5);
          await expect(page.locator('main').getByText('N/A')).toHaveCount(5);
        }

        if (screen.name === 'Manual Recommendation Entry') {
          await expect(page.getByRole('button', { name: 'Save Recommendation' })).toBeVisible();
          expect(await page.locator('form').evaluate((form) => getComputedStyle(form).gridTemplateColumns.split(' ').length))
            .toBe(viewport.width < 640 ? 1 : 2);
        }

        if (screen.name === 'Import') {
          await page.locator('input[type="file"]').setInputFiles({
            name: 'browser-only.csv',
            mimeType: 'text/csv',
            buffer: Buffer.from('symbol,broker,date,rating,target\nCARYSIL,ICICI Direct,2026-08-12,BUY,1410'),
          });
          await page.getByRole('button', { name: 'Upload' }).click();
          await expect(page.getByText('Step 2: Map Columns')).toBeVisible();
          await page.getByRole('button', { name: 'Process Mapping' }).click();
          await expect(page.getByText('Step 3: Preview & Confirm')).toBeVisible();
          const table = page.locator('table');
          await expect(table).toBeVisible();
          const tableContainer = table.locator('..');
          const tableBounds = await tableContainer.evaluate((element) => {
            const rect = element.getBoundingClientRect();
            return { left: rect.left, right: rect.right, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth };
          });
          expect(tableBounds.left).toBeGreaterThanOrEqual(-1);
          expect(tableBounds.right).toBeLessThanOrEqual(viewport.width + 1);
          expect(tableBounds.scrollWidth).toBeGreaterThanOrEqual(tableBounds.clientWidth);
          await expect(page.getByRole('button', { name: 'Confirm Import' })).toBeVisible();
        }

        if (screen.name === 'Review Queue') {
          await expect(page.getByText('Browser-only layout validation')).toBeVisible();
          await expect(page.getByRole('button', { name: 'Accept As New' })).toBeVisible();
          await expect(page.getByRole('button', { name: 'Reject' })).toBeVisible();
        }

        if (screen.name === 'Settings') {
          await expect(page.getByRole('button', { name: 'Save settings' })).toBeVisible();
        }

        await renderedLayoutAudit(page, screen.name, viewport.width);
      });
    }
  });
}
