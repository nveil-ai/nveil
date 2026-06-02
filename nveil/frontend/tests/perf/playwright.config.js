// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Playwright config for NVEIL synthetic perf + functional test suite.
//
// Targets the LOCAL Docker Compose stack by default (https://localhost:8000).
// Bring it up with `make up-perf` (sets AUTH_TEST_EMAILS so signup auto-confirms).
//
// Environment flags:
//   HEADED=1         → visible browser (watch cursor move)
//   SLOWMO=500       → delay ms between Playwright actions (for debugging)
//   TRACE=1          → force-record trace for every test (for deep debugging)
//   NVEIL_PERF_URL   → override base URL (e.g., point at staging)

import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.NVEIL_PERF_URL || 'https://localhost:8000';

// Pre-seed the cookie that CookieBanner.jsx checks. Without this, a fresh
// Playwright context shows the banner → layout shift (hurts CLS) + extra
// GTM traffic. Value 'true' = consent granted; same effect as a returning
// user who clicked accept.
const SEEDED_STATE = {
  cookies: [{
    name: 'cookieConsent',
    value: 'true',
    domain: new URL(BASE_URL).hostname,
    path: '/',
    expires: Math.floor(Date.now() / 1000) + 31536000,
    httpOnly: false,
    secure: true,
    sameSite: 'Lax',
  }],
  origins: [],
};

export default defineConfig({
  testDir: '.',
  testMatch: ['**/*.spec.js'],

  // Stack-health check + clean-slate bot account before the whole suite.
  globalSetup: './global-setup.js',
  // Safety-net clean-slate in case any Tier 2 test failed before 10-delete-account.
  globalTeardown: './global-teardown.js',

  // Serial — perf measurements mustn't fight each other for CPU.
  workers: 1,

  // Most tests are 10-30 s; room-open + chat-send can be much longer
  // (Trame iframe startup, AI response). Generous cap.
  timeout: 180_000,

  // No retries — a flaky perf test is a signal, not noise.
  retries: 0,

  reporter: [
    ['list'],
    ['json', { outputFile: 'results/perf-latest.json' }],
    ['html', { outputFolder: 'results/html', open: 'never' }],
  ],

  use: {
    baseURL: BASE_URL,
    // Local stack uses a self-signed cert for https://localhost:8000.
    ignoreHTTPSErrors: true,
    // Lock the browser locale to en-US so Chrome never offers to translate
    // the page (the translate prompt can steal focus and perturb INP).
    locale: 'en-US',
    // Visible browser + slow-motion driven by env for interactive debugging.
    headless: process.env.HEADED !== '1',
    launchOptions: {
      slowMo: Number(process.env.SLOWMO) || 0,
      args: [
        // Kill the auto-translate popup + related UI.
        '--disable-features=Translate,TranslateUI,AutofillServerCommunication',
        '--lang=en-US',
      ],
    },
    // Pre-seed cookieConsent so the in-app CookieBanner never appears.
    // Applies to the default `page` fixture. Specs that do their own
    // `browser.newContext()` should pass `{ storageState: SEEDED_STATE }`
    // or call addCookies() with the same cookie.
    storageState: SEEDED_STATE,
    // Always keep a trace when a test fails — retries is 0 so the default
    // 'on-first-retry' would produce nothing. 'retain-on-failure' means
    // every red test has a .zip you can open with `show-trace`.
    trace: process.env.TRACE === '1' ? 'on' : 'retain-on-failure',
    // Video is heavy + redundant with trace. Screenshots on failure are cheap.
    video: 'off',
    screenshot: 'only-on-failure',
    // Don't follow redirects automatically so tests can assert redirect behavior.
    // (Playwright's default is to follow.)
  },

  projects: [
    // Default — fast desktop, no throttling. Authenticated flows + full
    // functional coverage run here. Tier 1 runs here too for the upper-bound
    // numbers.
    {
      name: 'desktop-fast',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
      },
    },
    // Throttled projects disabled until their budgets are recalibrated —
    // desktop-fast budgets time out under 4× CPU. Re-enable once we split
    // BUDGETS per project.
    // {
    //   name: 'desktop-4x-slow',
    //   testIgnore: /tier2-authenticated/,
    //   use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    // },
    // {
    //   name: 'mobile-slow-4g',
    //   testIgnore: /tier2-authenticated/,
    //   use: { ...devices['iPhone 13'] },
    // },
  ],
});
