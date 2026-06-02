// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Open the room created in 05 and verify it actually became operational.
//
// "Room operational" is checked via three observable markers:
//   1. /server/room/start returns 200 (pod allocated, no 404/500)
//   2. The Chat panel renders (DeepChat web component mounted)
//   3. The Viz iframe got a src set (means startRoom flow finished)
//
// This is more reliable than waiting for a specific WS event — `viz_ready`
// fires on pod first-boot, `viz_loaded` only after AI builds a viz, and
// pod context-switches don't always re-emit either. The visible state is
// the real "room is loaded" criterion.

import { test, expect } from './_fixture.js';
import { assertAuthenticated } from './_fixture.js';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOM_STATE = path.join(__dirname, '..', '.auth', 'room-under-test.json');

test('06 — open room', async ({ sharedPage: page }) => {
  await assertAuthenticated(page);
  expect(fs.existsSync(ROOM_STATE), 'no room created — 05-room-create must run first').toBe(true);
  const { roomToken } = JSON.parse(fs.readFileSync(ROOM_STATE, 'utf8'));

  // 05's client-side navigation already landed on /room/{token}. If the
  // page is already there with the room running, just verify and don't
  // burn a full reload. Otherwise navigate fresh ("cold open" path).
  const expectedPath = `/room/${roomToken}`;
  const alreadyOnRoom = page.url().endsWith(expectedPath);

  let startResp = null;
  const t0 = Date.now();

  if (!alreadyOnRoom) {
    const startRoomPromise = page.waitForResponse(
      r => /\/server\/room\/start/.test(r.url()) && r.request().method() === 'POST',
      { timeout: 30_000 }
    );
    await page.goto(expectedPath, { waitUntil: 'load' });
    startResp = await startRoomPromise;
  }
  const elapsed = Date.now() - t0;

  // 1. Server allocated the pod successfully (only checked when we did
  //    a cold reload — if we reused the page from 05, start_room already
  //    fired during that test).
  if (startResp) {
    expect(startResp.status(), `start_room should return 200; got ${startResp.status()}`).toBe(200);
  }

  // 2. Chat panel rendered.
  await expect(
    page.locator('[class*="chat" i], [class*="deep-chat" i]').first(),
    'chat panel should render',
  ).toBeVisible({ timeout: 10_000 });

  // 3. Viz iframe got a src — means startRoom completed and set iframeSrc.
  await expect(
    page.locator('iframe[src*="/viz/app/"]'),
    'viz iframe should have a src pointing at /viz/app/',
  ).toHaveCount(1, { timeout: 10_000 });

  console.log(`Room open → operational: ${elapsed}ms`);
  expect(elapsed, 'room open should complete within 30 s').toBeLessThanOrEqual(30_000);
});
