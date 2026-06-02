// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// Compare a new perf run against the baseline (stored in baseline.json).
// Outputs a markdown summary suitable for PR comment.
//
// Usage:
//   node tests/perf/scripts/compare-runs.mjs           # compare vs baseline.json
//   node tests/perf/scripts/compare-runs.mjs --update  # replace baseline with new run

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const BASELINE = path.join(ROOT, 'baseline.json');
const LATEST = path.join(ROOT, 'results', 'perf-latest.json');

// Flag changes that exceed these deltas (percent worse than baseline).
const REGRESSION_THRESHOLDS = {
  ttfb: 25,
  fcp: 15,
  lcp: 10,
  tbtApprox: 20,
  totalTransferKB: 10,
};

const METRIC_LABELS = {
  ttfb: 'TTFB',
  fcp: 'FCP',
  lcp: 'LCP',
  tbtApprox: 'TBT (approx)',
  totalTransferKB: 'Transfer (KB)',
  longTaskCount: 'Long tasks',
};

function loadJSON(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function extractMedians(rawPlaywrightJson) {
  // Playwright's json reporter nests attachments in suites[].specs[].tests[].results[].attachments
  const out = {};
  const walk = (node) => {
    if (node.specs) node.specs.forEach(walk);
    if (node.tests) node.tests.forEach(walk);
    if (node.suites) node.suites.forEach(walk);
    if (node.results) {
      for (const r of node.results) {
        for (const att of r.attachments || []) {
          if (att.name === 'metrics.json' && att.path) {
            try {
              const m = JSON.parse(fs.readFileSync(att.path, 'utf8'));
              out[node.title || 'unknown'] = m.median || m;
            } catch {}
          }
        }
      }
    }
  };
  walk(rawPlaywrightJson);
  return out;
}

function percentDelta(baseline, current) {
  if (baseline == null || current == null) return null;
  if (baseline === 0) return current === 0 ? 0 : Infinity;
  return ((current - baseline) / baseline) * 100;
}

function formatRow(metric, baseline, current) {
  const delta = percentDelta(baseline, current);
  const thresh = REGRESSION_THRESHOLDS[metric];
  let indicator = '—';
  if (delta != null && thresh != null) {
    if (delta > thresh) indicator = '🔴';
    else if (delta < -thresh / 2) indicator = '🟢';
    else indicator = '🟡';
  }
  const deltaStr = delta == null ? '—' : `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%`;
  return `| ${METRIC_LABELS[metric] || metric} | ${baseline ?? '—'} | ${current ?? '—'} | ${deltaStr} | ${indicator} |`;
}

function renderReport(baseline, latest) {
  const lines = [
    '## Performance benchmark — comparison',
    '',
  ];
  const allTests = new Set([...Object.keys(baseline), ...Object.keys(latest)]);
  for (const test of allTests) {
    lines.push(`### ${test}`);
    lines.push('| Metric | Baseline | Current | Δ | |');
    lines.push('|---|---|---|---|---|');
    const b = baseline[test] || {};
    const c = latest[test] || {};
    const metrics = [...new Set([...Object.keys(b), ...Object.keys(c)])];
    for (const m of metrics) {
      lines.push(formatRow(m, b[m], c[m]));
    }
    lines.push('');
  }
  lines.push('---');
  lines.push('🟢 improved · 🟡 within tolerance · 🔴 regression (exceeds threshold)');
  return lines.join('\n');
}

function main() {
  const update = process.argv.includes('--update');

  if (!fs.existsSync(LATEST)) {
    console.error(`No latest results at ${LATEST}. Run the perf suite first.`);
    process.exit(1);
  }

  const latestRaw = loadJSON(LATEST);
  const latest = extractMedians(latestRaw);

  if (update || !fs.existsSync(BASELINE)) {
    fs.writeFileSync(BASELINE, JSON.stringify(latest, null, 2));
    console.log(`Baseline ${fs.existsSync(BASELINE) ? 'updated' : 'created'} at ${BASELINE}`);
    console.log(JSON.stringify(latest, null, 2));
    return;
  }

  const baseline = loadJSON(BASELINE);
  const report = renderReport(baseline, latest);
  console.log(report);

  // Write report to file for CI to post as PR comment.
  const reportPath = path.join(ROOT, 'results', 'report.md');
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, report);

  // Exit non-zero if any 🔴 appeared — blocks PR merge.
  if (report.includes('🔴')) {
    console.error('\nRegression detected. See report above.');
    process.exit(1);
  }
}

main();
