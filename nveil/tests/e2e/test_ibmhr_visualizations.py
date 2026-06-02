# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""IBMHR Visualization Test Suite

End-to-end tests for the Nveil SDK using the IBM HR Analytics dataset
(examples/Miscellaneous/IBMHR/IBMHR.csv — 2068 employees, 35 columns).

Two test categories are covered:

  Visualization types (ids 1–15)
    Exercises every supported mark type with natural-language prompts.
    Each test calls generate_spec() + render() and attempts export in all
    six formats. Expected outcomes:
      - ids 1–11, 15 : standard 2D charts (ECharts backend) → all 6 formats
      - id 12 (candle): may fail if the server cannot map salary data to OHLC
      - id 13 (node)  : may fail — requires graph-structured input
      - id 14 (surface): may fail — requires VTK (pip install 'nveil[extra]')

  Transform-heavy tests (ids 16–30)
    Exercises the choregraph transform library end-to-end by prompting for
    visualizations that require specific data-processing steps before
    rendering. Each entry documents the transforms it is expected to trigger:
      id 16 — filter_greater_than + aggregate_mean
      id 17 — filter_equal (×2, chained) + aggregate_mean
      id 18 — filter_in_range
      id 19 — filter_not_equal + aggregate_mean
      id 20 — aggregate_mean + sort_values + get_top_n
      id 21 — sort_values + get_top_percentage + aggregate_count
      id 22 — discretize + aggregate_mean
      id 23 — normalize_column (×2)
      id 24 — arithmetic_op (monthly income × 12)
      id 25 — calc_ratio + aggregate_mean
      id 26 — melt + aggregate_mean (multi-metric grouped bar)
      id 27 — hierarchical_rollup → treemap
      id 28 — aggregate_sum + sort_values
      id 29 — aggregate_median (grouped by gender)
      id 30 — filter_equal + aggregate_mean + sort_values + get_bottom_n

Per-test output
    For every test the suite records:
      - status          : "success" or "error"
      - error_type      : exception class name if failed
      - error_message   : full exception message
      - retry_after_s   : seconds to wait (populated on QuotaExceededError)
      - explanation     : human-readable description returned by the server
      - timing          : generate_spec wall time, render wall time, total
      - exports         : per-format result (success, file size, export time)
        Formats: html, png, jpg, svg, pdf, json

Results are written to nveil/tests/e2e/results/:
      summary_report.json  — machine-readable, one object per test
      summary_report.txt   — human-readable flat table
      <id>_<slug>/         — output files for each successful export

Usage
-----
Run all tests with default pacing (13s between tests, stays under rate limit):
    python nveil/tests/e2e/test_ibmhr_visualizations.py

Fire all requests without delay to intentionally trigger QuotaExceededError:
    python nveil/tests/e2e/test_ibmhr_visualizations.py --trigger-rate-limit

Against a server with a self-signed certificate (e.g. staging IP):
    python nveil/tests/e2e/test_ibmhr_visualizations.py --no-verify

Combine flags as needed:
    python nveil/tests/e2e/test_ibmhr_visualizations.py --no-verify --trigger-rate-limit

Via pytest (normal pacing, all tests):
    pytest nveil/tests/e2e/test_ibmhr_visualizations.py -s -v

Via pytest against a self-signed endpoint:
    NVEIL_NO_VERIFY=1 pytest nveil/tests/e2e/test_ibmhr_visualizations.py -s -v

Via pytest (rate-limit trigger, stops at first QuotaExceededError):
    NVEIL_TRIGGER_RATE_LIMIT=1 pytest nveil/tests/e2e/test_ibmhr_visualizations.py \\
        -k test_trigger_rate_limit -x -s

Filter to a specific test by id or slug:
    pytest nveil/tests/e2e/test_ibmhr_visualizations.py -k "07_pie" -s
    pytest nveil/tests/e2e/test_ibmhr_visualizations.py -k "transform" -s

Rate limiting
-------------
The API enforces 10 requests/minute per API key (= 5 generate_spec calls/min).
Default pacing sleeps 13s between tests. The --trigger-rate-limit flag disables
this sleep and stops the run as soon as a QuotaExceededError is received,
printing the retry_after value returned by the server.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_PATH = _REPO_ROOT / "examples" / "Miscellaneous" / "IBMHR" / "IBMHR.csv"
_RESULTS_DIR = Path(__file__).parent / "results"

# ---------------------------------------------------------------------------
# SDK configuration
# ---------------------------------------------------------------------------

# API_KEY = "nveil_D8PWbC6etkGMpmHu6GazJzTWLz2zN0eSImzt0GQ33HUEJla6lIWbXlqkzu4flC5S"
# BASE_URL = "https://app.nveil.com"
API_KEY = "nveil_IP_ZuOwekKXzdGGBZ-W_vT65hPZOubCYdmdxjkJiAOmgqtruxYrWStOBNRZ7n2s2"
BASE_URL = "https://34.8.13.210"

# ---------------------------------------------------------------------------
# Test matrix — one entry per visualization type to exercise
# ---------------------------------------------------------------------------

VISUALIZATIONS: list[dict] = [
    {
        "id": 1,
        "slug": "bar_by_department",
        "prompt": "Bar chart of employee count by department",
        "expected_mark": "bar",
    },
    {
        "id": 2,
        "slug": "stacked_bar_dept_jobrole",
        "prompt": "Stacked bar chart of headcount by department broken down by job role",
        "expected_mark": "bar (stacked)",
    },
    {
        "id": 3,
        "slug": "line_income_by_years",
        "prompt": "Line chart of average monthly income by years at company",
        "expected_mark": "line",
    },
    {
        "id": 4,
        "slug": "scatter_age_income_dept",
        "prompt": "Scatter plot of age vs monthly income colored by department",
        "expected_mark": "point",
    },
    {
        "id": 5,
        "slug": "histogram_income",
        "prompt": "Histogram showing the distribution of monthly income",
        "expected_mark": "histogram",
    },
    {
        "id": 6,
        "slug": "boxplot_income_by_jobrole",
        "prompt": "Box plot comparing monthly income across job roles",
        "expected_mark": "box",
    },
    {
        "id": 7,
        "slug": "pie_attrition",
        "prompt": "Pie chart showing the proportion of employees by attrition status",
        "expected_mark": "sector",
    },
    {
        "id": 8,
        "slug": "treemap_dept_jobrole",
        "prompt": "Treemap of employee count organized by department and job role",
        "expected_mark": "partition",
    },
    {
        "id": 9,
        "slug": "parallel_coords",
        "prompt": (
            "Parallel coordinates plot for age, monthly income, "
            "job level, and years at company"
        ),
        "expected_mark": "parallel",
    },
    {
        "id": 10,
        "slug": "heatmap_age_income",
        "prompt": "Density heatmap / contour showing the concentration of employees by age and monthly income",
        "expected_mark": "contour",
    },
    {
        "id": 11,
        "slug": "bubble_dept_income",
        "prompt": (
            "Bubble chart of department vs average monthly income "
            "where bubble size represents headcount"
        ),
        "expected_mark": "point (sized)",
    },
    {
        "id": 12,
        "slug": "candlestick_salary_dept",
        "prompt": "Candlestick chart showing salary ranges (min, Q1, Q3, max) by department",
        "expected_mark": "candle",
    },
    {
        "id": 13,
        "slug": "network_jobrole_dept",
        "prompt": "Network graph connecting job roles to their departments",
        "expected_mark": "node",
    },
    {
        "id": 14,
        "slug": "surface_age_years_income",
        "prompt": "3D surface plot of age, years at company, and monthly income",
        "expected_mark": "surface",
    },
    {
        "id": 15,
        "slug": "heatmap_salary_hike_by_ed_promo",
        "prompt": (
            "Heatmap of average percent salary hike by education level "
            "and years since last promotion, restricted to employees "
            "who were promoted within the last 5 years"
        ),
        "expected_mark": "contour",
        "expected_transforms": ["filter_less_than", "aggregate_mean"],
    },
    # ---- Transform-heavy tests (choregraph) ---------------------------------
    {
        "id": 16,
        "slug": "transform_filter_gt_agg_mean",
        "prompt": (
            "Bar chart of average monthly income by department, "
            "only for employees who have more than 5 years at the company"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["filter_greater_than", "aggregate_mean"],
    },
    {
        "id": 17,
        "slug": "transform_double_filter_equal",
        "prompt": (
            "Bar chart of average monthly income by job role "
            "for female employees who work overtime"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["filter_equal (Gender)", "filter_equal (OverTime)", "aggregate_mean"],
    },
    {
        "id": 18,
        "slug": "transform_filter_in_range_scatter",
        "prompt": (
            "Scatter plot of distance from home vs monthly income "
            "for employees aged between 28 and 45"
        ),
        "expected_mark": "point",
        "expected_transforms": ["filter_in_range"],
    },
    {
        "id": 19,
        "slug": "transform_filter_not_equal",
        "prompt": (
            "Bar chart of average job satisfaction by department, "
            "excluding employees in the Non-Travel business travel category"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["filter_not_equal", "aggregate_mean"],
    },
    {
        "id": 20,
        "slug": "transform_get_top_n",
        "prompt": (
            "Bar chart of the 10 job roles with the highest average monthly income"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["aggregate_mean", "sort_values", "get_top_n"],
    },
    {
        "id": 21,
        "slug": "transform_get_top_percentage",
        "prompt": (
            "Show the department breakdown of the top 15% earners "
            "as a bar chart compared to the overall headcount"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["sort_values", "get_top_percentage", "aggregate_count"],
    },
    {
        "id": 22,
        "slug": "transform_discretize_aggregate",
        "prompt": (
            "Group employees into 4 monthly income brackets and show "
            "the average years at company for each bracket as a bar chart"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["discretize", "aggregate_mean"],
    },
    {
        "id": 23,
        "slug": "transform_normalize_scatter",
        "prompt": (
            "Scatter plot of normalized monthly income versus normalized "
            "total working years, colored by department"
        ),
        "expected_mark": "point",
        "expected_transforms": ["normalize_column (MonthlyIncome)", "normalize_column (TotalWorkingYears)"],
    },
    {
        "id": 24,
        "slug": "transform_arithmetic_distribution",
        "prompt": (
            "Show the distribution of total annual compensation "
            "(monthly income multiplied by 12) by job level as a box plot"
        ),
        "expected_mark": "box",
        "expected_transforms": ["arithmetic_op"],
    },
    {
        "id": 25,
        "slug": "transform_calc_ratio",
        "prompt": (
            "Bar chart of the ratio of monthly income to hourly rate by department"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["calc_ratio", "aggregate_mean"],
    },
    {
        "id": 26,
        "slug": "transform_melt_multi_metric",
        "prompt": (
            "Grouped bar chart comparing average job satisfaction, "
            "environment satisfaction, relationship satisfaction, and "
            "work-life balance scores across departments"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["melt", "aggregate_mean"],
    },
    {
        "id": 27,
        "slug": "transform_hierarchical_rollup",
        "prompt": (
            "Treemap of total monthly payroll rolled up by department, "
            "then job role, then job level"
        ),
        "expected_mark": "partition",
        "expected_transforms": ["hierarchical_rollup"],
    },
    {
        "id": 28,
        "slug": "transform_aggregate_sum_sort",
        "prompt": (
            "Bar chart of total monthly payroll by department, "
            "sorted from highest to lowest"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["aggregate_sum", "sort_values"],
    },
    {
        "id": 29,
        "slug": "transform_aggregate_median_grouped",
        "prompt": (
            "Grouped bar chart of median monthly income by education field "
            "split by gender"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["aggregate_median"],
    },
    {
        "id": 30,
        "slug": "transform_filter_bottom_n",
        "prompt": (
            "Show the 5 job roles with the lowest average monthly income "
            "among full-time employees (standard hours equal to 80)"
        ),
        "expected_mark": "bar",
        "expected_transforms": ["filter_equal", "aggregate_mean", "sort_values", "get_bottom_n"],
    },
]

# Formats attempted for every successful render.
# save_html() handles .html; save_image() handles the rest.
EXPORT_FORMATS: list[str] = ["html", "png", "jpg", "svg", "pdf", "json"]

# ---------------------------------------------------------------------------
# Pacing
# ---------------------------------------------------------------------------

# Rate limit: 10 req/min per API key, 2 req per generate_spec call
# → max 5 generations/min → minimum 12s between tests.
# Default sleep adds 1s buffer. Set NVEIL_TRIGGER_RATE_LIMIT=1 to disable.
_INTER_TEST_SLEEP_S: int = 13


def _rate_limit_mode() -> bool:
    """Return True when the rate-limit trigger mode is active (no sleep)."""
    return os.environ.get("NVEIL_TRIGGER_RATE_LIMIT", "").lower() in ("1", "true", "yes")


def _no_verify_mode() -> bool:
    """Return True when SSL certificate verification should be skipped."""
    return os.environ.get("NVEIL_NO_VERIFY", "").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug_dir(viz: dict) -> Path:
    return _RESULTS_DIR / f"{viz['id']:02d}_{viz['slug']}"


def _export_fig(fig: Any, out_dir: Path) -> dict[str, dict]:
    """Try to export fig in every format. Returns per-format result dicts."""
    import nveil

    results: dict[str, dict] = {}
    for fmt in EXPORT_FORMATS:
        path = out_dir / f"output.{fmt}"
        t0 = time.perf_counter()
        try:
            if fmt == "html":
                nveil.save_html(fig, str(path))
            else:
                nveil.save_image(fig, str(path))
            elapsed = time.perf_counter() - t0
            results[fmt] = {
                "success": True,
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "export_time_s": round(elapsed, 3),
                "path": str(path.relative_to(_REPO_ROOT)),
            }
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            results[fmt] = {
                "success": False,
                "export_time_s": round(elapsed, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }
    return results


def _run_single(viz: dict) -> dict:
    """Run one visualization test. Returns a structured result dict."""
    import nveil
    from nveil.exceptions import (
        AuthenticationError,
        IncompatibleDataError,
        NveilError,
        QuotaExceededError,
        ScopeError,
        SpecGenerationError,
    )

    out_dir = _slug_dir(viz)
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "id": viz["id"],
        "prompt": viz["prompt"],
        "expected_mark": viz["expected_mark"],
        "expected_transforms": viz.get("expected_transforms", []),
        "status": "error",
        "error_type": None,
        "error_message": None,
        "retry_after_s": None,
        "explanation": None,
        "timing": {
            "generate_spec_wall_s": None,
            "render_wall_s": None,
            "total_wall_s": None,
            "sdk_timer_summary": None,
        },
        "exports": {},
    }

    total_t0 = time.perf_counter()

    # --- generate_spec -------------------------------------------------------
    spec = None
    t0 = time.perf_counter()
    try:
        spec = nveil.generate_spec(viz["prompt"], _DATA_PATH)
        result["timing"]["generate_spec_wall_s"] = round(time.perf_counter() - t0, 3)
    except AuthenticationError as exc:
        result["error_type"] = "AuthenticationError"
        result["error_message"] = str(exc)
        result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
        return result
    except ScopeError as exc:
        result["error_type"] = "ScopeError"
        result["error_message"] = str(exc)
        result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
        return result
    except QuotaExceededError as exc:
        result["error_type"] = "QuotaExceededError"
        result["error_message"] = str(exc)
        result["retry_after_s"] = exc.retry_after
        result["timing"]["generate_spec_wall_s"] = round(time.perf_counter() - t0, 3)
        result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
        return result
    except SpecGenerationError as exc:
        result["error_type"] = "SpecGenerationError"
        result["error_message"] = str(exc)
        result["timing"]["generate_spec_wall_s"] = round(time.perf_counter() - t0, 3)
        result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
        return result
    except NveilError as exc:
        result["error_type"] = type(exc).__name__
        result["error_message"] = str(exc)
        result["timing"]["generate_spec_wall_s"] = round(time.perf_counter() - t0, 3)
        result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
        return result
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error_message"] = str(exc)
        result["timing"]["generate_spec_wall_s"] = round(time.perf_counter() - t0, 3)
        result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
        return result

    # --- explanation ---------------------------------------------------------
    try:
        result["explanation"] = spec.explanation
    except Exception:
        pass

    # --- render --------------------------------------------------------------
    fig = None
    t0 = time.perf_counter()
    try:
        fig = spec.render(_DATA_PATH)
        result["timing"]["render_wall_s"] = round(time.perf_counter() - t0, 3)
    except IncompatibleDataError as exc:
        result["error_type"] = "IncompatibleDataError"
        result["error_message"] = str(exc)
        result["timing"]["render_wall_s"] = round(time.perf_counter() - t0, 3)
        result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
        return result
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error_message"] = str(exc)
        result["timing"]["render_wall_s"] = round(time.perf_counter() - t0, 3)
        result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
        return result

    # --- exports -------------------------------------------------------------
    result["exports"] = _export_fig(fig, out_dir)
    result["status"] = "success"
    result["timing"]["total_wall_s"] = round(time.perf_counter() - total_t0, 3)
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_TICK = "\u2713"
_CROSS = "\u2717"
_WARN = "~"


def _export_summary(exports: dict) -> str:
    parts = []
    for fmt in EXPORT_FORMATS:
        if not exports:
            parts.append(f"{fmt}:?")
            continue
        info = exports.get(fmt, {})
        sym = _TICK if info.get("success") else _CROSS
        parts.append(f"{fmt}:{sym}")
    return "  ".join(parts)


def _print_live(viz: dict, result: dict) -> None:
    status_sym = _TICK if result["status"] == "success" else _CROSS
    gen_t = f"{result['timing']['generate_spec_wall_s']:.1f}s" if result["timing"]["generate_spec_wall_s"] is not None else "—"
    rnd_t = f"{result['timing']['render_wall_s']:.1f}s" if result["timing"]["render_wall_s"] is not None else "—"
    tot_t = f"{result['timing']['total_wall_s']:.1f}s" if result["timing"]["total_wall_s"] is not None else "—"

    print(f"\n  [{status_sym}] #{result['id']:02d}  {viz['slug']}")
    print(f"       prompt     : {result['prompt']}")
    print(f"       expected   : {result['expected_mark']}")
    if result.get("expected_transforms"):
        print(f"       transforms : {', '.join(result['expected_transforms'])}")
    if result["status"] == "success":
        print(f"       timing     : gen={gen_t}  render={rnd_t}  total={tot_t}")
        if result.get("explanation"):
            expl = result["explanation"]
            expl_short = (expl[:120] + "…") if len(expl) > 120 else expl
            print(f"       explain    : {expl_short}")
        print(f"       exports    : {_export_summary(result.get('exports', {}))}")
    else:
        print(f"       error      : [{result['error_type']}] {result['error_message']}")
        if result.get("retry_after_s") is not None:
            print(f"       retry_after: {result['retry_after_s']}s")
        print(f"       timing     : {tot_t} total")


def _print_summary_table(results: list[dict]) -> None:
    success = sum(1 for r in results if r["status"] == "success")
    total = len(results)
    width = 90

    print("\n" + "=" * width)
    print(f"  IBMHR VISUALIZATION TEST SUMMARY  —  {success}/{total} passed")
    print("=" * width)
    header = f"  {'#':>2}  {'Slug':<35}  {'Status':>7}  {'Gen':>7}  {'Render':>7}  {'Total':>7}"
    print(header)
    print("-" * width)
    for r in results:
        slug = f"{r['id']:02d}_{next(v['slug'] for v in VISUALIZATIONS if v['id'] == r['id'])}"
        status = "OK" if r["status"] == "success" else "FAIL"
        gen_t = f"{r['timing']['generate_spec_wall_s']:.1f}s" if r["timing"]["generate_spec_wall_s"] is not None else "—"
        rnd_t = f"{r['timing']['render_wall_s']:.1f}s" if r["timing"]["render_wall_s"] is not None else "—"
        tot_t = f"{r['timing']['total_wall_s']:.1f}s" if r["timing"]["total_wall_s"] is not None else "—"
        sym = _TICK if r["status"] == "success" else _CROSS
        print(f"  {r['id']:>2}  {slug:<35}  {sym} {status:>5}  {gen_t:>7}  {rnd_t:>7}  {tot_t:>7}")
    print("=" * width)

    # Export format breakdown
    print("\n  Export format results (success counts):")
    fmt_counts = {fmt: 0 for fmt in EXPORT_FORMATS}
    for r in results:
        if r["status"] == "success":
            for fmt, info in r.get("exports", {}).items():
                if info.get("success"):
                    fmt_counts[fmt] = fmt_counts.get(fmt, 0) + 1
    for fmt, count in fmt_counts.items():
        bar = (_TICK * count) + (_CROSS * (success - count))
        print(f"    {fmt:<6}  {count:>2}/{success}  {bar}")
    print()


def _save_reports(results: list[dict]) -> None:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    json_path = _RESULTS_DIR / "summary_report.json"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    txt_path = _RESULTS_DIR / "summary_report.txt"
    lines = []
    for r in results:
        slug = f"{r['id']:02d}_{next(v['slug'] for v in VISUALIZATIONS if v['id'] == r['id'])}"
        lines.append(f"[{r['status'].upper():>7}]  {slug}")
        lines.append(f"  prompt  : {r['prompt']}")
        lines.append(f"  expected: {r['expected_mark']}")
        if r.get("expected_transforms"):
            lines.append(f"  transforms: {', '.join(r['expected_transforms'])}")
        if r["status"] == "success":
            lines.append(
                f"  timing  : gen={r['timing']['generate_spec_wall_s']}s  "
                f"render={r['timing']['render_wall_s']}s  "
                f"total={r['timing']['total_wall_s']}s"
            )
            if r.get("explanation"):
                lines.append(f"  explain : {r['explanation']}")
            for fmt, info in r.get("exports", {}).items():
                if info.get("success"):
                    lines.append(f"  {fmt:<6}: OK  {info['size_bytes']} bytes  ({info['export_time_s']}s)  -> {info['path']}")
                else:
                    lines.append(f"  {fmt:<6}: FAIL  {info.get('error', '?')}")
        else:
            lines.append(f"  error   : [{r['error_type']}] {r['error_message']}")
        lines.append("")

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Reports saved:")
    print(f"    {json_path}")
    print(f"    {txt_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse
    import nveil

    parser = argparse.ArgumentParser(description="IBMHR Visualization Test Suite")
    parser.add_argument(
        "--trigger-rate-limit",
        action="store_true",
        default=False,
        help=(
            "Disable inter-test sleep and fire all requests as fast as possible "
            "to intentionally trigger QuotaExceededError. "
            "By default tests are paced at one every "
            f"{_INTER_TEST_SLEEP_S}s to stay within the rate limit."
        ),
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        default=False,
        help=(
            "Disable SSL certificate verification. "
            "Use when connecting to a server with a self-signed certificate "
            "(e.g. a staging instance at an IP address)."
        ),
    )
    args = parser.parse_args()

    if args.trigger_rate_limit:
        os.environ["NVEIL_TRIGGER_RATE_LIMIT"] = "1"
    if args.no_verify:
        os.environ["NVEIL_NO_VERIFY"] = "1"

    if not _DATA_PATH.exists():
        print(f"[ERROR] IBMHR dataset not found: {_DATA_PATH}", file=sys.stderr)
        return 1

    no_verify = _no_verify_mode()
    nveil.configure(
        api_key=API_KEY,
        base_url=BASE_URL,
        timing=True,
        verbose=False,
        verify=not no_verify,
    )

    viz_tests = sum(1 for v in VISUALIZATIONS if not v.get("expected_transforms"))
    transform_tests = sum(1 for v in VISUALIZATIONS if v.get("expected_transforms"))
    trigger_mode = _rate_limit_mode()
    pacing_label = "DISABLED — rate limit trigger mode" if trigger_mode else f"{_INTER_TEST_SLEEP_S}s between tests"

    print(f"\nNVEIL IBMHR Visualization Test Suite")
    print(f"  Dataset    : {_DATA_PATH}")
    print(f"  Endpoint   : {BASE_URL}")
    print(f"  SSL verify : {'no (self-signed cert accepted)' if no_verify else 'yes'}")
    print(f"  Outputs    : {_RESULTS_DIR}")
    print(f"  Tests      : {len(VISUALIZATIONS)}  ({viz_tests} viz-type  +  {transform_tests} transform-heavy)")
    print(f"  Pacing     : {pacing_label}")

    all_results: list[dict] = []

    for i, viz in enumerate(VISUALIZATIONS):
        if i > 0 and not trigger_mode:
            print(f"\n  ⏱  pacing: waiting {_INTER_TEST_SLEEP_S}s…", end="", flush=True)
            time.sleep(_INTER_TEST_SLEEP_S)

        print(f"\n  Running #{viz['id']:02d}/{len(VISUALIZATIONS)}  [{viz['expected_mark']}]  {viz['prompt'][:70]}…", end="", flush=True)
        result = _run_single(viz)
        all_results.append(result)
        _print_live(viz, result)

        # Stop early if rate-limited in trigger mode — we've confirmed it works
        if trigger_mode and result.get("error_type") == "QuotaExceededError":
            print(f"\n  Rate limit triggered on test #{viz['id']} — stopping early.")
            break

    _print_summary_table(all_results)
    _save_reports(all_results)

    failures = sum(1 for r in all_results if r["status"] == "error")
    return 0 if failures == 0 else 1


# ---------------------------------------------------------------------------
# pytest compatibility — one test per visualization
# ---------------------------------------------------------------------------

def _make_pytest_id(viz: dict) -> str:
    return f"{viz['id']:02d}_{viz['slug']}"


try:
    import pytest

    @pytest.fixture(scope="module", autouse=True)
    def _configure_nveil():
        import nveil
        nveil.configure(
            api_key=API_KEY,
            base_url=BASE_URL,
            timing=True,
            verbose=False,
            verify=not _no_verify_mode(),
        )

    @pytest.fixture(autouse=True)
    def _inter_test_sleep(request):
        """Sleep between tests unless NVEIL_TRIGGER_RATE_LIMIT=1."""
        yield
        if not _rate_limit_mode():
            time.sleep(_INTER_TEST_SLEEP_S)

    @pytest.mark.parametrize("viz", VISUALIZATIONS, ids=[_make_pytest_id(v) for v in VISUALIZATIONS])
    def test_visualization(viz: dict):
        import nveil
        from nveil.exceptions import NveilError, QuotaExceededError

        out_dir = _RESULTS_DIR / f"{viz['id']:02d}_{viz['slug']}"
        out_dir.mkdir(parents=True, exist_ok=True)

        t0 = time.perf_counter()
        try:
            spec = nveil.generate_spec(viz["prompt"], _DATA_PATH)
        except QuotaExceededError as exc:
            retry_msg = f"  retry_after: {exc.retry_after}s" if exc.retry_after else ""
            pytest.fail(f"Rate limit hit [{type(exc).__name__}]: {exc}{retry_msg}")
        except NveilError as exc:
            pytest.fail(f"generate_spec failed [{type(exc).__name__}]: {exc}")

        print(f"\n  generate_spec: {time.perf_counter() - t0:.2f}s")

        t0 = time.perf_counter()
        try:
            fig = spec.render(_DATA_PATH)
        except NveilError as exc:
            pytest.fail(f"render failed [{type(exc).__name__}]: {exc}")

        print(f"  render: {time.perf_counter() - t0:.2f}s")

        exports = _export_fig(fig, out_dir)
        for fmt, info in exports.items():
            print(f"  {fmt}: {'OK' if info['success'] else 'FAIL'}")

        assert fig is not None, "render() returned None"

    @pytest.mark.parametrize("viz", VISUALIZATIONS, ids=[_make_pytest_id(v) for v in VISUALIZATIONS])
    def test_trigger_rate_limit(viz: dict):
        """Fire requests with no pacing to confirm QuotaExceededError is raised.

        Run with: NVEIL_TRIGGER_RATE_LIMIT=1 pytest -k test_trigger_rate_limit -x
        The -x flag stops at first failure; the first QuotaExceededError is the pass condition.
        """
        import nveil
        from nveil.exceptions import QuotaExceededError

        if not _rate_limit_mode():
            pytest.skip("Set NVEIL_TRIGGER_RATE_LIMIT=1 to run rate-limit trigger tests")

        try:
            spec = nveil.generate_spec(viz["prompt"], _DATA_PATH)
            spec.render(_DATA_PATH)
        except QuotaExceededError as exc:
            retry_info = f" (retry_after={exc.retry_after}s)" if exc.retry_after else ""
            pytest.xfail(f"Rate limit triggered as expected: {exc}{retry_info}")

except ImportError:
    pass


if __name__ == "__main__":
    sys.exit(main())
