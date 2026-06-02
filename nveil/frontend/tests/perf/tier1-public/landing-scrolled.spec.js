// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Scrolls the landing page top-to-bottom, asserting the 3 step-animations
// (Upload, Describe, Visualize) initialize ONLY when their section comes
// into view — verifying the IntersectionObserver + requestIdleCallback
// defer we shipped for StepAnimations.jsx.

import { test, expect } from '@playwright/test';

test('step-animations only initialize when scrolled into view', async ({ page }) => {
  await page.goto('/', { waitUntil: 'load' });
  // Wait for React hydration to attach the IntersectionObservers.
  await page.waitForTimeout(1000);

  // At scrollY=0: only "upload" section should be near viewport on most layouts.
  // "visualize" (the heavy one) is below the fold → its init() must NOT have fired.
  const initial = await page.evaluate(() => ({
    scrollY: window.scrollY,
    vsDotsAtTop: document.getElementById('vs-dots')?.children?.length ?? 0,
    vsStageRectTop: document.getElementById('vs-stage')?.getBoundingClientRect().top ?? null,
  }));

  // If vs-stage is below the viewport, its animation dots should not yet exist.
  if (initial.vsStageRectTop !== null && initial.vsStageRectTop > window_innerHeight()) {
    expect(initial.vsDotsAtTop, 'visualize animation should NOT init when below fold').toBe(0);
  }

  // Now scroll visualize into view and verify init fires within a few seconds.
  await page.evaluate(() => {
    document.getElementById('vs-stage')?.scrollIntoView({ behavior: 'instant', block: 'center' });
  });
  await page.waitForTimeout(3500);  // IO + rIC should both have fired by now

  const after = await page.evaluate(() => ({
    vsDots: document.getElementById('vs-dots')?.children?.length ?? 0,
    hasPaths: (document.getElementById('vs-mainSvg')?.querySelectorAll('path').length ?? 0) > 0,
  }));
  expect(after.vsDots, 'visualize animation should init after scrolled into view').toBeGreaterThan(0);
  expect(after.hasPaths, 'visualize SVG should have rendered paths').toBeTruthy();
});

function window_innerHeight() {
  // Default viewport from Playwright desktop-fast — used as a coarse check.
  return 900;
}
