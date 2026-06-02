// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Direct DELETE /server/auth/delete-account — called by 10-delete-account.spec.js
// as the main functional assertion AND by account-lifecycle.js as a safety-net
// teardown if tests fail before reaching the UI-driven deletion step.
//
// The backend endpoint (authentification.py::delete_account) requires an
// authenticated session (cookies).

/**
 * @param {import('@playwright/test').APIRequestContext} request
 *        must already have the bot's cookies (e.g., returned by apiLogin).
 * @param {string} baseURL
 * @returns {Promise<{ok: boolean, status: number, body: any}>}
 */
export async function apiDeleteAccount(request, baseURL) {
  const resp = await request.delete(`${baseURL}/server/auth/delete-account`, {
    ignoreHTTPSErrors: true,
  });
  return {
    ok: resp.ok(),
    status: resp.status(),
    body: await resp.json().catch(() => ({})),
  };
}
