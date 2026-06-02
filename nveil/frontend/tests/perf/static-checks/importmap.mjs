#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Static check — fails if any `__V_X__` placeholder survived the build.
// If they did, vendor-version-injector didn't fire for some reason and
// the browser will 404 when trying to fetch e.g. /vendor/plotly-__V_PLOTLY__.mjs.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..', '..', '..');
const INDEX_HTML = path.join(ROOT, 'dist', 'index.html');

if (!fs.existsSync(INDEX_HTML)) {
  console.error(`❌ dist/index.html missing — run \`npm run build\` first.`);
  process.exit(1);
}

const html = fs.readFileSync(INDEX_HTML, 'utf8');
// We only care about unresolved placeholders inside an importmap or src attr,
// not the descriptive comment that explains the syntax.
const stripped = html.replace(/<!--[\s\S]*?-->/g, '');
const matches = [...stripped.matchAll(/__V_[A-Z_]+__/g)];

if (matches.length === 0) {
  console.log(`✓ importmap placeholders all resolved`);
  process.exit(0);
}
const unique = [...new Set(matches.map(m => m[0]))];
console.error(`❌ ${matches.length} unresolved __V_X__ placeholder(s) in dist/index.html:`);
for (const u of unique) console.error(`    ${u}`);
console.error(`\nvendor-version-injector in vite.config.js failed to substitute these.`);
console.error(`Check VENDOR_VERSIONS in vite.config.js and the plugin's transformIndexHtml hook.`);
process.exit(1);
