// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Final test: delete the bot account. Verifies via re-login attempt
// that the account really is gone. Leaves DB clean for the next suite run.

// Import test/expect from _fixture.js so this spec is part of the same
// test group as the rest of tier2 (and runs alphabetically after 09).
// Otherwise it groups with base-test specs and Playwright orders it apart
// from the rest of the lifecycle.
import { request as playwrightRequest } from '@playwright/test';
import { test, expect } from './_fixture.js';
import { BOT } from '../utils/account-lifecycle.js';
import { apiLogin } from '../utils/api-login.js';
import { apiDeleteAccount } from '../utils/api-delete-account.js';

const BASE = process.env.NVEIL_PERF_URL || 'https://localhost:8000';

test('10 — delete bot account + verify deletion', async () => {
  // Re-login via API (09-logout cleared the browser session; we need a
  // fresh auth context for the delete call).
  const ctx = await playwrightRequest.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });
  try {
    await apiLogin(ctx, BASE, BOT.email, BOT.password);

    const t0 = Date.now();
    const result = await apiDeleteAccount(ctx, BASE);
    const elapsed = Date.now() - t0;
    console.log(`Delete-account: ${elapsed}ms (status=${result.status})`);

    expect(result.ok, `delete should succeed: ${JSON.stringify(result.body)}`).toBeTruthy();
    expect(elapsed).toBeLessThanOrEqual(10_000);
  } finally {
    await ctx.dispose();
  }

  // VERIFICATION: subsequent login attempt must fail — account is gone.
  const verify = await playwrightRequest.newContext({ baseURL: BASE, ignoreHTTPSErrors: true });
  try {
    let loginFailed = false;
    try {
      await apiLogin(verify, BASE, BOT.email, BOT.password);
    } catch {
      loginFailed = true;
    }
    expect(loginFailed, 'post-deletion login should FAIL (account gone)').toBeTruthy();
  } finally {
    await verify.dispose();
  }
});

// Safety-net: even if 10-delete-account is skipped (e.g., due to env or
// earlier test failure), the globalTeardown cleans up via account-lifecycle.
// But having this test as the primary teardown means we measure AND assert
// the flow works.
