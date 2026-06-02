// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// CDP-based CPU + network throttling profiles.
//
// Playwright's devices preset covers viewport + UA only; CPU and network
// throttling have to be applied via the Chrome DevTools Protocol per page.
// Call applyThrottling(page, PROFILES.desktop4xSlow) in your test's before-
// navigation setup.

export const PROFILES = {
  // No throttling — upper bound, fast developer laptop.
  unthrottled: { cpuRate: 1, network: null },

  // Mid-tier real user — 4× CPU slowdown, fast 4G network.
  desktop4xSlow: {
    cpuRate: 4,
    network: {
      offline: false,
      latency: 40,                // ms RTT
      downloadThroughput: 9_000_000 / 8,   // 9 Mbps → bytes/s
      uploadThroughput: 3_000_000 / 8,     // 3 Mbps → bytes/s
    },
  },

  // Worst-case real user — slow 4G + 4× CPU.
  mobileSlow4g: {
    cpuRate: 4,
    network: {
      offline: false,
      latency: 150,
      downloadThroughput: 1_600_000 / 8,   // 1.6 Mbps
      uploadThroughput: 750_000 / 8,       // 750 kbps
    },
  },
};

/**
 * Apply the given throttling profile to a Playwright page. Returns the CDP
 * session so callers can detach/adjust later if needed.
 */
export async function applyThrottling(page, profile) {
  const client = await page.context().newCDPSession(page);
  if (profile.cpuRate && profile.cpuRate !== 1) {
    await client.send('Emulation.setCPUThrottlingRate', { rate: profile.cpuRate });
  }
  if (profile.network) {
    await client.send('Network.emulateNetworkConditions', profile.network);
  }
  return client;
}

/**
 * Pick the throttling profile for the current Playwright project. Tests
 * use this so they don't have to know the project name.
 */
export function profileForProject(projectName) {
  switch (projectName) {
    case 'desktop-4x-slow':
      return PROFILES.desktop4xSlow;
    case 'mobile-slow-4g':
      return PROFILES.mobileSlow4g;
    default:
      return PROFILES.unthrottled;
  }
}
