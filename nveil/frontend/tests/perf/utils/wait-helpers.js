// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Reusable "wait for X" primitives tests can compose.
//
// Playwright's built-in waitForXxx covers DOM/URL but not the product-specific
// signals NVEIL uses — WebSocket frames for `viz_loaded`, `chat_response`,
// `trame-ready`. These helpers bridge that gap.

/**
 * Wait for the first WebSocket frame (incoming) that matches `predicate`.
 * Useful for `{ event: 'viz_loaded' }` or `{ event: 'chat_response' }`.
 *
 * @param {import('@playwright/test').Page} page
 * @param {(frame: object) => boolean} predicate — receives the parsed JSON
 *        frame (returns false if parsing fails so callers can inspect raw too).
 * @param {number} timeoutMs
 * @returns {Promise<object>} the matching frame payload
 */
export async function waitForWsFrame(page, predicate, timeoutMs = 60_000, { sinceMs = 0 } = {}) {
  // If the shared fixture is running, frames are buffered on page.__wsFrames.
  // Check the buffer for a match first (useful for frames received before
  // this call was made), then install a fresh listener for future frames.
  const startAt = Date.now();
  const buffer = page.__wsFrames || [];
  for (const entry of buffer) {
    if (entry.at < sinceMs) continue;
    try { if (predicate(entry.payload)) return entry.payload; } catch { /* skip */ }
  }

  return new Promise((resolve, reject) => {
    const handlers = [];
    const timer = setTimeout(() => {
      for (const [ws, fn] of handlers) ws.off('framereceived', fn);
      if (page.__wsFrames) page.__waitForWsFrame_poller && clearInterval(page.__waitForWsFrame_poller);
      reject(new Error(`waitForWsFrame timeout after ${timeoutMs}ms`));
    }, timeoutMs);

    // Poll the shared buffer too, so frames on WSes opened before this call
    // (e.g., the /ws/events one from login) are covered.
    if (page.__wsFrames) {
      let idx = page.__wsFrames.length;
      const poller = setInterval(() => {
        while (idx < page.__wsFrames.length) {
          const entry = page.__wsFrames[idx++];
          try {
            if (predicate(entry.payload)) {
              clearTimeout(timer);
              clearInterval(poller);
              for (const [w, fn] of handlers) w.off('framereceived', fn);
              resolve(entry.payload);
              return;
            }
          } catch { /* skip */ }
        }
      }, 100);
      page.__waitForWsFrame_poller = poller;
    }

    // Also install a direct listener for any NEW websockets opened after
    // this call — covers WS that reconnect during navigation.
    function onWebSocket(ws) {
      const onFrame = ({ payload }) => {
        let parsed;
        try { parsed = JSON.parse(payload); } catch { parsed = payload; }
        try {
          if (predicate(parsed)) {
            clearTimeout(timer);
            if (page.__waitForWsFrame_poller) clearInterval(page.__waitForWsFrame_poller);
            for (const [w, fn] of handlers) w.off('framereceived', fn);
            resolve(parsed);
          }
        } catch { /* predicate threw; keep listening */ }
      };
      ws.on('framereceived', onFrame);
      handlers.push([ws, onFrame]);
    }
    page.on('websocket', onWebSocket);
    // Unused, silence linter on startAt
    void startAt;
  });
}

/**
 * Wait for a Performance API timing mark to land. Useful once the app
 * emits its own `performance.mark('nveil.viz.ready')` (not required for v1,
 * but this helper is ready when the marks are added).
 */
export async function waitForPerfMark(page, markName, timeoutMs = 30_000) {
  return page.evaluate(
    ({ name, t }) => new Promise((resolve, reject) => {
      // Was it already fired before we observed?
      const existing = performance.getEntriesByName(name);
      if (existing.length) return resolve(existing[0].startTime);
      const timer = setTimeout(() => {
        observer.disconnect();
        reject(new Error(`waitForPerfMark('${name}') timeout after ${t}ms`));
      }, t);
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.name === name) {
            clearTimeout(timer);
            observer.disconnect();
            resolve(entry.startTime);
            return;
          }
        }
      });
      observer.observe({ type: 'mark', buffered: true });
    }),
    { name: markName, t: timeoutMs }
  );
}

/**
 * Wait for `condition(page)` to return truthy, polling every `intervalMs`.
 * Falls back to page.waitForFunction-style behavior but more flexible for
 * conditions that span JS + DOM + browser state.
 */
export async function waitForCondition(page, condition, { timeoutMs = 30_000, intervalMs = 250 } = {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const result = await condition(page);
    if (result) return result;
    await page.waitForTimeout(intervalMs);
  }
  throw new Error(`waitForCondition timeout after ${timeoutMs}ms`);
}

/**
 * Wait for the network to be genuinely idle (0 inflight requests for >=
 * stableMs). Playwright's `networkidle` is "≤ 2 requests for 500 ms" which
 * is too lenient for our tests that care about lazy-chunk arrival.
 */
export async function waitForFullIdle(page, { stableMs = 1000, timeoutMs = 15_000 } = {}) {
  const start = Date.now();
  let inflight = 0;
  let idleSince = Date.now();

  const onRequest = () => { inflight++; idleSince = Infinity; };
  const onSettled = () => {
    inflight = Math.max(0, inflight - 1);
    if (inflight === 0) idleSince = Date.now();
  };
  page.on('request', onRequest);
  page.on('requestfinished', onSettled);
  page.on('requestfailed', onSettled);

  try {
    while (Date.now() - start < timeoutMs) {
      if (inflight === 0 && Date.now() - idleSince >= stableMs) return;
      await page.waitForTimeout(100);
    }
    throw new Error(`waitForFullIdle timeout after ${timeoutMs}ms (inflight=${inflight})`);
  } finally {
    page.off('request', onRequest);
    page.off('requestfinished', onSettled);
    page.off('requestfailed', onSettled);
  }
}
