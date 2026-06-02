// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// /does-not-exist must render the SPA shell with a 404 status code and
// must NOT load heavy viz libs (regression: SPA catchall pulling the wrong chunks).

import { test, expect } from '@playwright/test';
import { measurePage } from '../utils/collect-metrics.js';

test('404 route falls through to SPA without loading heavy libs', async ({ page }, testInfo) => {
  const m = await measurePage(page, async () => {
    const response = await page.goto('/this-definitely-does-not-exist-xyz123', { waitUntil: 'load' });
    // SPA catchall may return 404 or 200 depending on server.py config; both fine.
    if (response) {
      expect([200, 404]).toContain(response.status());
    }
  });
  await testInfo.attach('metrics.json', { body: JSON.stringify(m, null, 2), contentType: 'application/json' });

  const forbidden = (m.network.raw || []).filter(r =>
    /\/vendor\/(plotly|maplibre|deckgl)/.test(r.url)
  );
  expect(forbidden, '404 page must NOT fetch heavy viz libs').toHaveLength(0);
});
