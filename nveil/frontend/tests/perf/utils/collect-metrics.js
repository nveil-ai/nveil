// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// The "measure everything" helper. Injects instrumentation into a page,
// collects Web Vitals + long tasks + network + JS/CSS coverage + memory,
// returns structured JSON a test can assert on AND ship to the baseline
// comparator.
//
// Usage pattern:
//
//   test('landing', async ({ page }) => {
//     const m = await measurePage(page, async () => {
//       await page.goto('/', { waitUntil: 'load' });
//       // optional: scroll, click, whatever
//     });
//     expect(m.vitals.lcp).toBeLessThan(2500);
//     await testInfo.attach('metrics.json', { body: JSON.stringify(m), contentType: 'application/json' });
//   });
//
// The instrumentation runs inside the page (PerformanceObserver, web-vitals).
// All aggregation happens in Playwright (network, coverage).

/**
 * Inject Web Vitals + Long Tasks observers into every page before navigation.
 * Called once per test via `await installInstrumentation(page)`.
 *
 * We use PerformanceObserver directly (not the web-vitals lib) because the
 * lib defers many callbacks until page hide/unload, which automated tests
 * don't naturally trigger. Direct observation gives us live values we can
 * read mid-page without tricks.
 */
export async function installInstrumentation(page) {
  await page.addInitScript(() => {
    window.__nveilPerf = {
      vitals: {},
      longTasks: [],
      memoryBefore: null,
      memoryAfter: null,
    };

    // TTFB — navigation timing, synchronous once nav commits.
    try {
      const upd = () => {
        const n = performance.getEntriesByType('navigation')[0];
        if (n) window.__nveilPerf.vitals.ttfb = Math.round(n.responseStart);
      };
      addEventListener('load', upd, { once: true });
      upd();
    } catch {}

    // FCP — first "contentful" paint, fires once.
    try {
      const obs = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          if (e.name === 'first-contentful-paint') {
            window.__nveilPerf.vitals.fcp = Math.round(e.startTime);
          }
        }
      });
      obs.observe({ type: 'paint', buffered: true });
    } catch {}

    // LCP — keeps updating until user input; we take the latest candidate.
    try {
      const obs = new PerformanceObserver((list) => {
        const entries = list.getEntries();
        const last = entries[entries.length - 1];
        if (last) window.__nveilPerf.vitals.lcp = Math.round(last.startTime);
      });
      obs.observe({ type: 'largest-contentful-paint', buffered: true });
    } catch {}

    // CLS — sum layout-shift values (Chromium's definition; same as web-vitals).
    try {
      let cls = 0;
      const obs = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          if (!e.hadRecentInput) cls += e.value;
        }
        window.__nveilPerf.vitals.cls = Math.round(cls * 10000) / 10000;
      });
      obs.observe({ type: 'layout-shift', buffered: true });
    } catch {}

    // INP (approximation) — biggest interaction delay. Requires user
    // interactions to produce values; most tests won't hit it so this
    // stays null unless the test simulates input.
    try {
      let maxInp = 0;
      const obs = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          if (e.duration > maxInp) maxInp = e.duration;
        }
        if (maxInp > 0) window.__nveilPerf.vitals.inp = Math.round(maxInp);
      });
      obs.observe({ type: 'event', buffered: true, durationThreshold: 40 });
    } catch {}

    // Long tasks — basis for TBT.
    try {
      const obs = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          window.__nveilPerf.longTasks.push({
            start: Math.round(entry.startTime),
            duration: Math.round(entry.duration),
            name: entry.name,
            attr: entry.attribution?.[0]?.containerSrc
               || entry.attribution?.[0]?.containerName
               || 'main',
          });
        }
      });
      obs.observe({ type: 'longtask', buffered: true });
    } catch {}

    // Memory snapshot at pageshow.
    if (performance?.memory) {
      window.__nveilPerf.memoryBefore = {
        used: performance.memory.usedJSHeapSize,
        total: performance.memory.totalJSHeapSize,
      };
    }
  });
}

// Memoized web-vitals loader. Uses the IIFE bundle (designed for
// script-tag injection) that exposes everything via window.webVitals.
let _webVitalsCache = null;
async function getWebVitalsInitScript() {
  if (_webVitalsCache) return _webVitalsCache;
  const { readFileSync } = await import('node:fs');
  const { fileURLToPath } = await import('node:url');
  const { dirname, resolve } = await import('node:path');
  const here = dirname(fileURLToPath(import.meta.url));
  const wvPath = resolve(here, '..', '..', '..', 'node_modules', 'web-vitals', 'dist', 'web-vitals.iife.js');
  const wvSource = readFileSync(wvPath, 'utf8');
  _webVitalsCache = `
    ${wvSource}
    (() => {
      const wv = window.webVitals;
      if (!wv) return;
      const store = (name) => (metric) => {
        window.__nveilPerf.vitals[name] = Math.round(metric.value * 100) / 100;
      };
      try { wv.onLCP(store('lcp'),   { reportAllChanges: true }); } catch {}
      try { wv.onFCP(store('fcp'));                                } catch {}
      try { wv.onCLS(store('cls'),   { reportAllChanges: true }); } catch {}
      try { wv.onINP(store('inp'));                                } catch {}
      try { wv.onTTFB(store('ttfb'));                              } catch {}
    })();
  `;
  return _webVitalsCache;
}

/**
 * Instrument network interception on a page. Returns a harvester fn that
 * produces the breakdown. Must be installed BEFORE navigation.
 */
export function instrumentNetwork(page) {
  const requests = [];
  const onRequest = (request) => {
    requests.push({ url: request.url(), method: request.method(), startedAt: Date.now(), response: null });
  };
  const onResponse = async (response) => {
    const req = requests.find(r => r.url === response.url() && r.response === null);
    if (!req) return;
    let bodyLen = null;
    try {
      const hdr = response.headers();
      bodyLen = hdr['content-length'] ? Number(hdr['content-length']) : null;
      req.response = {
        status: response.status(),
        cfCache: hdr['cf-cache-status'] || null,
        contentType: hdr['content-type'] || null,
        contentEncoding: hdr['content-encoding'] || null,
        transferSize: bodyLen,
      };
    } catch {}
  };
  page.on('request', onRequest);
  page.on('response', onResponse);

  return {
    detach() {
      page.off('request', onRequest);
      page.off('response', onResponse);
    },
    harvest() {
      const byOrigin = {};
      const byType = {};
      const byStatus = {};
      let totalTransfer = 0;
      let errors = [];
      for (const r of requests) {
        const u = safeUrl(r.url);
        const origin = u?.origin || 'unknown';
        byOrigin[origin] = (byOrigin[origin] || 0) + 1;
        const resp = r.response;
        if (resp) {
          const statusClass = `${Math.floor(resp.status / 100)}xx`;
          byStatus[statusClass] = (byStatus[statusClass] || 0) + 1;
          if (resp.status >= 400) errors.push({ url: r.url, status: resp.status });
          if (resp.transferSize) totalTransfer += resp.transferSize;
          const typeKey = (resp.contentType || '').split(';')[0] || 'unknown';
          byType[typeKey] = (byType[typeKey] || 0) + 1;
        }
      }
      return {
        total: requests.length,
        totalTransferBytes: totalTransfer,
        byOrigin,
        byType,
        byStatus,
        errors: errors.slice(0, 20),
        raw: requests.map(r => ({ url: r.url, status: r.response?.status, size: r.response?.transferSize })),
      };
    },
  };
}
function safeUrl(u) { try { return new URL(u); } catch { return null; } }

/**
 * Start JS + CSS coverage before navigation. Returns a harvester that
 * computes % unused per chunk.
 */
export async function instrumentCoverage(page) {
  await page.coverage.startJSCoverage({ resetOnNavigation: false });
  await page.coverage.startCSSCoverage({ resetOnNavigation: false });
  return {
    async harvest() {
      const js = await page.coverage.stopJSCoverage();
      const css = await page.coverage.stopCSSCoverage();
      const summarize = (entries) => entries.map(entry => {
        const text = entry.text || '';
        const totalBytes = Buffer.byteLength(text, 'utf8');
        let usedBytes = 0;
        for (const fn of entry.functions || []) {
          for (const range of fn.ranges || []) {
            if (range.count > 0) usedBytes += range.endOffset - range.startOffset;
          }
        }
        // CSS has a different shape (ranges live at entry-level).
        for (const range of entry.ranges || []) {
          usedBytes += range.end - range.start;
        }
        return {
          url: entry.url,
          totalBytes,
          usedBytes: Math.min(usedBytes, totalBytes),
          unusedPct: totalBytes > 0 ? Math.round(((totalBytes - usedBytes) / totalBytes) * 1000) / 10 : null,
        };
      });
      return { js: summarize(js), css: summarize(css) };
    },
  };
}

/**
 * High-level runner: install all instrumentation, run the user's action,
 * collect everything, return structured metrics.
 */
export async function measurePage(page, action, { waitAfterMs = 1500, withCoverage = false } = {}) {
  await installInstrumentation(page);
  const net = instrumentNetwork(page);
  let cov = null;
  if (withCoverage) cov = await instrumentCoverage(page);

  await action();

  // Give LCP + long tasks a moment to settle.
  await page.waitForTimeout(waitAfterMs);

  // Pull in-page metrics.
  const inPage = await page.evaluate(() => {
    const perf = window.__nveilPerf || {};
    if (performance?.memory) {
      perf.memoryAfter = {
        used: performance.memory.usedJSHeapSize,
        total: performance.memory.totalJSHeapSize,
      };
    }
    const nav = performance.getEntriesByType('navigation')[0];
    return {
      vitals: perf.vitals || {},
      longTasks: perf.longTasks || [],
      tbtApprox: (perf.longTasks || []).reduce((s, t) => s + Math.max(0, t.duration - 50), 0),
      memoryBefore: perf.memoryBefore,
      memoryAfter: perf.memoryAfter,
      nav: nav ? {
        ttfb: Math.round(nav.responseStart),
        dcl: Math.round(nav.domContentLoadedEventEnd),
        loadEvent: Math.round(nav.loadEventEnd),
      } : null,
    };
  });

  const network = net.harvest();
  net.detach();
  const coverage = cov ? await cov.harvest() : null;

  return { ...inPage, network, coverage };
}

/**
 * Run `fn` N times, collect metrics each time, return median + p75 of key
 * numeric metrics (plus the raw runs for attachment).
 */
export async function measureN(fn, n = 5) {
  const runs = [];
  for (let i = 0; i < n; i++) runs.push(await fn(i));
  const keyFields = ['lcp', 'fcp', 'cls', 'inp', 'ttfb'];
  const vitalsMed = Object.fromEntries(keyFields.map(k => [k, median(runs.map(r => r.vitals?.[k]).filter(v => v != null))]));
  const vitalsP75 = Object.fromEntries(keyFields.map(k => [k, percentile(runs.map(r => r.vitals?.[k]).filter(v => v != null), 75)]));
  const tbtMed = median(runs.map(r => r.tbtApprox).filter(v => v != null));
  const transferMed = median(runs.map(r => r.network?.totalTransferBytes).filter(v => v != null));
  return {
    runs,
    median: { ...vitalsMed, tbtApprox: tbtMed, totalTransferBytes: transferMed },
    p75: { ...vitalsP75 },
  };
}

function median(arr) {
  if (!arr.length) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
function percentile(arr, p) {
  if (!arr.length) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, idx)];
}

// Keep the old export name working for the 2 old spec files we haven't
// migrated yet (landing.spec.js, authenticated-flows.spec.js — will be
// deleted in the tier1 migration step). Shim forwards to measurePage so
// nothing breaks mid-refactor.
export { measurePage as collectMetrics };
