#!/usr/bin/env node
// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Static check — fails if the built bundle grew beyond budget.
// Reads dist/ directly, no browser. Runs in ~1 s.
//
// Budget (tune as needed):
//   - main eager chain total:     ≤ 260 KB gzipped   (we're at ~207 KB after recent work)
//   - any single chunk gzipped:   ≤ 500 KB           (keeps individual chunks tractable)
//   - total dist/assets gzipped:  ≤ 1800 KB          (guardrail on overall ship size)
//
// The main-eager-chain is computed by walking from index-*.js through
// static `from "./..."` imports. This is the same graph `measurePage` will
// observe as the landing page's initial load.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..', '..', '..');         // nveil/frontend
const ASSETS = path.join(ROOT, 'dist', 'assets');

const BUDGET_EAGER_GZIP_KB = 260;
const BUDGET_SINGLE_CHUNK_GZIP_KB = 500;
const BUDGET_TOTAL_GZIP_KB = 1800;

if (!fs.existsSync(ASSETS)) {
  console.error(`❌ dist/assets/ missing — run \`npm run build\` first.`);
  process.exit(1);
}

const files = fs.readdirSync(ASSETS);
const jsFiles = files.filter(f => f.endsWith('.js'));
const brFiles = new Set(files.filter(f => f.endsWith('.js.br')));

// Walk main-entry's static-import graph.
const mainJs = jsFiles.find(f => f.startsWith('index-'));
if (!mainJs) {
  console.error(`❌ dist/assets/index-*.js not found`);
  process.exit(1);
}

const eagerChain = new Set();
const queue = [mainJs];
while (queue.length) {
  const f = queue.shift();
  if (eagerChain.has(f)) continue;
  eagerChain.add(f);
  const full = path.join(ASSETS, f);
  if (!fs.existsSync(full)) continue;
  const src = fs.readFileSync(full, 'utf8');
  // Capture static `from"./foo.js"` only (not dynamic import() calls).
  const re = /from\s*['"]\.\/([^'"]+\.js)['"]/g;
  for (const m of src.matchAll(re)) {
    const target = m[1];
    if (!eagerChain.has(target)) queue.push(target);
  }
}

const sizeOf = (f) => {
  const br = `${f}.br`;
  if (brFiles.has(br)) return fs.statSync(path.join(ASSETS, br)).size;
  // Fallback to raw size if .br is missing (shouldn't happen in production build).
  return fs.statSync(path.join(ASSETS, f)).size;
};

const eagerChainBytes = [...eagerChain].reduce((s, f) => s + sizeOf(f), 0);
const totalBytes = jsFiles.reduce((s, f) => s + sizeOf(f), 0);
const largestChunk = jsFiles
  .map(f => ({ f, size: sizeOf(f) }))
  .sort((a, b) => b.size - a.size)[0];

const eagerKB = eagerChainBytes / 1024;
const totalKB = totalBytes / 1024;
const largestKB = largestChunk.size / 1024;

console.log(`Static bundle-budget check (gzipped):`);
console.log(`  eager chain (${eagerChain.size} chunks):  ${eagerKB.toFixed(1)} KB   ` +
            `(budget ${BUDGET_EAGER_GZIP_KB} KB)`);
console.log(`  total /assets/:                       ${totalKB.toFixed(1)} KB   ` +
            `(budget ${BUDGET_TOTAL_GZIP_KB} KB)`);
console.log(`  largest chunk: ${largestChunk.f}  ${largestKB.toFixed(1)} KB   ` +
            `(budget ${BUDGET_SINGLE_CHUNK_GZIP_KB} KB)`);

let failed = 0;
if (eagerKB > BUDGET_EAGER_GZIP_KB) {
  console.error(`❌ EAGER CHAIN OVER BUDGET: ${eagerKB.toFixed(1)} KB > ${BUDGET_EAGER_GZIP_KB} KB`);
  console.error(`   Chain:`, [...eagerChain].join(', '));
  failed++;
}
if (largestKB > BUDGET_SINGLE_CHUNK_GZIP_KB) {
  console.error(`❌ CHUNK OVER BUDGET: ${largestChunk.f} is ${largestKB.toFixed(1)} KB > ${BUDGET_SINGLE_CHUNK_GZIP_KB} KB`);
  failed++;
}
if (totalKB > BUDGET_TOTAL_GZIP_KB) {
  console.error(`❌ TOTAL OVER BUDGET: ${totalKB.toFixed(1)} KB > ${BUDGET_TOTAL_GZIP_KB} KB`);
  failed++;
}

if (failed === 0) console.log(`✓ all budgets OK`);
process.exit(failed > 0 ? 1 : 0);
