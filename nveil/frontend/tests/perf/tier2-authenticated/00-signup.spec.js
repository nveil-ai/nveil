// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Signup via the real UI — walks the whole RegisterSteps flow end-to-end,
// just like a new user would. NO api-signup fallback: if the UI doesn't
// work, this test fails loudly and the suite stops.
//
// Flow:
//   1. Click NavBar login button (#nav-login) → auth modal opens in login mode
//   2. Click "Sign up here" to switch to register mode
//   3. Step 1 of 3: pick "Personal Use"
//   4. Step 2 of 3: fill first name, last name, email, password → Next
//   5. Step 3 of 3: pick country, fill profession, pick education, accept CGU → Submit
//   6. Assert access_token cookie appears

import { test, expect } from './_fixture.js';
import { BOT } from '../utils/account-lifecycle.js';

test('00 — signup via UI (creates bot account)', async ({ sharedPage: page }) => {
    const t0 = Date.now();

    await page.goto('/', { waitUntil: 'load' });

    // 1. Open the auth modal. The NavBar has a stable id.
    await page.locator('#nav-login').click();

    // 2. Modal opens in login mode — switch to register.
    await page.getByRole('button', { name: /sign up here|s'inscrire ici|cr[ée]er un compte/i })
      .click();

    // 3. Step 1/3: pick "Personal Use".
    await page.getByRole('button', { name: /personal use|usage personnel/i }).click();

    // 4. Step 2/3: identity + credentials.
    const [firstName, lastName] = BOT.name.includes(' ')
      ? BOT.name.split(' ', 2)
      : [BOT.name, 'Bot'];
    await page.locator('input[name="firstName"]').fill(firstName);
    await page.locator('input[name="lastName"]').fill(lastName);
    await page.locator('input[name="email"]').fill(BOT.email);
    await page.locator('input[name="password"]').fill(BOT.password);
    await page.getByRole('button', { name: /^(Next|Suivant)$/i }).click();

    // 5. Step 3/3: country, profession, education, CGU, submit.
    //    country + education are react-select ⇒ role=combobox.
    //    Order rendered on step 3 for personal: [country, education].
    const combos = page.locator('[role="combobox"]:visible');
    await combos.nth(0).click();                                      // open country
    await page.getByRole('option').first().click();                   // pick first country

    await page.locator('input[name="profession"]').fill('QA Engineer');

    await combos.nth(1).click();                                      // open education
    await page.getByRole('option').first().click();                   // pick first level

    // Required checkboxes: acceptCGU + acceptPrivacy (acceptCommunication
    // is optional). react-aria hides the real <input type="checkbox">, so
    // we target the inputs directly with force:true. Can't click the label
    // text because acceptPrivacy's label IS an <a href> — would navigate.
    const checkboxes = page.locator('input[type="checkbox"]');
    await checkboxes.nth(0).check({ force: true });   // acceptCGU
    await checkboxes.nth(1).check({ force: true });   // acceptPrivacy

    // Submit — isLastStep=true ⇒ button label is "Submit".
    await page.getByRole('button', { name: /^(Submit|Envoyer|Valider)$/i }).click();

    // 6. Wait for the session to land. access_token is HttpOnly (set by
    //    authentification.py with httponly=True) so document.cookie can't
    //    see it — we have to poll the context's cookie jar via Playwright.
    await expect.poll(
      async () => {
        const cookies = await page.context().cookies();
        return cookies.some(c => c.name === 'access_token');
      },
      { message: 'access_token cookie never appeared', timeout: 20_000 }
    ).toBe(true);

    const elapsed = Date.now() - t0;
    console.log(`Signup UI flow: ${elapsed}ms`);
    expect(elapsed, 'signup within 30s').toBeLessThanOrEqual(30_000);

    // No need to save storageState — subsequent tests share this same
    // context via the sharedPage fixture, so the session rides along.
});
