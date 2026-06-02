#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Static check — asserts that no chunk in the eager landing graph
// statically imports from a heavy-viz vendor chunk.
//
// This catches the exact regression class we fought earlier this project:
//   - a shared utility (prop-types, __vitePreload helper) placed by Rolldown
//     into vendor-plotly / vendor-deckgl, forcing every chunk that needed
//     the utility to statically pull the entire heavy vendor file.
// Detecting it here avoids a full build → browser run → "plotly loaded on
// landing??" investigation cycle.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..', '..', '..');
const ASSETS = path.join(ROOT, 'dist', 'assets');

// Chunks in this list MUST be lazy-only. Any static import of these from
// a chunk in the landing's eager graph = regression.
const FORBIDDEN_IN_EAGER = [
  'vendor-plotly',
  'vendor-maplibre',
  'vendor-deckgl',
  'vendor-forcegraph',
  'vendor-kedro',
];

if (!fs.existsSync(ASSETS)) {
  console.error(`❌ dist/assets/ missing — run \`npm run build\` first.`);
  process.exit(1);
}

const files = fs.readdirSync(ASSETS).filter(f => f.endsWith('.js'));
const mainJs = files.find(f => f.startsWith('index-'));
if (!mainJs) {
  console.error(`❌ dist/assets/index-*.js not found`);
  process.exit(1);
}

// Walk the eager static-import graph starting from index-*.js
const eagerChain = new Set();
const queue = [mainJs];
while (queue.length) {
  const f = queue.shift();
  if (eagerChain.has(f)) continue;
  eagerChain.add(f);
  const full = path.join(ASSETS, f);
  const src = fs.readFileSync(full, 'utf8');
  const re = /from\s*['"]\.\/([^'"]+\.js)['"]/g;
  for (const m of src.matchAll(re)) {
    const target = m[1];
    if (!eagerChain.has(target)) queue.push(target);
  }
}

// Now, for each eager chunk, check if it statically imports a forbidden one.
const violations = [];
for (const f of eagerChain) {
  const src = fs.readFileSync(path.join(ASSETS, f), 'utf8');
  for (const forbidden of FORBIDDEN_IN_EAGER) {
    // Match `from "./vendor-plotly-HASH.js"` etc.
    const re = new RegExp(`from\\s*['"]\\.\\/${forbidden}-[^'"]+['"]`, 'g');
    for (const m of src.matchAll(re)) {
      violations.push({ chunk: f, importing: m[0] });
    }
  }
}

console.log(`Static import-graph check (eager chain = ${eagerChain.size} chunks):`);
if (violations.length === 0) {
  console.log(`✓ no forbidden heavy-vendor imports in eager chain`);
  process.exit(0);
}

console.error(`❌ ${violations.length} forbidden imports found in eager landing chain:\n`);
for (const v of violations) {
  console.error(`  ${v.chunk}:`);
  console.error(`    ${v.importing}`);
}
console.error(`\nThese heavy vendors MUST stay lazy-only — pulling them eagerly on landing`);
console.error(`reverts the chunking work. If intentional, move the import behind a lazy()`);
console.error(`boundary or tighten the codeSplitting rules in vite.config.js.`);
process.exit(1);
