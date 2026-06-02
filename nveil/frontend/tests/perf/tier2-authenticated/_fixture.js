// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Shared fixture for Tier 2. All authenticated specs represent ONE user
// session (signup → login → upload → room → chat → logout → delete), so
// they should run on ONE context and ONE page — like a real user.
//
// Why not Playwright's default "fresh context per test"?
//   - Throws away WebSocket connections, React state, open modals, the
//     current room — each spec would have to re-establish all of that.
//   - Cascade-fails: if spec N leaves something inconsistent, spec N+1
//     picks up the carnage instead of its own clean slate.
//   - Slower: 10+ context creations per run.
//
// Why not `test.use({ storageState })` (what we had before)?
//   - Only restores cookies. In-memory state is gone. HttpOnly cookies
//     keep HTTP calls authenticated but WebSocket reconnect logic has to
//     fire each time, and that's what was breaking 05+ after 04.
//
// Pattern: one worker-scoped context with cookieConsent pre-seeded, and
// one worker-scoped page. Auto-fixtures means every spec that does
// `test('...', async ({ sharedPage }) => ...)` inherits the same page.

import { test as base } from '@playwright/test';
import { newPerfContext } from '../utils/new-context.js';

export const test = base.extend({
  sharedCtx: [async ({ browser }, use) => {
    const ctx = await newPerfContext(browser);
    await use(ctx);
    await ctx.close();
  }, { scope: 'worker' }],

  sharedPage: [async ({ sharedCtx }, use) => {
    const page = await sharedCtx.newPage();

    // WS-frame buffer. Playwright's page.on('websocket') only fires for
    // NEW connections created after the listener is registered. The app
    // opens /ws/events during login (first test), so if individual specs
    // registered the listener later they'd never see frames. Register it
    // once at fixture time and stash all received frames for later lookup.
    page.__wsFrames = [];
    page.on('websocket', (ws) => {
      ws.on('framereceived', ({ payload }) => {
        let parsed;
        try { parsed = JSON.parse(payload); } catch { parsed = payload; }
        page.__wsFrames.push({ at: Date.now(), payload: parsed });
      });
    });

    await use(page);
    // Intentionally do NOT close — it persists across specs in the worker.
  }, { scope: 'worker' }],
});

// Call at the start of every authenticated spec (except 00-signup and
// 01-login which handle auth themselves). Verifies the session; if the
// cookies have been invalidated by some earlier test (e.g., chat flow
// triggering a 401 that clears auth), re-login via the API so the
// current spec can still run on its own merits.
import { BOT } from '../utils/account-lifecycle.js';
import { apiLogin } from '../utils/api-login.js';

export async function assertAuthenticated(page) {
  const baseURL = process.env.NVEIL_PERF_URL || 'https://localhost:8000';
  let resp = await page.request.get('/server/auth/me').catch(() => null);
  if (resp && resp.ok()) return;

  // Session lost — self-heal by re-logging in on the shared context.
  // We use apiLogin (form POST) on the page's own request context so the
  // Set-Cookie lands in the BrowserContext cookie jar.
  console.warn('[assertAuthenticated] session lost — re-logging in');
  await apiLogin(page.request, baseURL, BOT.email, BOT.password);
  resp = await page.request.get('/server/auth/me').catch(() => null);
  if (!resp || !resp.ok()) {
    throw new Error(
      `\n\n❌ Re-login failed (GET /server/auth/me → ${resp?.status() ?? 'no response'} after apiLogin).\n` +
      `   The bot account may have been deleted or the credentials changed.\n`
    );
  }
}

export { expect } from '@playwright/test';

