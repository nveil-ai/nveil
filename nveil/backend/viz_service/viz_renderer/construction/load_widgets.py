# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

import json

from dive.builder.construction.bar_mark import bar_widget_descriptors
from dive.builder.construction.box_mark import box_widget_descriptors
from dive.builder.construction.candle_mark import candle_widget_descriptors
from dive.builder.construction.choropleth_mark import choropleth_widget_descriptors
from dive.builder.construction.contour_mark import contour_widget_descriptors
from dive.builder.construction.flow_mark import flow_widget_descriptors
from dive.builder.construction.histogram_mark import histogram_widget_descriptors
from dive.builder.construction.line_mark import line_widget_descriptors
from dive.builder.construction.node_mark import node_widget_descriptors
from dive.builder.construction.parallel_mark import parallel_widget_descriptors
from dive.builder.construction.point_mark import point_widget_descriptors
from dive.builder.construction.sector import sector_widget_descriptors
from dive.builder.construction.surface_mark import surface_widget_descriptors
from dive.builder.construction.unigrid_mark import unigrid_widget_descriptors
from dive.builder.construction.voxel import voxel_widget_descriptors
from dive.builder.construction.vector_field import vector_field_widgets_descriptors
from dive.builder.construction.partition_mark import partition_widget_descriptors
from dive.builder.construction.text_mark import text_widget_descriptors
# Map mark class names to their descriptor functions
_DESCRIPTOR_MAP = {
    "Text": text_widget_descriptors,
    "Voxel": voxel_widget_descriptors,
    "PointMark": point_widget_descriptors,
    "Histogram": histogram_widget_descriptors,
    "UniGridMark": unigrid_widget_descriptors,
    "LineMark": line_widget_descriptors,
    "BarMark": bar_widget_descriptors,
    "Surface": surface_widget_descriptors,
    "Contour": contour_widget_descriptors,
    "BoxViolin": box_widget_descriptors,
    "Candle": candle_widget_descriptors,
    "Sector": sector_widget_descriptors,
    "Choropleth": choropleth_widget_descriptors,
    "Node": node_widget_descriptors,
    "VectorField": vector_field_widgets_descriptors,
    "Flow": flow_widget_descriptors,
    "Parallel": parallel_widget_descriptors,
    "Partition": partition_widget_descriptors,
}


def build_widget_descriptors(state, vl):
    """Build JSON widget descriptors for React-side rendering.

    Returns a JSON string of the descriptor array. Each mark type
    provides its own `*_widget_descriptors()` function.

    When the VizLoader has an active timeline (more than one timestep),
    a ``"timeline"`` descriptor is prepended so the frontend can render
    the timeline control bar.
    """
    descriptors = []

    # Timeline descriptor (prepended so it renders first / at the top)
    ts_idx = getattr(vl, "timestep_index", None)
    if ts_idx and ts_idx.count > 1:
        descriptors.append({
            "type": "timeline",
            "key": "timeline_current",
            "playing_key": "timeline_playing",
            "fps_key": "timeline_fps",
            "count": ts_idx.count,
            "labels": ts_idx.labels,
        })

    def _seed(items):
        for item in items:
            key = item.get("key")
            if key and "default" in item:
                state[key] = item["default"]
            children = item.get("children")
            if children:
                _seed(children)

    for mark_frame in vl.currentFrame:
        mark_type = type(getattr(mark_frame, "mark", None)).__name__
        fn = _DESCRIPTOR_MAP.get(mark_type)
        if fn:
            mark_descriptors = fn(state, mark_frame)
            descriptors.extend(mark_descriptors)
            # Each mark's descriptor derives `default` from its XML attributes,
            # so seeding state from those defaults makes the XML the single
            # source of truth on every explicit load (chat, history). Slider
            # edits go through update_viz_for_context and don't re-enter this
            # function, so they survive between loads. Dashboards skip the
            # whole call (only the "main" panel hits build_widget_descriptors),
            # preserving the per-panel widget values saved with the dashboard.
            _seed(mark_descriptors)
    return json.dumps(descriptors, default=str)
