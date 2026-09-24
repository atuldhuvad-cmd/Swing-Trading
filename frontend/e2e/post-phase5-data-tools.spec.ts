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

  test('Broker PDF preview reads a synthetic report and stores nothing', async ({ page, request }) => {
    const runtime = auditRuntime(page);
    const uploadsBefore = await (await request.get('/api/broker-uploads')).json();
    const recsBefore = await (await request.get('/api/recommendations')).json();
    await page.goto('/broker-uploads');
    await page.locator('#broker-pdf-file').setInputFiles({ name: 'synthetic-motilal.pdf', mimeType: 'application/pdf', buffer: syntheticMotilalPdf() });
    await page.getByRole('button', { name: 'Preview PDF' }).click();
    const panel = page.getByTestId('pdf-preview');
    await expect(panel).toBeVisible();
    await expect(panel.getByText('Preview only — nothing was saved or imported', { exact: false })).toBeVisible();
    await expect(panel.getByText('Motilal Oswal', { exact: true })).toBeVisible();
    await expect(panel.getByText('2026-09-09')).toBeVisible();
    await expect(panel.getByText('3105', { exact: true })).toBeVisible();
    await expect(panel.getByText('3880', { exact: true })).toBeVisible();
    await expect(panel.getByText('BROKER_RESEARCH · Motilal Oswal')).toBeVisible();
    await expect(panel.getByText('Not stated')).toHaveCount(3);
    expect(await (await request.get('/api/broker-uploads')).json()).toEqual(uploadsBefore);
    expect((await (await request.get('/api/recommendations')).json()).length).toBe(recsBefore.length);
    expect(runtime).toEqual({ consoleErrors: [], pageErrors: [], failedRequests: [], unexpectedResponses: [] });
  });

  for (const width of widths) {
    test(`${width}px broker PDF preview has no overflow`, async ({ page }) => {
      const runtime = auditRuntime(page);
      await page.setViewportSize({ width, height: width < 500 ? 844 : 900 });
      await page.route('**/api/broker-uploads/preview', (route) => route.fulfill({ json: previewFixture() }));
      await page.goto('/broker-uploads');
      await page.locator('#broker-pdf-file').setInputFiles({ name: 'layout-check-with-a-long-file-name.pdf', mimeType: 'application/pdf', buffer: syntheticMotilalPdf() });
      await page.getByRole('button', { name: 'Preview PDF' }).click();
      await expect(page.getByTestId('preview-action')).toHaveText('CONFLICT_REVIEW_REQUIRED');
      await expect(page.getByTestId('preview-differences')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      const panelRight = await page.getByTestId('pdf-preview').evaluate((el) => el.getBoundingClientRect().right);
      expect(panelRight).toBeLessThanOrEqual(width + 1);
      expect(runtime).toEqual({ consoleErrors: [], pageErrors: [], failedRequests: [], unexpectedResponses: [] });
    });
  }
});

// ---------------------------------------------------------------- synthetic fixtures (no real report)

function syntheticMotilalPdf(): Buffer {
  const pages = [
    ['9 September 2026', 'Company Update | Sector: Infrastructure', 'Adani Enterprises',
      'Motilal Oswal research is available on www.motilaloswal.com/Institutional-Equities',
      'Asha Example - Research analyst (Asha.Example@MotilalOswal.com)', 'CMP: INR3,105 TP: INR3,880 (+25%) Buy'],
    ['Adani Enterprises 9 September 2026 2', 'Expected return (over 12-month) BUY >=15%', 'Motilal Oswal Financial Services Limited'],
  ];
  const esc = (s: string) => s.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
  const objects: string[] = [];
  const add = (body: string) => { objects.push(body); return objects.length; };
  const font = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>');
  const pagesId = objects.length + 1 + 2 * pages.length;
  const pageIds: number[] = [];
  for (const lines of pages) {
    const stream = lines.map((line, i) => `BT /F1 9 Tf 1 0 0 1 40 ${800 - 14 * i} Tm (${esc(line)}) Tj ET`).join('\n');
    const content = add(`<< /Length ${Buffer.byteLength(stream, 'latin1')} >>\nstream\n${stream}\nendstream`);
    pageIds.push(add(`<< /Type /Page /Parent ${pagesId} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 ${font} 0 R >> >> /Contents ${content} 0 R >>`));
  }
  add(`<< /Type /Pages /Kids [${pageIds.map((p) => `${p} 0 R`).join(' ')}] /Count ${pageIds.length} >>`);
  const catalog = add(`<< /Type /Catalog /Pages ${pagesId} 0 R >>`);
  let out = '%PDF-1.4\n';
  const offsets: number[] = [];
  objects.forEach((body, i) => { offsets.push(Buffer.byteLength(out, 'latin1')); out += `${i + 1} 0 obj\n${body}\nendobj\n`; });
  const xref = Buffer.byteLength(out, 'latin1');
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n` + offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('');
  out += `trailer\n<< /Size ${objects.length + 1} /Root ${catalog} 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, 'latin1');
}

function previewFixture() {
  return {
    action: 'CONFLICT_REVIEW_REQUIRED', persisted: false,
    file: { original_filename: 'layout-check-with-a-long-file-name.pdf', size_bytes: 324692, sha256: 'f'.repeat(64), duplicate_file: false, duplicate_of_upload_id: null },
    discovery: { discovery_source: 'Trendlyne', discovery_url: null, discovery_url_status: 'UNAVAILABLE' },
    canonical_source: { source_type: 'BROKER_RESEARCH', publication_name: 'ICICI Securities', proposed_verification_status: 'VERIFIED_PRIMARY', verification_state: 'PENDING_VISUAL_CONFIRMATION' },
    extraction: {
      report_type: { value: 'Company Update', status: 'KNOWN' }, report_date: { value: '2026-08-31', status: 'KNOWN' },
      report_cmp: { value: '720', status: 'KNOWN' }, cmp_as_of: { value: null, status: 'NOT_STATED' },
      target: { value: '920', status: 'KNOWN' }, previous_target: { value: '1020', status: 'KNOWN' },
      entry_low: { value: null, status: 'NOT_STATED' }, stop_loss: { value: null, status: 'NOT_STATED' },
      time_horizon: { value: null, status: 'NOT_STATED' }, analysts: { value: ['Ravi Sample', 'Meera Placeholder'], status: 'KNOWN' },
    },
    broker: { name: 'ICICI Securities' },
    stock: { company_name: 'HDFC Bank', nse_symbol: 'HDFCBANK', status: 'KNOWN' },
    rating: { original: 'BUY (Maintain)', normalized: 'BUY' },
    existing_match: { recommendation_id: 1, normalized_rating: 'BUY', recommendation_date: '2026-08-31', recommended_price: '709.6', target_price: '925' },
    differences: [{ field: 'report_cmp (recommended_price)', report: '720', stored: '709.6' }, { field: 'target', report: '920', stored: '925' }],
    not_stated_in_report: ['entry_low stored as 725.0 but not stated in this report'],
    warnings: ['TARGET_REVISED: previous target 1020 shown in parentheses', 'NO_STOP_LOSS_STATED: stop loss stays empty',
      'NO_ENTRY_RANGE_STATED: entry range stays empty; the report CMP is not an entry price'],
  };
}
