// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Smoke tests for /feedback and /plan — basic perf budget, no errors.

import { test, expect } from '@playwright/test';
import { measurePage } from '../utils/collect-metrics.js';

for (const route of ['/feedback', '/plan']) {
  test(`smoke ${route}`, async ({ page }, testInfo) => {
    const m = await measurePage(page, async () => {
      await page.goto(route, { waitUntil: 'load' });
    });
    await testInfo.attach('metrics.json', { body: JSON.stringify(m, null, 2), contentType: 'application/json' });

    // Page must actually have rendered something.
    const body = await page.locator('body').innerHTML();
    expect(body.length, `${route} should render content`).toBeGreaterThan(500);

    // No 5xx errors.
    const hardErrors = (m.network.errors || []).filter(e => e.status >= 500);
    expect(hardErrors, `${route} 5xx errors`).toHaveLength(0);

    // Loose LCP budget — these are smaller pages than landing.
    if (m.vitals.lcp != null) expect(m.vitals.lcp).toBeLessThanOrEqual(3500);
  });
}
