// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Create a room from the authenticated UI — measure API call + navigation.

import { test, expect } from './_fixture.js';
import { assertAuthenticated } from './_fixture.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOM_STATE = path.join(__dirname, '..', '.auth', 'room-under-test.json');

test('05 — create room', async ({ sharedPage: page }) => {
  await assertAuthenticated(page);
  await page.goto('/', { waitUntil: 'load' });

  // The NavBar "+" new-room button is an icon-only <button> with
  // data-tooltip=t("nav.newRoom"). No accessible name, so match the
  // tooltip attribute directly.
  const newRoomBtn = page.locator('button[data-tooltip="New chat"]').first();
  await expect(newRoomBtn, 'new room button should be visible').toBeVisible({ timeout: 10_000 });

  const t0 = Date.now();
  // Watch for the /server/rooms/create response so we can grab the room_id —
  // some downstream tests (e.g., file-linking, dashboards) need the id, not
  // just the URL token.
  const createRespPromise = page.waitForResponse(
    r => /\/server\/rooms\/create/.test(r.url()) && r.request().method() === 'POST',
    { timeout: 10_000 }
  );

  await newRoomBtn.click();

  const createResp = await createRespPromise;
  const createBody = await createResp.json().catch(() => ({}));
  const roomId = createBody.id;
  const roomTokenFromApi = createBody.token;

  // Wait for the URL to settle on the new room.
  await page.waitForURL(/\/room\/[^/?#]+/i, { timeout: 15_000 });
  const url = page.url();
  const roomTokenFromUrl = url.match(/\/room\/([^/?#]+)/i)?.[1];
  expect(roomTokenFromUrl, 'should extract room token from URL').toBeTruthy();
  expect(roomId, 'create-response should include the room id').toBeTruthy();

  // Use the API-response values as authoritative — the URL token may
  // belong to a stale in-flight create response otherwise.
  const roomToken = roomTokenFromApi;

  const elapsed = Date.now() - t0;
  console.log(`Room create → /room/:token redirect: ${elapsed}ms (token=${roomToken}, id=${roomId})`);
  expect(elapsed, 'create-room click → redirect should be < 5s').toBeLessThanOrEqual(5000);

  // Persist token + id for subsequent tests (06-room-open, 07-viz, etc).
  fs.writeFileSync(ROOM_STATE, JSON.stringify({ roomToken, roomId, createdAt: Date.now() }));
});
