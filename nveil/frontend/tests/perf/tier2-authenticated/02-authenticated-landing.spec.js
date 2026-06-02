// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Authenticated / — additional API calls (auth/me, rooms/list, dashboards/list)
// happen on top of the landing's normal Web Vitals measurement.

import { test, expect } from './_fixture.js';
import { assertAuthenticated } from './_fixture.js';
import { measurePage } from '../utils/collect-metrics.js';

test('02 — authenticated landing page', async ({ sharedPage: page }, testInfo) => {
  await assertAuthenticated(page);
  // 'load' not 'networkidle' — this app keeps WebSockets open, so
  // networkidle never fires and the goto() stalls until timeout.
  const m = await measurePage(page, async () => {
    await page.goto('/', { waitUntil: 'load' });
  }, { waitAfterMs: 2000 });
  await testInfo.attach('metrics.json', { body: JSON.stringify(m, null, 2), contentType: 'application/json' });

  // Functional — we're logged in, so auth/me should have succeeded.
  const authMe = (m.network.raw || []).find(r => /\/server\/auth\/me/.test(r.url));
  expect(authMe, '/server/auth/me should have been called').toBeTruthy();
  expect(authMe.status, '/server/auth/me should return 200').toBe(200);

  // Perf — authenticated landing has extra API calls + hydration, so TBT
  // is looser than cold unauthenticated landing.
  if (m.vitals.lcp != null) expect(m.vitals.lcp).toBeLessThanOrEqual(3500);
  expect(m.tbtApprox ?? 0).toBeLessThanOrEqual(1200);
});
