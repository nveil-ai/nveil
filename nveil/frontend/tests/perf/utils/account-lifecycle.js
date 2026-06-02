// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Coordinates the bot account lifecycle for a single test-suite invocation.
//
// Contract:
//   - Suite entry: `ensureCleanSlate()` — if a prior bot account exists (from
//     a crashed run), delete it so 00-signup.spec.js starts from zero.
//   - Suite exit: `ensureCleanSlate()` again (afterAll safety net) — deletes
//     the account if any test failed before 10-delete-account.spec.js ran.
//
// Credentials come from env vars. Never hardcoded.

import { request as playwrightRequest } from '@playwright/test';
import { apiLogin } from './api-login.js';
import { apiDeleteAccount } from './api-delete-account.js';

export const BOT = {
  email: process.env.NVEIL_PERF_EMAIL || 'testing-bot@nveil.com',
  password: process.env.NVEIL_PERF_PASSWORD || 'perf-bot-pw-local-only-🤖',
  name: process.env.NVEIL_PERF_NAME || 'Perf Bot',
};

/**
 * Delete the bot account if it exists. Idempotent — safe to call multiple
 * times. Uses a throwaway APIRequestContext (independent of any running
 * browser) so it works in beforeAll/afterAll hooks where no page exists.
 */
export async function ensureCleanSlate(baseURL) {
  const ctx = await playwrightRequest.newContext({
    baseURL,
    ignoreHTTPSErrors: true,
  });
  try {
    let loginResult;
    try {
      loginResult = await apiLogin(ctx, baseURL, BOT.email, BOT.password);
    } catch {
      // Login failed = account doesn't exist (or creds mismatch). Nothing to clean.
      return { cleaned: false, reason: 'login-failed-or-absent' };
    }
    // Re-use the authenticated context for the delete call.
    const delResult = await apiDeleteAccount(ctx, baseURL);
    return { cleaned: delResult.ok, status: delResult.status };
  } finally {
    await ctx.dispose();
  }
}
