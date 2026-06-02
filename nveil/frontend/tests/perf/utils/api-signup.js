// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Direct /server/auth/register fallback — used by utils/account-lifecycle.js
// when a prior test run left the bot account around (rare but possible after
// a crash). Also useful as a last-ditch "make the account exist" in global-
// setup if the UI signup spec hasn't run yet.
//
// Production signup path is exercised by tier2-authenticated/00-signup.spec.js;
// this is for plumbing, not the functional assertion.

import { expect } from '@playwright/test';

/**
 * @param {import('@playwright/test').APIRequestContext} request
 * @param {string} baseURL
 * @param {object} opts
 * @param {string} opts.email
 * @param {string} opts.password
 * @param {string} opts.name
 */
export async function apiSignup(request, baseURL, { email, password, name }) {
  const resp = await request.post(`${baseURL}/server/auth/register`, {
    data: { email, password, name },
    ignoreHTTPSErrors: true,
  });
  // 400 "Email already registered" is acceptable — caller decides.
  if (resp.status() === 400) {
    const body = await resp.text().catch(() => '');
    if (body.includes('already registered')) {
      return { alreadyExists: true };
    }
  }
  expect(resp.ok(), `register failed: ${resp.status()} ${await resp.text().catch(() => '')}`).toBeTruthy();
  return { alreadyExists: false, user: await resp.json().catch(() => ({})) };
}
