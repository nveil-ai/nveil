// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Login via the real UI — assumes 00-signup created the account.
//
// Flow:
//   1. Click NavBar login button (#nav-login) → auth modal opens in login mode
//   2. Fill email + password in the LoginForm
//   3. Click submit
//   4. Assert access_token cookie appears

// Import test/expect from the shared _fixture.js so this spec is part of
// the same test group as 00-signup and the rest of tier2. Otherwise
// Playwright sorts tests by their `test` object identity first, which
// would run base-test specs (like this one if it imported from
// '@playwright/test') BEFORE extended-test specs — placing 01-login
// before 00-signup. We don't actually use the sharedPage fixture here
// (this spec deliberately uses its own context for a clean login measure).
import { test, expect } from './_fixture.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { BOT } from '../utils/account-lifecycle.js';
import { newPerfContext } from '../utils/new-context.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_STATE = path.join(__dirname, '..', '.auth', 'state.json');

test('01 — login via UI', async ({ browser }) => {
  // Fresh context — no cookies, so we measure a real login round-trip.
  // (cookieConsent is pre-seeded so the CookieBanner never renders.)
  const ctx = await newPerfContext(browser);
  const page = await ctx.newPage();

  await page.goto('/', { waitUntil: 'load' });

  const t0 = Date.now();

  // 1. Open the auth modal.
  await page.locator('#nav-login').click();

  // 2. Fill LoginForm (default mode of the modal).
  //    LoginForm renders <input type="email" name="email"> and
  //    <input type="password" name="password">.
  await page.locator('input[name="email"]').fill(BOT.email);
  await page.locator('input[name="password"]').fill(BOT.password);

  // 3. Submit. The submit button's text is t("auth.signIn") = "Sign in".
  await page.locator('form button[type="submit"]').first().click();

  // 4. Wait for session cookie. access_token is HttpOnly so document.cookie
  //    can't see it — poll the context cookie jar instead.
  await expect.poll(
    async () => {
      const cookies = await ctx.cookies();
      return cookies.some(c => c.name === 'access_token');
    },
    { message: 'access_token cookie never appeared', timeout: 15_000 }
  ).toBe(true);
  const elapsed = Date.now() - t0;

  console.log(`Login UI flow: ${elapsed}ms`);
  expect(elapsed, 'login within 10s').toBeLessThanOrEqual(10_000);

  await ctx.storageState({ path: AUTH_STATE });
  await ctx.close();
});
