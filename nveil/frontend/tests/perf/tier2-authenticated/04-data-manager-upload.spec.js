// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Upload a small CSV via the DataManager UI — walks the real user flow:
//   1. Navigate to /data
//   2. Click "Upload Files" in the toolbar → modal opens (this also clears
//      pendingFiles, so we must open the modal BEFORE attaching the file)
//   3. Attach the CSV to the hidden <input type="file"> (ref=fileInputRef)
//   4. Click the modal's submit button → POST /server/data/upload
//   5. Watch for the upload response + poll /server/data/list

import { test, expect } from './_fixture.js';
import { assertAuthenticated } from './_fixture.js';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.join(__dirname, '..', 'fixtures', 'sample-small.csv');

test('04 — upload sample CSV via DataManager', async ({ sharedPage: page }) => {
  await assertAuthenticated(page);
  await page.goto('/data', { waitUntil: 'load' });

  // 1. Open the upload modal. Button contains <MdCloudUpload /> + text
  //    "Upload Files". Accessible name of icon+text buttons may merge the
  //    two — match loosely on "upload".
  const openBtn = page.getByRole('button', { name: /upload/i }).first();
  await expect(openBtn, 'upload button visible in toolbar').toBeVisible({ timeout: 10_000 });
  await openBtn.click();

  // Modal rendered → footer visible.
  await page.locator('[class*="modalFooter" i]').waitFor({ timeout: 5000 });

  // 2. Attach the file to the hidden <input type="file">.
  await page.locator('input[type="file"]').first().setInputFiles(FIXTURE);

  // 3. Click the modal's submit button — last button in modalFooter.
  const t0 = Date.now();
  const uploadRespPromise = page.waitForResponse(
    r => /\/server\/data\/upload/.test(r.url()) && r.request().method() === 'POST',
    { timeout: 30_000 }
  );
  await page.locator('[class*="modalFooter" i] button').last().click();
  const uploadResp = await uploadRespPromise;
  expect(uploadResp.status(), 'upload POST should return 2xx')
    .toBeGreaterThanOrEqual(200);
  expect(uploadResp.status()).toBeLessThan(300);

  // 4. Poll /server/data/list until file's processing_status is not 'processing'.
  await expect.poll(async () => {
    const resp = await page.request.get('/server/data/list').catch(() => null);
    if (!resp || !resp.ok()) return false;
    const body = await resp.json().catch(() => null);
    if (!body) return false;
    // File-service response: files[].original_name / display_name (no "name" field).
    const match = (body.files || []).find(f =>
      (f.original_name || f.display_name || '').includes('sample-small')
    );
    return !!match && match.processing_status !== 'processing';
  }, {
    message: 'uploaded file never reached a non-processing status',
    timeout: 60_000,
    intervals: [500, 1000, 2000, 4000],
  }).toBe(true);

  const elapsed = Date.now() - t0;
  console.log(`Upload + processing: ${elapsed}ms`);
  expect(elapsed, 'upload should finish within 60s for a 213-byte CSV').toBeLessThanOrEqual(60_000);
});
