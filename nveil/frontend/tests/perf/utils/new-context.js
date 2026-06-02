// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Helper for specs that need their own BrowserContext (instead of the
// default `page` fixture). Pre-seeds the `cookieConsent` cookie so the
// in-app CookieBanner never renders — keeps CLS + network noise out of
// cold-load measurements. Also sets ignoreHTTPSErrors (local self-signed
// cert) and locks locale so Chrome's translate prompt never fires.

const BASE_URL = process.env.NVEIL_PERF_URL || 'https://localhost:8000';

export async function newPerfContext(browser, opts = {}) {
  const ctx = await browser.newContext({
    baseURL: BASE_URL,     // ← so page.goto('/') resolves correctly
    ignoreHTTPSErrors: true,
    locale: 'en-US',
    ...opts,
  });
  await ctx.addCookies([{
    name: 'cookieConsent',
    value: 'true',
    url: BASE_URL,
  }]);
  return ctx;
}
