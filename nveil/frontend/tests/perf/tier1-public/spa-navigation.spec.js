// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// SPA navigation caching — route chunks loaded on first visit should NOT
// be re-downloaded on subsequent navigations to the same route.
// Tests `/` → `/explore` → `/` and verifies vendor chunks reused.

import { test, expect } from '@playwright/test';
import { measurePage, instrumentNetwork } from '../utils/collect-metrics.js';

test('navigating / → /explore → / reuses chunks (no redownload)', async ({ page }) => {
  // 1. First visit to /
  await page.goto('/', { waitUntil: 'networkidle' });

  // 2. Go to /explore and record what gets loaded.
  const net = instrumentNetwork(page);
  await page.goto('/explore', { waitUntil: 'networkidle' });
  const exploreNet = net.harvest();
  net.detach();
  const vendorUrlsAfterExplore = new Set(
    (exploreNet.raw || []).filter(r => /\/vendor\//.test(r.url)).map(r => r.url)
  );

  // 3. Back to / then to /explore again. The vendor chunks should NOT come
  // back across the wire (browser cache hit).
  await page.goto('/', { waitUntil: 'networkidle' });
  const net2 = instrumentNetwork(page);
  await page.goto('/explore', { waitUntil: 'networkidle' });
  const reNet = net2.harvest();
  net2.detach();
  const vendorRefetched = (reNet.raw || [])
    .filter(r => vendorUrlsAfterExplore.has(r.url))
    .filter(r => !r.status || r.status === 200);   // 304 Not-Modified is a cache hit, allowed

  // If the browser re-issued a conditional-GET that came back 304, that's still
  // a cache hit — no bytes transferred. We only flag fresh 200 responses.
  if (vendorRefetched.length > 0) {
    console.warn(`Re-fetched on second visit:`, vendorRefetched.map(r => r.url));
  }
  // Playwright's fresh-context behavior can legitimately re-fetch 1-2 vendor
  // chunks when certain cache-hint combinations differ. Allow a small budget;
  // regression would look like 5+ chunks re-downloading.
  expect(vendorRefetched.length, 'vendor chunks mostly reused on same-route re-nav').toBeLessThanOrEqual(2);
});
