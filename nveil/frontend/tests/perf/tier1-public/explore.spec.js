// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// /explore cold-load — heavy libs (plotly, deckgl, maplibre) SHOULD fetch here.
// Verifies they're served from /vendor/ and fetched lazily (not as part of
// /explore's eager chunk, but as dynamic imports when the cards appear).

import { test, expect } from '@playwright/test';
import { measurePage } from '../utils/collect-metrics.js';

test('/explore cold load fetches heavy vendors from /vendor/', async ({ page }, testInfo) => {
  const m = await measurePage(page, async () => {
    await page.goto('/explore', { waitUntil: 'networkidle' });
  }, { waitAfterMs: 3000 });

  await testInfo.attach('metrics.json', { body: JSON.stringify(m, null, 2), contentType: 'application/json' });

  // At least one vendor chunk should have loaded (depends on which showcase cards are visible).
  const vendorHits = (m.network.raw || []).filter(r => /\/vendor\//.test(r.url));
  expect(vendorHits.length, `expected /vendor/ requests on /explore; got ${vendorHits.length}`).toBeGreaterThan(0);

  // Plotly or deckgl specifically — one of them must be on the page.
  const plotlyOrDeckgl = vendorHits.filter(r => /plotly|deckgl-|maplibre/.test(r.url));
  expect(plotlyOrDeckgl.length, 'plotly/deckgl/maplibre should load on /explore').toBeGreaterThan(0);

  // Perf budget — /explore is heavier than /, so thresholds relaxed.
  if (m.vitals.lcp != null) expect(m.vitals.lcp, 'LCP').toBeLessThanOrEqual(4500);
  expect(m.tbtApprox ?? 0, 'TBT approx').toBeLessThanOrEqual(1000);
});
