// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Direct /server/auth/login to get a valid session without driving the UI.
// Used by tests that need a fresh session between scenarios (post-logout
// re-auth, deletion-verification after logout, etc.) without re-running
// the full UI login (which we test separately in 01-login.spec.js).
//
// Takes a Playwright APIRequestContext so CSRF cookies are handled.

import { expect } from '@playwright/test';

/**
 * Authenticate via the backend API. Returns cookies the caller can set
 * on a browser context via context.addCookies(...).
 *
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} baseURL        — e.g. https://localhost:8000
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{cookies: import('@playwright/test').Cookie[], response: any}>}
 */
export async function apiLogin(request, baseURL, email, password) {
  // 1. Prime the CSRF cookie + token.
  const csrfResp = await request.get(`${baseURL}/server/auth/csrf`, { ignoreHTTPSErrors: true });
  expect(csrfResp.ok(), `CSRF bootstrap failed: ${csrfResp.status()}`).toBeTruthy();
  const csrfJson = await csrfResp.json();
  const csrfToken = csrfJson.csrfToken;

  // 2. Submit the form-urlencoded login.
  const loginResp = await request.post(`${baseURL}/server/auth/login`, {
    form: { username: email, password },
    headers: { 'X-CSRF-Token': csrfToken },
    ignoreHTTPSErrors: true,
  });
  expect(loginResp.ok(), `login failed: ${loginResp.status()} ${await loginResp.text().catch(() => '')}`).toBeTruthy();

  // 3. Grab the cookies attached by the response.
  const storageState = await request.storageState();
  return { cookies: storageState.cookies, response: await loginResp.json().catch(() => ({})) };
}

/**
 * Shove auth cookies into a browser context so subsequent page.goto is authenticated.
 * Equivalent to saving via storageState, but programmatic and does not touch disk.
 */
export async function installSessionCookies(context, cookies) {
  await context.addCookies(cookies);
}
