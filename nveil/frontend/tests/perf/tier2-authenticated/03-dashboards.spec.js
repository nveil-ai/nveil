// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// /dashboards — empty-state rendering for a freshly signed-up user.

import { test, expect } from './_fixture.js';
import { assertAuthenticated } from './_fixture.js';

test('03 — /dashboards lists without errors', async ({ sharedPage: page }) => {
  await assertAuthenticated(page);

  // Watch the list API call directly — a successful response means 2xx,
  // not just "something came back" (401 would also match URL).
  const listRespPromise = page.waitForResponse(
    r => /\/server\/dashboards\/list/.test(r.url()) && r.status() < 400,
    { timeout: 15_000 }
  );

  const t0 = Date.now();
  await page.goto('/dashboards', { waitUntil: 'load' });

  const listResp = await listRespPromise;
  const elapsed = Date.now() - t0;

  expect(listResp.status()).toBe(200);

  console.log(`/dashboards list: ${elapsed}ms`);
  expect(elapsed, '/dashboards should load within 10s').toBeLessThanOrEqual(10_000);
});
