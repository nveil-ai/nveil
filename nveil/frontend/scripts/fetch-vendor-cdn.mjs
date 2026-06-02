// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

// Self-host heavy viz libraries as ES modules.
//
// At build time, bundle locally-installed packages (plotly) into standalone
// ESM files under public/vendor/. These are served from app.nveil.com through
// Cloudflare's edge — zero third-party runtime dependency, same edge-cache
// latency as a public CDN for far users.
//
// We use Rolldown programmatically (already a transitive dep of rolldown-vite)
// so there's nothing extra to install. No network access at build time —
// everything comes from node_modules.
//
// Scope: ONLY the heavy libs with no React peer dep. React itself plus
// react-plotly.js/factory stay in Vite's normal bundle graph so they use our
// single bundled React instance automatically.
//
// Filenames include the installed version (from package.json) so upgrading
// the npm dep produces a new URL and cache-busts automatically.

import { build } from 'rolldown';
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const VENDOR_DIR = path.join(ROOT, 'public', 'vendor');

const pkgJson = JSON.parse(
  fs.readFileSync(path.join(ROOT, 'package.json'), 'utf8')
);
const deps = { ...pkgJson.dependencies, ...pkgJson.devDependencies };

function v(name) {
  const raw = deps[name];
  if (!raw) throw new Error(`"${name}" missing from package.json`);
  return raw.replace(/^[\^~>=<]+/, '');
}

const PLOTLY = v('plotly.js-dist-min');

// Each entry = one self-contained ESM file in /vendor/. `external` lists
// bare-import specifiers the output should keep as `import ... from "X"` so
// they resolve at runtime through the importmap to OUR other vendor files.
const ENTRIES = [
  // Self-contained — no React, no shared peer deps.
  { entry: 'plotly.js-dist-min', out: `plotly-${PLOTLY}.mjs`, external: [] },
];

async function bundleOne({ entry, out, external }) {
  const outPath = path.join(VENDOR_DIR, out);
  await build({
    input: entry,
    cwd: ROOT,
    platform: 'browser',
    external,
    // Force single-file output even when source has dynamic imports.
    // We want one standalone file per entry for vendor self-hosting.
    output: {
      file: outPath,
      format: 'esm',
      minify: true,
      codeSplitting: false,
    },
    resolve: {
      // Prefer 'browser' conditions in package.json exports.
      conditionNames: ['browser', 'import', 'module', 'default'],
    },
    logLevel: 'warn',
  });

  // Pre-compress: matches how /assets/* are handled via PreCompressedStaticMiddleware.
  // Browsers get .br or .gz based on Accept-Encoding; uncompressed .mjs is the fallback.
  const raw = fs.readFileSync(outPath);
  const gz = zlib.gzipSync(raw, { level: 9 });
  const br = zlib.brotliCompressSync(raw, {
    params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11 },
  });
  fs.writeFileSync(outPath + '.gz', gz);
  fs.writeFileSync(outPath + '.br', br);

  return { raw: raw.length, gz: gz.length, br: br.length };
}

async function main() {
  fs.mkdirSync(VENDOR_DIR, { recursive: true });
  const expected = new Set(ENTRIES.flatMap(e => [e.out, e.out + '.gz', e.out + '.br']));
  const existing = new Set(
    fs.existsSync(VENDOR_DIR) ? fs.readdirSync(VENDOR_DIR) : []
  );

  let built = 0;
  let skipped = 0;
  let failed = 0;
  let totalBytes = 0;

  for (const entry of ENTRIES) {
    const outPath = path.join(VENDOR_DIR, entry.out);
    if (fs.existsSync(outPath) && fs.statSync(outPath).size > 1024) {
      skipped++;
      totalBytes += fs.statSync(outPath).size;
      continue;
    }
    try {
      process.stdout.write(`  bundling ${entry.entry.padEnd(24)} → ${entry.out.padEnd(32)} ... `);
      const sizes = await bundleOne(entry);
      totalBytes += sizes.raw;
      process.stdout.write(
        `${(sizes.raw / 1024).toFixed(1)} KB ` +
        `(br ${(sizes.br / 1024).toFixed(1)} KB) ✓\n`
      );
      built++;
    } catch (e) {
      process.stdout.write(`FAILED\n`);
      console.error(`    ${(e.message || String(e)).split('\n')[0]}`);
      failed++;
    }
  }

  // Clean up stale files from previous builds (version bumps leave old files).
  for (const f of existing) {
    if (!expected.has(f)) {
      fs.unlinkSync(path.join(VENDOR_DIR, f));
      console.log(`  pruned stale ${f}`);
    }
  }

  console.log(
    `\nVendor bundle: ${built} built, ${skipped} cached, ${failed} failed. ` +
    `Total ${(totalBytes / 1024 / 1024).toFixed(2)} MB across ${ENTRIES.length} files.`
  );

  if (failed > 0) {
    console.error('\nERROR: some vendor bundles failed. Aborting build.');
    process.exit(1);
  }
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
