// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Runs ONCE after the whole Playwright suite finishes.
//
// Safety net: if any Tier 2 test crashed before 10-delete-account could run,
// the bot account is still in the DB. We defensively call ensureCleanSlate
// here so the NEXT suite invocation starts with zero prior state.
//
// No failure if cleanup succeeds or if there's nothing to clean.

import { request as playwrightRequest } from '@playwright/test';
import { ensureCleanSlate } from './utils/account-lifecycle.js';

export default async function globalTeardown(config) {
  const baseURL = config.projects[0].use.baseURL || process.env.NVEIL_PERF_URL || 'https://localhost:8000';

  // 1. Bot account cleanup (defensive — usually 10-delete-account already
  //    handled this).
  try {
    const result = await ensureCleanSlate(baseURL);
    if (result.cleaned) {
      console.log(`[globalTeardown] ✓ cleaned up bot account after suite run`);
    } else {
      console.log(`[globalTeardown] ✓ nothing to clean (reason: ${result.reason || 'n/a'})`);
    }
  } catch (err) {
    console.warn(`[globalTeardown] ! account cleanup failed: ${err.message}`);
  }

  // 2. Reset the viz pool. Local stack has a /server/pool/reload endpoint
  //    that kills every viz container and refills to min_size. We use it
  //    to wipe any orphaned/leaked pods at end-of-suite so the next run
  //    starts clean — without this, each run leaves +1 pod behind.
  try {
    const ctx = await playwrightRequest.newContext({ baseURL, ignoreHTTPSErrors: true });
    const resp = await ctx.post('/server/pool/reload', { timeout: 30_000 }).catch(e => e);
    if (resp?.ok && resp.ok()) {
      const body = await resp.json().catch(() => ({}));
      console.log(`[globalTeardown] ✓ pool reloaded (displaced ${body.displaced_sessions ?? 0} sessions)`);
    } else if (resp?.status) {
      console.warn(`[globalTeardown] ! pool reload returned ${resp.status()}`);
    } else {
      console.warn(`[globalTeardown] ! pool reload error: ${resp?.message ?? 'unknown'}`);
    }
    await ctx.dispose();
  } catch (err) {
    console.warn(`[globalTeardown] ! pool reload failed: ${err.message}`);
  }
}
