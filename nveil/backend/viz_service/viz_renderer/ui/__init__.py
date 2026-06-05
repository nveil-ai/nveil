# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-License-Identifier: AGPL-3.0-or-later

# UI layout builders — lazy imports to avoid loading Trame widgets at module level.
# viz_context.py only needs ui.icons, not the full layout module.


def __getattr__(name):
    if name in (
        "build_main_layout",
        "CSS_FILE",
        "VUETIFY_CONFIG",
        "_build_echarts_container",
        "_build_deckgl_container",
        "_build_vtk_container",
        "_build_graph_container",
        "_build_html_container",
    ):
        from .layout import (
            build_main_layout,
            CSS_FILE,
            VUETIFY_CONFIG,
            _build_echarts_container,
            _build_deckgl_container,
            _build_vtk_container,
            _build_graph_container,
            _build_html_container,
        )
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
