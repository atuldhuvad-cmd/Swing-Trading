import { expect, test, type Page, type Request, type Response } from '@playwright/test';

const viewports = [
  { label: '320px', width: 320, height: 800 },
  { label: '375px', width: 375, height: 812 },
  { label: '390px', width: 390, height: 844 },
  { label: '768px', width: 768, height: 1024 },
  { label: '1024px', width: 1024, height: 768 },
];

const routes = [
  { name: 'Home', path: '/' },
  { name: 'Candidates', path: '/final-candidates' },
  { name: 'Data hub', path: '/data' },
  { name: 'Broker opinion', path: '/broker-opinion' },
  { name: 'Market Data', path: '/market-data' },
  { name: 'Candidate Evidence ADANIENT', path: '/evidence/9' },
  { name: 'Candidate Evidence invalid', path: '/evidence/999999' },
  { name: 'Stock Consensus', path: '/consensus/4' },
  { name: 'Recommendations', path: '/recommendations' },
  { name: 'Recommendation Entry', path: '/recommendations/new' },
  { name: 'Import', path: '/imports/new' },
  { name: 'Review', path: '/review' },
  { name: 'Master', path: '/master' },
  { name: 'Settings', path: '/settings' },
  { name: 'Trade Journal', path: '/trades' },
  { name: 'Source Readiness', path: '/source-readiness' },
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

function unexpectedConsole(errors: string[], path: string) {
  return errors.filter((text) => {
    if (path === '/evidence/999999' && text.includes('404')) return false;
    return true;
  });
}

function unexpectedHttp(httpErrors: { url: string; status: number }[], path: string) {
  return httpErrors.filter((e) => {
    if (path === '/evidence/999999' && e.status === 404 && e.url.includes('/api/evidence/stocks/999999')) {
      return false;
    }
    return true;
  });
}

test.describe('Dedicated console and network audit', () => {
  for (const viewport of viewports) {
    test.describe(viewport.label, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height } });

      for (const route of routes) {
        test(`${route.name}`, async ({ page }) => {
          const audit = attachAudit(page);
          await page.goto(route.path, { waitUntil: 'load' });
          await page.waitForTimeout(800);
          const snap = audit.snapshot();
          const unexpected = unexpectedHttp(snap.httpErrors, route.path);
          expect(unexpectedConsole(snap.consoleErrors, route.path), `${route.name} console.error`).toEqual([]);
          expect(snap.pageErrors, `${route.name} uncaught`).toEqual([]);
          expect(snap.failedRequests, `${route.name} failed requests`).toEqual([]);
          expect(unexpected, `${route.name} unexpected HTTP`).toEqual([]);

          const overflow = await page.evaluate(() => ({
            documentWidth: document.documentElement.scrollWidth,
            viewport: document.documentElement.clientWidth,
          }));
          expect(overflow.documentWidth, `${route.name} overflow`).toBeLessThanOrEqual(overflow.viewport);
        });
      }
    });
  }
});
