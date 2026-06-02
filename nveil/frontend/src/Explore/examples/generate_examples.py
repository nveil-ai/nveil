#!/usr/bin/env python3
"""Generate pre-computed example JSON specs for the Explore page.

Usage:
    cd nveil/frontend/src/Explore/examples
    python generate_examples.py

Outputs lightweight JSON files consumed by the React frontend.
No external dependencies required (stdlib only).
"""

import json
import math
import os
import random
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent

COLORS = ["#1b90ba", "#2563eb", "#7c3aed", "#a33cb2", "#10b981", "#f59e0b", "#ef4444", "#06b6d4"]
COLORSCALE = [[0, "#0d1b2a"], [0.25, "#1b3a5c"], [0.5, "#1b90ba"], [0.75, "#7c3aed"], [1, "#a33cb2"]]


def write_json(name: str, data: dict):
    path = OUTPUT_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"  {path.name} ({path.stat().st_size:,} bytes)")


# ── Charts & Distributions ──────────────────────

def generate_bar():
    """Bar chart — revenue by category."""
    write_json("bar", {
        "data": [{
            "type": "bar",
            "x": ["Electronics", "Clothing", "Food", "Books", "Home", "Sports", "Toys"],
            "y": [42000, 31500, 28000, 19500, 17200, 14800, 12300],
            "marker": {"color": ["#1b90ba", "#2563eb", "#7c3aed", "#a33cb2", "#db2777", "#e05555", "#f59e0b"]},
        }],
        "layout": {"xaxis": {"title": "Category"}, "yaxis": {"title": "Revenue ($)"}},
    })


def generate_line():
    """Multi-series line chart — monthly sales YoY."""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    write_json("line", {
        "data": [
            {"type": "scatter", "mode": "lines", "name": "2024",
             "x": months, "y": [12000, 14500, 13200, 17800, 16500, 19200, 21000, 20300, 18700, 22100, 24500, 26800],
             "line": {"color": "#1b90ba", "width": 2.5}},
            {"type": "scatter", "mode": "lines", "name": "2023",
             "x": months, "y": [9800, 11200, 10500, 13400, 12800, 15100, 16200, 15800, 14600, 17300, 19100, 20500],
             "line": {"color": "#7c3aed", "width": 2, "dash": "dot"}},
        ],
        "layout": {"xaxis": {"title": "Month"}, "yaxis": {"title": "Sales ($)"}},
    })


def generate_point():
    """Scatter plot — age vs income with color scale."""
    random.seed(42)
    n = 25
    ages = [random.randint(22, 60) for _ in range(n)]
    incomes = [int(a * 1500 + random.gauss(0, 8000) + 10000) for a in ages]
    sizes = [max(6, int(inc / 6000)) for inc in incomes]
    write_json("point", {
        "data": [{
            "type": "scatter", "mode": "markers",
            "x": ages, "y": incomes,
            "marker": {"size": sizes, "color": ages,
                       "colorscale": [[0, "#1b90ba"], [0.33, "#2563eb"], [0.66, "#7c3aed"], [1, "#a33cb2"]],
                       "showscale": True,
                       "colorbar": {"title": "Age", "tickfont": {"color": "#a1a1aa"}, "titlefont": {"color": "#a1a1aa"}}},
        }],
        "layout": {"xaxis": {"title": "Age"}, "yaxis": {"title": "Income"}},
    })


def generate_histogram():
    """Histogram with bimodal distribution."""
    random.seed(42)
    vals = [random.gauss(45, 8) for _ in range(80)] + [random.gauss(72, 6) for _ in range(60)]
    write_json("histogram", {
        "data": [{
            "type": "histogram", "x": [round(v, 1) for v in vals], "nbinsx": 25,
            "marker": {"color": "rgba(27,144,186,0.7)", "line": {"color": "#1b90ba", "width": 1}},
        }],
        "layout": {"xaxis": {"title": "Score"}, "yaxis": {"title": "Count"}},
    })


def generate_box():
    """Box plots — salary by department."""
    random.seed(42)
    depts = [
        ("Engineering", 78000, 12000, "#1b90ba"),
        ("Marketing", 55000, 5000, "#7c3aed"),
        ("Sales", 56000, 12000, "#a33cb2"),
        ("Design", 60000, 5000, "#2563eb"),
    ]
    data = []
    for name, mu, sigma, color in depts:
        vals = [int(random.gauss(mu, sigma)) for _ in range(12)]
        data.append({"type": "box", "name": name, "y": vals, "marker": {"color": color}, "boxpoints": "outliers"})
    write_json("box", {"data": data, "layout": {"yaxis": {"title": "Salary ($)"}}})


def generate_sector():
    """Pie chart — browser market share."""
    write_json("sector", {
        "data": [{
            "type": "pie",
            "labels": ["Chrome", "Safari", "Firefox", "Edge", "Other"],
            "values": [64.7, 18.6, 3.3, 5.1, 8.3],
            "marker": {"colors": ["#1b90ba", "#2563eb", "#7c3aed", "#a33cb2", "#444"]},
            "hole": 0.35,
            "textinfo": "label+percent",
            "textfont": {"color": "#e0e0e0", "size": 11},
        }],
        "layout": {},
    })


def generate_violin():
    """Violin plot — salary distribution by department."""
    random.seed(42)
    eng = [round(random.gauss(85000, 15000), 0) for _ in range(30)]
    mkt = [round(random.gauss(65000, 10000), 0) for _ in range(30)]
    sales = [round(random.gauss(72000, 18000), 0) for _ in range(30)]
    write_json("violin", {
        "data": [
            {"type": "violin", "y": eng, "name": "Engineering", "marker": {"color": "#1b90ba"}, "box": {"visible": True}, "meanline": {"visible": True}},
            {"type": "violin", "y": mkt, "name": "Marketing", "marker": {"color": "#7c3aed"}, "box": {"visible": True}, "meanline": {"visible": True}},
            {"type": "violin", "y": sales, "name": "Sales", "marker": {"color": "#a33cb2"}, "box": {"visible": True}, "meanline": {"visible": True}},
        ],
        "layout": {"yaxis": {"title": "Salary"}, "showlegend": False},
    })


def generate_candle():
    """Candlestick chart — 3 months of stock prices."""
    random.seed(42)
    dates = [f"2024-{m:02d}-{d:02d}" for m in range(1, 4) for d in range(1, 11)]
    price = 150.0
    opens, highs, lows, closes = [], [], [], []
    for _ in dates:
        o = round(price, 2)
        c = round(o + random.gauss(0, 3), 2)
        h = round(max(o, c) + abs(random.gauss(0, 2)), 2)
        l = round(min(o, c) - abs(random.gauss(0, 2)), 2)
        opens.append(o); highs.append(h); lows.append(l); closes.append(c)
        price = c
    write_json("candle", {
        "data": [{"type": "candlestick", "x": dates, "open": opens, "high": highs, "low": lows, "close": closes,
                  "increasing": {"line": {"color": "#10b981"}}, "decreasing": {"line": {"color": "#ef4444"}}}],
        "layout": {"xaxis": {"title": "Date", "rangeslider": {"visible": False}}, "yaxis": {"title": "Price"}},
    })


# ── Spatial & Heatmaps ──────────────────────────

def generate_surface3d():
    """3D surface — Gaussian peak with cosine modulation."""
    S = 20
    z = []
    for i in range(S):
        row = []
        for j in range(S):
            x = -3 + 6 * j / (S - 1)
            y = -3 + 6 * i / (S - 1)
            r = math.sqrt(x**2 + y**2)
            v = 3 * math.exp(-r**2 / 4) * math.cos(r)
            row.append(round(v, 3))
        z.append(row)
    write_json("surface3d", {
        "data": [{"type": "surface", "z": z, "colorscale": COLORSCALE, "showscale": True,
                  "colorbar": {"tickfont": {"color": "#a1a1aa"}},
                  "contours": {"z": {"show": True, "usecolormap": True, "project": {"z": True}}}}],
        "layout": {"scene": {
            "xaxis": {"title": "X", "backgroundcolor": "rgba(0,0,0,0)", "gridcolor": "rgba(255,255,255,0.06)", "color": "#a1a1aa"},
            "yaxis": {"title": "Y", "backgroundcolor": "rgba(0,0,0,0)", "gridcolor": "rgba(255,255,255,0.06)", "color": "#a1a1aa"},
            "zaxis": {"title": "Z", "backgroundcolor": "rgba(0,0,0,0)", "gridcolor": "rgba(255,255,255,0.06)", "color": "#a1a1aa"},
            "bgcolor": "rgba(0,0,0,0)",
            "camera": {"eye": {"x": 1.5, "y": 1.5, "z": 1.2}},
        }, "margin": {"l": 0, "r": 0, "t": 0, "b": 0}},
    })


def generate_unigrid():
    """Heatmap — temperature grid with square aspect ratio + color bar."""
    N = 10
    z = []
    for i in range(N):
        row = []
        for j in range(N):
            cx, cy = (j - N / 2) / (N / 2), (i - N / 2) / (N / 2)
            row.append(round(48 - math.sqrt(cx**2 + cy**2) * 30 + math.sin(cx * 3) * 5, 1))
        z.append(row)
    write_json("unigrid", {
        "data": [{"type": "heatmap", "z": z, "colorscale": COLORSCALE, "showscale": True,
                  "colorbar": {"tickfont": {"color": "#a1a1aa"}, "titlefont": {"color": "#a1a1aa"}}}],
        "layout": {"xaxis": {"title": "Longitude", "scaleanchor": "y"}, "yaxis": {"title": "Latitude"}},
    })


def generate_contour():
    """Contour plot — sin(x)*cos(y) mathematical function."""
    S = 20
    z = []
    for i in range(S):
        row = []
        for j in range(S):
            x = -3 + 6 * j / (S - 1)
            y = -3 + 6 * i / (S - 1)
            v = math.sin(x) * math.cos(y) * 3 + math.cos(x * y / 3)
            row.append(round(v, 3))
        z.append(row)
    write_json("contour", {
        "data": [{"type": "contour", "z": z, "colorscale": COLORSCALE, "showscale": True,
                  "colorbar": {"tickfont": {"color": "#a1a1aa"}},
                  "contours": {"coloring": "heatmap"}}],
        "layout": {"xaxis": {"title": "X"}, "yaxis": {"title": "Y", "scaleanchor": "x"}},
    })


def generate_choropleth():
    """Choropleth map — GDP per capita by country."""
    write_json("choropleth", {
        "data": [{"type": "choropleth",
                  "locations": ["USA", "CAN", "GBR", "FRA", "DEU", "JPN", "AUS", "BRA", "IND", "CHN",
                                "RUS", "ZAF", "MEX", "KOR", "ITA", "ESP", "NGA", "EGY", "ARG", "IDN"],
                  "z": [63543, 51988, 46510, 42330, 50801, 39285, 51812, 8717, 2256, 12556,
                        12173, 6001, 10045, 31489, 34321, 29614, 2184, 3699, 10636, 4292],
                  "locationmode": "ISO-3",
                  "colorscale": COLORSCALE, "showscale": True,
                  "colorbar": {"title": "GDP/cap", "tickfont": {"color": "#a1a1aa"}, "titlefont": {"color": "#a1a1aa"}},
                  "marker": {"line": {"color": "rgba(255,255,255,0.15)", "width": 0.5}}}],
        "layout": {"geo": {
            "showframe": False, "showcoastlines": True,
            "coastlinecolor": "rgba(255,255,255,0.15)",
            "projection": {"type": "natural earth"},
            "bgcolor": "rgba(0,0,0,0)",
            "landcolor": "rgba(30,30,30,0.8)",
            "showlakes": False,
            "countrycolor": "rgba(255,255,255,0.08)",
        }, "margin": {"l": 0, "r": 0, "t": 0, "b": 0}},
    })


def generate_vector():
    """2D vector field — multi-vortex with Plotly native streamlines + arrows."""
    import numpy as np
    import plotly.figure_factory as ff

    N = 20
    x_range = np.linspace(-3, 3, N)
    y_range = np.linspace(-3, 3, N)
    X, Y = np.meshgrid(x_range, y_range)

    vortices = [
        (-1.8, 1.2, 1.4, 1),
        (1.5, 1.8, 1.1, -1),
        (0.2, -0.5, 1.8, 1),
        (-1.2, -1.8, 1.0, -1),
        (2.0, -1.0, 1.3, 1),
    ]
    U = np.zeros_like(X)
    V = np.zeros_like(Y)
    for cx, cy, strength, sign in vortices:
        dx, dy = X - cx, Y - cy
        r = np.sqrt(dx**2 + dy**2) + 0.25
        decay = strength * np.exp(-r * 0.6)
        U += -sign * dy * decay / r
        V += sign * dx * decay / r
    U += 0.15 * np.sin(Y * 0.8)
    V += 0.15 * np.cos(X * 0.8)

    fig = ff.create_streamline(
        x_range.tolist(), y_range.tolist(),
        U.tolist(), V.tolist(),
        density=0.8, arrow_scale=0.06,
    )

    # White traces, strip NaN, compact coordinates
    data = []
    for trace in fig.data:
        t = {"type": "scatter", "showlegend": False, "hoverinfo": "skip"}
        tx = [round(v, 2) if v is not None and not (isinstance(v, float) and math.isnan(v)) else None for v in trace.x]
        ty = [round(v, 2) if v is not None and not (isinstance(v, float) and math.isnan(v)) else None for v in trace.y]
        t["x"] = tx
        t["y"] = ty
        if trace.mode and "markers" in trace.mode:
            t["mode"] = "markers"
            t["marker"] = {"color": "rgba(255,255,255,0.8)", "size": 4}
        else:
            t["mode"] = "lines"
            t["line"] = {"color": "rgba(255,255,255,0.6)", "width": 0.8}
        data.append(t)

    write_json("vector", {
        "data": data,
        "layout": {
            "xaxis": {"range": [-3.5, 3.5], "scaleanchor": "y",
                      "showgrid": False, "zeroline": False, "showticklabels": False},
            "yaxis": {"range": [-3.5, 3.5],
                      "showgrid": False, "zeroline": False, "showticklabels": False},
            "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
        },
    })


# ── Networks & Flows ────────────────────────────

def generate_node():
    """Force-directed graph — collaboration network."""
    nodes = [
        {"id": i, "name": name, "color": color}
        for i, (name, color) in enumerate([
            ("Alice", "#1b90ba"), ("Bob", "#1b90ba"), ("Carol", "#2563eb"), ("Dave", "#2563eb"),
            ("Eve", "#7c3aed"), ("Frank", "#7c3aed"), ("Grace", "#a33cb2"), ("Heidi", "#a33cb2"),
            ("Ivan", "#1b90ba"), ("Judy", "#2563eb"), ("Karl", "#7c3aed"), ("Liam", "#a33cb2"),
        ])
    ]
    links = [
        {"source": 0, "target": 1}, {"source": 0, "target": 2}, {"source": 1, "target": 3},
        {"source": 2, "target": 4}, {"source": 3, "target": 5}, {"source": 4, "target": 6},
        {"source": 5, "target": 7}, {"source": 6, "target": 0}, {"source": 7, "target": 1},
        {"source": 8, "target": 0}, {"source": 8, "target": 3}, {"source": 9, "target": 2},
        {"source": 9, "target": 5}, {"source": 10, "target": 4}, {"source": 10, "target": 7},
        {"source": 11, "target": 6}, {"source": 11, "target": 1}, {"source": 8, "target": 9},
        {"source": 10, "target": 11},
    ]
    write_json("node", {"nodes": nodes, "links": links})


def generate_sankey():
    """Sankey diagram — energy flow."""
    write_json("sankey", {
        "data": [{"type": "sankey",
                  "node": {"label": ["Coal", "Gas", "Nuclear", "Solar", "Electricity", "Heat", "Residential", "Industry", "Transport"],
                           "color": ["#444", "#666", "#7c3aed", "#f59e0b", "#1b90ba", "#ef4444", "#10b981", "#2563eb", "#a33cb2"],
                           "pad": 20, "thickness": 20},
                  "link": {"source": [0, 1, 2, 3, 0, 1, 4, 4, 4, 5, 5],
                           "target": [4, 4, 4, 4, 5, 5, 6, 7, 8, 6, 7],
                           "value": [30, 40, 25, 15, 20, 15, 35, 50, 25, 15, 20],
                           "color": ["rgba(68,68,68,0.3)", "rgba(102,102,102,0.3)", "rgba(124,58,237,0.3)", "rgba(245,158,11,0.3)",
                                     "rgba(68,68,68,0.3)", "rgba(102,102,102,0.3)", "rgba(27,144,186,0.3)", "rgba(27,144,186,0.3)",
                                     "rgba(27,144,186,0.3)", "rgba(239,68,68,0.3)", "rgba(239,68,68,0.3)"]}}],
        "layout": {"font": {"color": "#a1a1aa", "size": 11}},
    })


def generate_parallel():
    """Parallel coordinates — car specs."""
    random.seed(42)
    n = 40
    mpg = [round(random.uniform(12, 45), 1) for _ in range(n)]
    cyl = [random.choice([4, 6, 8]) for _ in range(n)]
    hp = [round(random.uniform(60, 300), 0) for _ in range(n)]
    wt = [round(random.uniform(1.5, 5.5), 2) for _ in range(n)]
    write_json("parallel", {
        "data": [{"type": "parcoords",
                  "line": {"color": mpg, "colorscale": [[0, "#1b90ba"], [0.5, "#7c3aed"], [1, "#a33cb2"]], "showscale": True,
                           "colorbar": {"title": "MPG", "tickfont": {"color": "#a1a1aa"}, "titlefont": {"color": "#a1a1aa"}}},
                  "dimensions": [
                      {"label": "MPG", "values": mpg, "range": [10, 50]},
                      {"label": "Cylinders", "values": cyl, "range": [3, 9]},
                      {"label": "Horsepower", "values": hp, "range": [50, 320]},
                      {"label": "Weight (t)", "values": wt, "range": [1, 6]},
                  ]}],
        "layout": {},
    })


def generate_partition():
    """Treemap — company headcount by department/team."""
    write_json("partition", {
        "data": [{"type": "treemap",
                  "labels": ["Company", "Engineering", "Product", "Sales", "Frontend", "Backend", "DevOps", "Design", "PM", "NA", "EMEA", "APAC"],
                  "parents": ["", "Company", "Company", "Company", "Engineering", "Engineering", "Engineering", "Product", "Product", "Sales", "Sales", "Sales"],
                  "values": [0, 0, 0, 0, 15, 20, 8, 12, 6, 18, 14, 10],
                  "marker": {"colorscale": COLORSCALE, "colors": [0, 20, 40, 60, 25, 30, 15, 50, 45, 70, 55, 35]},
                  "textfont": {"color": "#e0e0e0"},
                  "textinfo": "label+value"}],
        "layout": {"margin": {"l": 0, "r": 0, "t": 0, "b": 0}},
    })


if __name__ == "__main__":
    print("Generating example JSONs for Explore page...")
    generate_bar()
    generate_line()
    generate_point()
    generate_histogram()
    generate_box()
    generate_sector()
    generate_violin()
    generate_candle()
    generate_surface3d()
    generate_unigrid()
    generate_contour()
    generate_choropleth()
    generate_node()
    generate_sankey()
    generate_parallel()
    generate_partition()
    generate_vector()
    print("Done!")
