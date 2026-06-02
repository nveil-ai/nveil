// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Logout via UI — verify cookies cleared. NavBar has a stable #nav-logout
// button that opens a confirm dialog; clicking "Disconnect" in the dialog
// performs the actual logout.

import { test, expect } from './_fixture.js';
import { assertAuthenticated } from './_fixture.js';

test('09 — logout clears cookies', async ({ sharedPage: page }) => {
  await assertAuthenticated(page);
  await page.goto('/', { waitUntil: 'load' });

  // Open the logout confirm dialog. #nav-logout is a stable id in NavBar.
  await page.locator('#nav-logout').click();

  const t0 = Date.now();

  // Confirm dialog has a "Disconnect" button (t("nav.disconnect")).
  await page.getByRole('button', { name: /disconnect|déconnecter/i }).click();

  // access_token is HttpOnly — poll the context cookie jar, not document.cookie.
  await expect.poll(async () => {
    const cookies = await page.context().cookies();
    return cookies.some(c => c.name === 'access_token' && c.value);
  }, { message: 'access_token cookie still present', timeout: 10_000 }).toBe(false);
  const elapsed = Date.now() - t0;

  console.log(`Logout UI flow: ${elapsed}ms`);
  expect(elapsed).toBeLessThanOrEqual(5000);
});
