// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Click the first showcase card and measure chart open/paint latency.

import { test, expect } from '@playwright/test';

test('clicking showcase card opens modal + renders chart', async ({ page }) => {
  await page.goto('/explore', { waitUntil: 'networkidle' });

  // ShowcaseCard renders as <button> containing <h3 class={cardTitle}>.
  // Targeting the <h3> child is robust across CSS-module hash changes
  // (CSS modules produce class names like `_card_abc123` — neither
  // "showcaseCard" nor "Showcase" appears literally in the DOM).
  const firstCard = page.locator('button:has(h3)').first();
  await expect(firstCard, 'a showcase card button should be present').toBeVisible({ timeout: 10_000 });

  const t0 = Date.now();
  await firstCard.click();

  // Wait for either an SVG plot (plotly) or canvas (deckgl) inside the modal.
  await page.waitForFunction(() => {
    const modal = document.querySelector('[role="dialog"], [class*="modal" i]');
    if (!modal) return false;
    return !!(modal.querySelector('svg, canvas, div.plot-container, .deckgl-canvas'));
  }, { timeout: 15_000 });

  const elapsed = Date.now() - t0;
  console.log(`Showcase card → chart paint: ${elapsed}ms`);
  expect(elapsed, 'chart should render within 15s').toBeLessThanOrEqual(15_000);
});
