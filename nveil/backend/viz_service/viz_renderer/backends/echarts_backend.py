# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Apache ECharts visualization backend.

Merges the mark builders' option dicts, applies the theme-driven
figure padding (from ``dive.builder.themes.apply_figure_layout``), and
pushes the result to the Vue ``<v-chart>`` widget via
``ctx.ctrl_echarts_update``. SDK and viz_service use the same layout
helper so their charts share an identical base envelope.
"""
from dive.builder.figure_merge import mergeEcharts
from dive.builder.legend_utils import apply_legend
from dive.builder.themes import apply_figure_layout, get_echarts_theme_tokens


def show_echarts_viz(ctx, options, frame=None):
    """Render a list of ECharts option dicts to the trame widget.

    Args:
        ctx: VizContext with ``ctrl_echarts_update`` bound to the widget.
        options: List of per-mark option dicts returned from builders.
        frame: Optional VizFrame to reapply legend (title, description,
            reference lines/shapes) after merge.
    """
    if not options:
        return

    merged = mergeEcharts(options)

    # When merging multiple marks, the per-mark legend may have been lost.
    # Reapply figure-level annotations (title/subtitle/markLine/markArea).
    if frame is not None and len(options) > 1:
        apply_legend(merged, frame, backend="echarts")

    apply_figure_layout(merged, get_echarts_theme_tokens(getattr(ctx, "state_proxy", None)))

    # Remember the last-rendered option so ``nveil_viewer.export_image``
    # can hand it to ``dive.builder.export`` for PNG / SVG / PDF export
    # without having to re-run the mark builders.
    ctx._last_echarts_option = merged

    # Detect series-composition changes (types added / removed between
    # renders). When the composition changes — e.g. the user toggled
    # use_streamlines off so the flowGL series disappeared — echarts'
    # ``notMerge: false`` merge semantics would keep the old series
    # alive from the previous push. Calling ``clear()`` before the
    # update gives a clean slate for the new option. Only fires when
    # the series *types* actually changed; parameter-only updates
    # (slider drags, palette swap) preserve zoom / camera.
    # ``coordinateSystem`` is part of the signature because a polar bar
    # and a cartesian bar both have ``type: "bar"`` — without it, a
    # polar→cartesian transition would skip the clear and leave the
    # previous ``polar``/``angleAxis``/``radiusAxis`` components alive,
    # producing a polar render under cartesian axes.
    new_sig = tuple(
        (s.get("type"), s.get("coordinateSystem"))
        for s in merged.get("series", [])
    )
    if getattr(ctx, "_last_series_sig", None) != new_sig:
        if hasattr(ctx, "ctrl_echarts_clear") and ctx.ctrl_echarts_clear:
            ctx.ctrl_echarts_clear()
    ctx._last_series_sig = new_sig

    if isinstance(merged.get("title"), dict):
        merged["title"] = dict(merged["title"])

    if hasattr(ctx, "ctrl_echarts_update") and ctx.ctrl_echarts_update:
        ctx.ctrl_echarts_update(merged)
    else:
        raise RuntimeError(
            "No ctrl_echarts_update available — VizContext not bound to UI"
        )
