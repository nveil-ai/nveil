# Performance & functional test suite

Single Playwright-driven suite that serves two intertwined goals:

1. **Functional correctness** — signup → login → dashboards → upload → create room → open viz → chat → logout → account deletion, all exercised end-to-end against the real local stack (Postgres, AI, viz, file services).
2. **Performance measurement** — Core Web Vitals, long tasks, network breakdown, JS/CSS coverage, memory captured for each flow. Regressions gated against a committed baseline.

Every Tier 2 test asserts **both** functional correctness AND a perf budget. A failing test means something broke — the report tells you which.

---

## Quick start

First time only (dependency install):
```bash
cd nveil/frontend && npm install && npx playwright install chromium
```

Then, from the repo root:

```bash
make up-perf      # start the stack in perf mode (once per session)
make perf-all     # static checks + full suite — run as many times as you want
make down         # stop the stack when you're done
```

`perf-all` does NOT rebuild the backend or the frontend — it runs against whatever image / `dist/` is already there. Rebuild explicitly if you need to pick up code changes. The Makefile auto-picks a local-dev bot password; you don't configure anything.

---

## Modes of operation

All commands run from the repo root. Requires the stack to be up via `make up-perf` (or use `make perf-all` which handles it for you).

| Command | What it does |
|---|---|
| `make perf-all` | **One-shot**: static checks + full suite. Assumes stack is up, no compilation. |
| `make up-perf` | Bring the stack up in perf mode (uses existing images, no rebuild). |
| `make perf` | Full suite (stack must already be up). |
| `make perf-ui` | **Playwright UI mode** — interactive timeline scrubber + DOM inspector + live replay. |
| `make perf-landing` | Just tier1 (public) tests. |
| `make perf-auth` | Just tier2 (authenticated) tests. |
| `make perf-static` | No-browser static regression guards (<5 s). |
| `make perf-baseline` | Snapshot current medians as the new baseline. |
| `make perf-compare` | Diff the latest run against the baseline. |
| `make perf-codegen` | Playwright recorder — capture selectors for new flows. |
| `make down` | Stop the stack. |

**Flags** apply to any `perf*` target:

| Flag | Purpose |
|---|---|
| `HEADED=1` | Show the browser window — watch the cursor drive the UI |
| `SLOWMO=500` | Insert 500 ms between Playwright actions (good with `HEADED=1`) |
| `TRACE=1` | Force-record a Playwright trace for every test |

Examples:

```bash
make perf-all HEADED=1                        # full suite with visible browser
make perf HEADED=1 SLOWMO=400                 # headed + slow-motion
make perf-landing HEADED=1                    # tier1 only, visible
TRACE=1 make perf -- 00-signup                # record trace for one spec
NVEIL_PERF_URL=https://staging.nveil.com make perf-landing   # staging, tier1
```

Open a captured trace with `npx playwright show-trace nveil/frontend/tests/perf/results/**/*.zip`. You get a full replay: network waterfall, console, screenshots per action, DOM snapshots.

---

## Suite structure

```
tests/perf/
├── playwright.config.js           # runner config: 3 projects, env flags, trace settings
├── global-setup.js                # stack health check + defensive clean-slate
├── global-teardown.js             # safety-net cleanup after the suite
├── tier1-public/                  # no auth needed
│   ├── landing.spec.js                    # 5-run Core Web Vitals
│   ├── landing-regression-guards.spec.js  # no plotly on landing, 1 React, no 4xx
│   ├── landing-scrolled.spec.js           # step-animations defer via IntersectionObserver
│   ├── explore.spec.js                    # /vendor/ chunks load on /explore
│   ├── explore-interaction.spec.js        # click showcase card → chart paints
│   ├── spa-navigation.spec.js             # chunks cached across re-nav
│   ├── other-routes.spec.js               # /feedback, /plan smoke
│   └── not-found.spec.js                  # 404 stays light
├── tier2-authenticated/           # runs in numbered order; shares auth state
│   ├── 00-signup.spec.js                  # creates bot account via UI (every run)
│   ├── 01-login.spec.js                   # measures login UX
│   ├── 02-authenticated-landing.spec.js
│   ├── 03-dashboards.spec.js
│   ├── 04-data-manager-upload.spec.js     # uploads fixtures/sample-small.csv
│   ├── 05-room-create.spec.js
│   ├── 06-room-open.spec.js               # waits on viz_loaded WS frame
│   ├── 07-chat-send.spec.js               # waits on chat_response (informational)
│   ├── 08-room-to-room.spec.js            # SPA cache reuse
│   ├── 09-logout.spec.js
│   └── 10-delete-account.spec.js          # final teardown + verification
├── static-checks/                 # no browser, <5s
│   ├── bundle-budget.mjs
│   ├── import-graph.mjs                   # rejects heavy-vendor imports in eager chain
│   └── importmap.mjs                      # rejects unresolved __V_X__ placeholders
├── utils/
│   ├── collect-metrics.js                 # web-vitals + long-tasks + network + coverage
│   ├── wait-helpers.js                    # waitForWsFrame, waitForFullIdle, etc.
│   ├── throttling.js                      # CPU + network throttling profiles
│   ├── api-login.js                       # direct /server/auth/login
│   ├── api-signup.js                      # direct /server/auth/register (fallback)
│   ├── api-delete-account.js              # direct DELETE /server/auth/delete-account
│   └── account-lifecycle.js               # ensureCleanSlate orchestrator
├── scripts/
│   ├── compare-runs.mjs                   # baseline vs latest, PR-style report
│   └── run-with-env.mjs                   # cross-platform env-var setter for npm scripts
├── fixtures/
│   └── sample-small.csv                   # 213-byte CSV for upload test
├── .auth/                         # gitignored — auth state, current room token
└── results/                       # gitignored — per-run JSON + HTML report + traces
```

---

## Environment variables

Most of these are auto-set by the Makefile — you only touch them when you want to override the default behavior.

| Var | Default (set by Makefile) | Purpose |
|---|---|---|
| `NVEIL_PERF_URL` | `https://localhost:8000` | Base URL of the stack to test |
| `PERF_BOT_EMAIL` | `testing-bot@nveil.com` | Bot account email (must be in `AUTH_TEST_EMAILS` on the stack side) |
| `PERF_BOT_PASSWORD` | `PerfBotLocal!2026` | Bot account password — local dev only |
| `PERF_BOT_NAME` | `Perf Bot` | Name used during signup form fill |
| `HEADED` | unset | `1` → visible browser |
| `SLOWMO` | `0` | ms delay between Playwright actions |
| `TRACE` | unset | `1` → force-record trace for every test |

To override: `PERF_BOT_EMAIL=foo@bar make perf`. The Makefile forwards these into `NVEIL_PERF_EMAIL` / `NVEIL_PERF_PASSWORD` / `NVEIL_PERF_NAME` for the test runner.

---

## How the auth lifecycle works

Every suite invocation is **idempotent**:

1. `globalSetup` pings `/server/auth/csrf` to verify the stack is up. Fails fast with a friendly message if you forgot `make up-perf`.
2. `globalSetup` also deletes any lingering bot account from a prior crashed run (defensive).
3. `00-signup.spec.js` creates the bot via the multi-step RegisterSteps UI. Backend auto-confirms because `AUTH_TEST_EMAILS` matches the email. Saves cookies to `.auth/state.json`.
4. `01-login.spec.js` performs a fresh login, measures it. Re-saves state.
5. `02` through `09` reuse the saved session via `test.use({ storageState: '.auth/state.json' })`.
6. `10-delete-account.spec.js` deletes the account, verifies via re-login attempt that it's gone.
7. `globalTeardown` runs a safety-net `ensureCleanSlate` in case any test crashed before step 10.

If any step fails, subsequent `.describe.serial` tests skip. But cleanup still fires.

---

## Static regression guards

Three checks run in <5 s without launching a browser. Ideal as the first PR gate:

- `bundle-budget.mjs` — eager-chain gzipped size, largest chunk, total. Fails if any budget exceeded.
- `import-graph.mjs` — rejects any static import of `vendor-plotly`/`vendor-deckgl`/`vendor-maplibre`/`vendor-forcegraph`/`vendor-kedro` from the eager landing chunk. Catches the exact regression we fought in the chunking cleanup.
- `importmap.mjs` — fails if any `__V_X__` placeholder survived the build (vendor-version-injector misfiring).

Wired: `npm run perf:static`.

---

## Baselines and regressions

After the first stable suite run:

```bash
make perf-baseline   # captures medians → tests/perf/baseline.json (committed)
```

On subsequent runs:

```bash
make perf            # produces results/perf-latest.json
make perf-compare    # diffs vs baseline.json; exits non-zero on regression
```

Current regression thresholds (in `scripts/compare-runs.mjs`):
- TTFB +25 %, FCP +15 %, LCP +10 %, TBT +20 %, transfer +10 %, chunk size +15 %.

Accept a deliberate regression: update `baseline.json` in the same PR that caused it.

---

## Troubleshooting

**"Stack not reachable at https://localhost:8000"**
Run `make up-perf` (not `make up` — that doesn't set `AUTH_TEST_EMAILS`), or just `make perf-all` which handles it. Verify with `curl -sSk https://localhost:8000/server/auth/csrf`.

**"Email already registered" on signup**
A prior run crashed before `10-delete-account`. `globalSetup` tries to clean this up automatically, but if your password is different from what's in env, it can't. Manually: `DELETE FROM nveilseption.users WHERE email IN ('testing-bot@nveil.com','perf-bot@nveil.com');` on the Postgres container.

**"Invalid hook call" or 500 errors on authenticated routes**
Check `make up-perf` output for server errors; the `AUTH_TEST_EMAILS` env var is set by the Makefile target and passed through in `docker-compose.yaml`. Confirm: `docker exec -it app-server-1 env | grep AUTH_TEST`.

**Flaky room-open / chat-send**
These are informational-only because Trame iframe startup and AI response times are highly variable (5-90 s). They don't gate the PR; they log timing for trend tracking.

**Tests time out on slow throttling project**
Tier 2 runs only on `desktop-fast` (enforced via `testIgnore: /tier2-authenticated/` in the throttling projects). If you need authenticated flows under throttling, comment those out explicitly.

---

## What's NOT covered in v1

- CI integration (Gitea Actions). Run locally until the suite stabilizes.
- Visual regression (screenshot diffing). Separate tool, different concern.
- Load testing (k6, artillery). Perf tests measure single-user latency, not throughput.
- Custom `performance.mark()` inside the app for precise "room ready" / "viz first frame" signals. Added later if useful.
