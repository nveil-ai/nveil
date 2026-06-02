// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import viteCompression from 'vite-plugin-compression2';
import Sitemap from 'vite-plugin-sitemap';
import { visualizer } from 'rollup-plugin-visualizer';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// Read installed versions from package.json so the importmap in index.html
// can reference versioned /vendor/*.mjs filenames produced by
// scripts/fetch-vendor-cdn.mjs. The plugin below substitutes __V_X__
// placeholders at build + dev time.
const _pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8'));
const _v = (name) => (_pkg.dependencies[name] || _pkg.devDependencies[name]).replace(/^[\^~>=<]+/, '');
const VENDOR_VERSIONS = {
  V_PLOTLY: _v('plotly.js-dist-min'),
};

const vendorVersionInjector = {
  name: 'vendor-version-injector',
  transformIndexHtml(html) {
    return html.replace(/__V_[A-Z_]+__/g, (match) => {
      const key = match.slice(2, -2);
      return VENDOR_VERSIONS[key] ?? match;
    });
  },
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(),
  vendorVersionInjector,
  // gzip + brotli pre-compression (served by PreCompressedStaticMiddleware)
  viteCompression({ algorithm: 'gzip' }),
  viteCompression({ algorithm: 'brotliCompress' }),
  Sitemap({
    hostname: 'https://app.nveil.com',
    dynamicRoutes: ['/explore', '/feedback'],
    robots: [
      { userAgent: '*', allow: '/', disallow: ['/viz/', '/server/', '/cdn-cgi/', '/room/', '/dashboard/'] },
      { userAgent: 'GPTBot', allow: '/' },
      { userAgent: 'CCBot', allow: '/' },
      { userAgent: 'Google-Extended', allow: '/' },
    ],
  }),
  visualizer({ filename: 'dist/stats.html', template: 'treemap', gzipSize: true, brotliSize: true }),
  ],

  resolve: {
    alias: {
      '@nveil/app': path.resolve(import.meta.dirname, 'src'),
    },
    preserveSymlinks: true,
  },

  build: {
    sourcemap: false,
    target: 'esnext',
    chunkSizeWarningLimit: 5000,
    // Vite 8 uses Oxc natively for JS minify — no terser needed
    minify: true,
    cssCodeSplit: true,
    modulePreload: {
      // Don't modulepreload heavy lazy-only chunks — they inflate TBT on initial load
      resolveDependencies: (filename, deps) => {
        return deps.filter(dep =>
          !dep.includes('vendor-forcegraph') &&
          !dep.includes('vendor-plotly') &&
          !dep.includes('vendor-kedro')
          // Note: vendor-viz-core is NOT filtered because main statically
          // imports __vitePreload helper from it; preloading helps parallelize.

        );
      },
    },
    rolldownOptions: {
      // Self-hosted vendors — the browser fetches these from /vendor/ at
      // runtime via the importmap in index.html. Built by scripts/fetch-vendor-cdn.mjs
      // which bundles each package from node_modules into a standalone ESM
      // file (no third-party runtime CDN).
      //
      // Only libs with NO React peer are externalized here. React itself
      // plus React-using wrappers (react-plotly.js/factory) stay in Vite's
      // normal bundle so they share the single bundled React instance.
      external: [
        'plotly.js-dist-min',
        ...(process.env.NVEIL_CLOUD ? [] : ['@nveil/cloud-frontend']),
      ],
      output: {
        // No manual chunking — Rolldown's default produces 3x smaller eager
        // load than hand-crafted groups (651 KB vs 2 MB previously), because
        // the default isolates __vitePreload into a tiny dedicated chunk and
        // keeps shared utilities out of heavy vendor chunks.
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/server': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false,
        ws: true,
      },
      '/api': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/oauth': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/viz': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/assets': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    }
  },
})
