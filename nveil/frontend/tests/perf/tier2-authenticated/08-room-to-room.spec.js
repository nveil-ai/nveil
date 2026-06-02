// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Create a 2nd room, navigate between them, verify no re-download of
// Chat/Viz bundles (SPA cache working).

import { test, expect } from './_fixture.js';
import { assertAuthenticated } from './_fixture.js';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { instrumentNetwork } from '../utils/collect-metrics.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOM_STATE = path.join(__dirname, '..', '.auth', 'room-under-test.json');

test('08 — room-to-room navigation reuses chunks', async ({ sharedPage: page }) => {
  await assertAuthenticated(page);
  expect(fs.existsSync(ROOM_STATE), 'no room available — 05-room-create must run first').toBe(true);
  const { roomToken: room1 } = JSON.parse(fs.readFileSync(ROOM_STATE, 'utf8'));

  // Visit room 1 first to warm caches.
  await page.goto(`/room/${room1}`, { waitUntil: 'load' });
  await page.waitForTimeout(1500);

  // Create a 2nd room. NavBar "+" button is icon-only with data-tooltip.
  await page.goto('/', { waitUntil: 'load' });
  const newRoomBtn = page.locator('button[data-tooltip="New chat"]').first();
  await expect(newRoomBtn, 'new room button should be visible').toBeVisible({ timeout: 10_000 });
  await newRoomBtn.click();
  await page.waitForURL(/\/room\/[^/?#]+/, { timeout: 15_000 });
  const room2 = page.url().match(/\/room\/([^/?#]+)/)?.[1];
  expect(room2, 'should have second room token').toBeTruthy();

  // Now measure: room2 → room1 (back to already-visited room)
  const net = instrumentNetwork(page);
  const t0 = Date.now();
  await page.goto(`/room/${room1}`, { waitUntil: 'load' });
  const elapsed = Date.now() - t0;
  const captured = net.harvest();
  net.detach();

  const chatOrViz = (captured.raw || []).filter(r =>
    /\/assets\/(Chat|Viz)-/.test(r.url) && r.status === 200
  );
  console.log(`Room → Room transition: ${elapsed}ms; Chat/Viz re-fetches: ${chatOrViz.length}`);
  // Some intra-chunk fetches are legitimate (lazy-loaded sub-modules in
  // deep-chat / viz panels). The regression we care about is full-bundle
  // reload, which would be 10+ re-fetches.
  expect(chatOrViz.length, 'Chat/Viz bundles must not fully re-download').toBeLessThanOrEqual(5);
  expect(elapsed, 'Room transition should be SPA-fast').toBeLessThanOrEqual(5000);
});
