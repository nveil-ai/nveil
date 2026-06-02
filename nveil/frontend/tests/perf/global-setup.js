// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Runs ONCE before the whole Playwright suite.
//
// Two jobs:
//   1. Stack-health check — confirm the local backend is reachable
//      (GET /server/auth/csrf). Fail fast with a friendly message if
//      the user forgot `make up-perf`.
//   2. Clean-slate the bot account — if a prior run crashed before
//      10-delete-account.spec.js, the account lingers in DB and
//      00-signup.spec.js would collide with "Email already registered".
//      We delete it here defensively so the suite always starts clean.
//
// NO authentication happens here. Signup is the first test in Tier 2.

import { request } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureCleanSlate } from './utils/account-lifecycle.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default async function globalSetup(config) {
  const baseURL = config.projects[0].use.baseURL || process.env.NVEIL_PERF_URL || 'https://localhost:8000';

  // Ensure results/ exists (Playwright writes reports here; non-fatal if it doesn't yet).
  fs.mkdirSync(path.join(__dirname, 'results'), { recursive: true });
  // Ensure .auth/ exists for storage state files tests will write later.
  fs.mkdirSync(path.join(__dirname, '.auth'), { recursive: true });

  // --- 1. Stack-health check ---
  let attempts = 0;
  const maxAttempts = 5;
  const ctx = await request.newContext({ baseURL, ignoreHTTPSErrors: true });
  while (attempts < maxAttempts) {
    try {
      const resp = await ctx.get('/server/auth/csrf', { timeout: 3000 });
      if (resp.ok()) {
        const body = await resp.json().catch(() => null);
        if (body && body.csrfToken) break;
      }
    } catch {}
    attempts++;
    if (attempts >= maxAttempts) {
      await ctx.dispose();
      throw new Error(
        `\n\n❌ Stack not reachable at ${baseURL}/server/auth/csrf.\n` +
        `   Run \`make up-perf\` from the repo root first.\n` +
        `   (That sets AUTH_TEST_EMAILS so signup can auto-confirm test accounts.)\n`
      );
    }
    await new Promise(r => setTimeout(r, 1000));
  }
  console.log(`[globalSetup] ✓ stack reachable at ${baseURL}`);

  // --- 2. Clean-slate any leftover bot account ---
  try {
    const cleanup = await ensureCleanSlate(baseURL);
    if (cleanup.cleaned) {
      console.log(`[globalSetup] ✓ deleted leftover bot account from prior run`);
    } else {
      console.log(`[globalSetup] ✓ no leftover bot account (reason: ${cleanup.reason || 'n/a'})`);
    }
  } catch (err) {
    console.warn(`[globalSetup] ! clean-slate attempt failed: ${err.message}`);
    // Non-fatal — 00-signup will fail with a useful error if the account still exists.
  }

  await ctx.dispose();
}
