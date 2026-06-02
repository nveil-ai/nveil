// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Specific regression assertions — the exact bugs we hunted manually this project:
//  A) heavy viz libs loaded on landing → SHOULD NOT happen
//  B) two React instances duplicated → SHOULD NOT happen
//  C) unexpected 3rd-party origins beyond our allowlist → alert but don't block

import { test, expect } from '@playwright/test';
import { measurePage } from '../utils/collect-metrics.js';

const FORBIDDEN_PATTERNS_ON_LANDING = [
  /vendor-plotly/,
  /vendor-maplibre/,
  /vendor-deckgl/,
  /vendor-forcegraph/,
  /vendor-kedro/,
  /\/vendor\/plotly-/,
  /\/vendor\/maplibre/,
  /\/vendor\/deckgl/,
];

// Domains we know the landing page calls: analytics, fonts, auth, ad pixels,
// YouTube embeds (from landing content), Google sub-domains spawned by GTM.
// Any origin NOT matching these patterns is flagged as a soft warning (not
// hard-failed) — we might legitimately add one and want to know.
const ALLOWED_THIRD_PARTY_PATTERNS = [
  /^https:\/\/([a-z0-9-]+\.)?googletagmanager\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?google-analytics\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?analytics\.google\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?doubleclick\.net$/,
  /^https:\/\/fonts\.(googleapis|gstatic)\.com$/,
  /^https:\/\/accounts\.google\.com$/,
  /^https:\/\/www\.google\.com$/,
  /^https:\/\/jnn-pa\.googleapis\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?youtube(-nocookie)?\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?ytimg\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?googlevideo\.com$/,
  /^https:\/\/www\.redditstatic\.com$/,
  /^https:\/\/alb\.reddit\.com$/,
  /^https:\/\/pixel-config\.reddit\.com$/,
  /^https:\/\/w3-reporting-nel\.reddit\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?facebook\.(com|net)$/,
  /^https:\/\/([a-z0-9-]+\.)?linkedin\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?licdn\.com$/,
];

test('no heavy viz libs fetched on landing', async ({ page }, testInfo) => {
  const m = await measurePage(page, async () => {
    await page.goto('/', { waitUntil: 'networkidle' });
  });

  const hits = (m.network.raw || []).filter(r =>
    FORBIDDEN_PATTERNS_ON_LANDING.some(p => p.test(r.url))
  );
  await testInfo.attach('network.json', {
    body: JSON.stringify(m.network, null, 2),
    contentType: 'application/json',
  });
  expect(hits, `landing must NOT fetch heavy viz chunks (found ${hits.length})`).toHaveLength(0);
});

test('single React instance (no dup via wrappers)', async ({ page }) => {
  await page.goto('/', { waitUntil: 'load' });
  // Wait for React hydration to commit.
  await page.waitForTimeout(2000);
  const reactInfo = await page.evaluate(() => {
    // Strategy: find the React root container and inspect its fiber. A
    // duplicated React instance shows up as more than one container node
    // whose first child has a __reactContainer$<id> or __reactFiber$<id>
    // attached. Works in production (devtools hook is absent there).
    const allElems = document.querySelectorAll('*');
    const reactContainerIds = new Set();
    const reactFiberIds = new Set();
    for (const el of allElems) {
      for (const key of Object.keys(el)) {
        if (key.startsWith('__reactContainer$')) reactContainerIds.add(key);
        if (key.startsWith('__reactFiber$')) reactFiberIds.add(key);
      }
    }
    return {
      devtoolsHookPresent: typeof window.__REACT_DEVTOOLS_GLOBAL_HOOK__ !== 'undefined',
      devtoolsRenderersCount: window.__REACT_DEVTOOLS_GLOBAL_HOOK__?.renderers?.size ?? null,
      // Each React instance assigns its own unique $id; more than one ID
      // across the DOM = multiple React instances.
      uniqueFiberIds: [...reactFiberIds],
      uniqueContainerIds: [...reactContainerIds],
    };
  });

  // Sanity: React hydrated at all.
  const anyReactPresent = reactInfo.uniqueFiberIds.length > 0 || reactInfo.uniqueContainerIds.length > 0;
  expect(anyReactPresent, 'React should have hydrated the DOM').toBeTruthy();

  // The real regression check: more than one fiber ID means duplicated React.
  // (Each React instance generates a unique random-suffixed prop key.)
  expect(reactInfo.uniqueFiberIds.length, `multiple React instances detected: ${reactInfo.uniqueFiberIds.join(', ')}`).toBeLessThanOrEqual(1);
  expect(reactInfo.uniqueContainerIds.length, `multiple React root containers: ${reactInfo.uniqueContainerIds.join(', ')}`).toBeLessThanOrEqual(1);

  // If the devtools hook IS present (e.g., running with React DevTools installed),
  // use it as a supplementary signal — but don't require it.
  if (reactInfo.devtoolsHookPresent && reactInfo.devtoolsRenderersCount != null) {
    expect(reactInfo.devtoolsRenderersCount, 'exactly one React renderer via devtools hook').toBe(1);
  }
});

test('no unexpected third-party origins', async ({ page }, testInfo) => {
  const m = await measurePage(page, async () => {
    await page.goto('/', { waitUntil: 'networkidle' });
  });
  const originsSeen = Object.keys(m.network.byOrigin || {});
  const unexpected = originsSeen.filter(origin => {
    if (origin === 'unknown') return false;
    try {
      const u = new URL(origin);
      if (u.hostname === 'localhost' || u.hostname.endsWith('.nveil.com') || u.hostname === 'app.nveil.com') return false;
    } catch { return true; }
    return !ALLOWED_THIRD_PARTY_PATTERNS.some(p => p.test(origin));
  });
  await testInfo.attach('origins.json', {
    body: JSON.stringify({ seen: originsSeen, unexpected }, null, 2),
    contentType: 'application/json',
  });
  // Soft signal — log rather than hard-fail. Tighten once we know the full
  // set of expected ad/analytics origins.
  if (unexpected.length) {
    console.warn(`⚠️  unexpected third-party origins: ${unexpected.join(', ')}`);
  }
});

test('no HTTP errors on landing', async ({ page }, testInfo) => {
  const m = await measurePage(page, async () => {
    await page.goto('/', { waitUntil: 'networkidle' });
  });
  const errors = m.network.errors || [];
  await testInfo.attach('errors.json', { body: JSON.stringify(errors, null, 2), contentType: 'application/json' });
  // 3xx redirects are fine; 4xx/5xx are not (apart from the occasional 401 on /server/auth/me before login).
  const hardErrors = errors.filter(e => e.status >= 500 || (e.status >= 400 && !/\/server\/auth\/(me|refresh)/.test(e.url)));
  expect(hardErrors, `hard HTTP errors on landing: ${JSON.stringify(hardErrors)}`).toHaveLength(0);
});
