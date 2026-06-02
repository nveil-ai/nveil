// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Landing cold-load perf benchmark.
// Runs 5 times, reports median, asserts Core Web Vitals budgets.

import { test, expect } from '@playwright/test';
import { measurePage, measureN } from '../utils/collect-metrics.js';
import { applyThrottling, profileForProject } from '../utils/throttling.js';
import { newPerfContext } from '../utils/new-context.js';

// Budgets calibrated for the LOCAL Docker Compose stack (no Cloudflare edge
// compression, uncompressed-ish transfers). Production hits Cloudflare for
// the first byte of most assets, so real-world transfers are ~40% smaller.
// The `compare-runs.mjs` baseline comparator catches PRs that REGRESS from
// the current run; these absolute budgets only guard against massive drift.
const BUDGETS = {
  ttfb: 800,
  fcp: 2500,
  lcp: 3500,
  cls: 0.1,
  tbtApprox: 800,
  totalTransferBytesKb: 2000,
};

test.describe('landing page', () => {
  test('cold-load Web Vitals — 5 runs, median in green', async ({ browser }, testInfo) => {
    const profile = profileForProject(testInfo.project.name);
    const result = await measureN(async () => {
      const ctx = await newPerfContext(browser);
      const page = await ctx.newPage();
      await applyThrottling(page, profile);
      const m = await measurePage(page, async () => {
        await page.goto('/', { waitUntil: 'load' });
      });
      await ctx.close();
      return m;
    }, 5);

    await testInfo.attach('metrics.json', {
      body: JSON.stringify(result, null, 2),
      contentType: 'application/json',
    });
    console.log(`Landing median: ${JSON.stringify(result.median)}`);

    const m = result.median;
    if (m.ttfb   != null) expect(m.ttfb,   'TTFB median').toBeLessThanOrEqual(BUDGETS.ttfb);
    if (m.fcp    != null) expect(m.fcp,    'FCP median').toBeLessThanOrEqual(BUDGETS.fcp);
    if (m.lcp    != null) expect(m.lcp,    'LCP median').toBeLessThanOrEqual(BUDGETS.lcp);
    if (m.cls    != null) expect(m.cls,    'CLS median').toBeLessThanOrEqual(BUDGETS.cls);
    expect(m.tbtApprox ?? 0, 'TBT approx').toBeLessThanOrEqual(BUDGETS.tbtApprox);
    if (m.totalTransferBytes != null) {
      expect(m.totalTransferBytes / 1024, 'total transfer').toBeLessThanOrEqual(BUDGETS.totalTransferBytesKb);
    }
  });
});
