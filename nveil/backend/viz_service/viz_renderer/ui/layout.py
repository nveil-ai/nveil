# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Main UI layout builder for the visualization viewer."""
from pathlib import Path

from trame.widgets import client, deckgl, iframe
from trame_echarts import Chart as EChartsChart
from trame.widgets import vtk as vtk_widgets
from trame_additionnal_widgets import force_graph
from trame_vuetify.ui.vuetify3 import VAppLayout
from trame_vuetify.widgets import vuetify3 as vuetify  # ✅ Corriger ici
from ui.icons import MDI

# CSS file path (relative to viz_renderer folder)
CSS_FILE = Path(__file__).parent.parent / "config/viz.css"


def _load_kpi_css() -> str:
    """Read the shared KPI card stylesheet from the dive package.

    Single source of truth with dive.builder.export so exported
    thumbnails match what's rendered in the viewer.
    """
    try:
        from importlib.resources import files
        return (
            files("dive.builder._html_assets")
            .joinpath("kpi.css")
            .read_text(encoding="utf-8")
        )
    except (ImportError, FileNotFoundError, ModuleNotFoundError):
        return ""

# Vuetify configuration
VUETIFY_CONFIG = {
    "theme": {
        "defaultTheme": "dark",
        "themes": {
            "dark": {
                "colors": {
                    "surface": "#212121",
                },
            },
        },
    },
}


def build_main_layout(app, prefix=""):
    """Build the main Trame UI layout.

    Args:
        app: The main App instance with server, state, ctrl, and render_window.
        prefix: State key prefix (default "main_" for chat mode).
    """
    with VAppLayout(app.server, vuetify_config=VUETIFY_CONFIG) as app_layout:
        client.Style(CSS_FILE.read_text(), type="text/css")
        kpi_css = _load_kpi_css()
        if kpi_css:
            client.Style(kpi_css, type="text/css")

        with vuetify.VLayout() as layout:
            # IFrame communicator for React integration.
            # target_origin must match the React app's browser origin (like the trame-react example).
            from shared.secrets import get_secret
            _gcp = get_secret("GCP", "0")
            _port = "" if _gcp == "1" else ":8000"
            _target_origin = f"https://localhost{_port}"
            comm = iframe.Communicator(enable_rpc=True, target_origin=_target_origin)
            app.ctrl.react_send_event = comm.post_message

            # Handle export trigger from React — executes trame download
            client.Script("""
                window.addEventListener("message", function(e) {
                    if (e.data && e.data.type === "trigger-export-download") {
                        var ext = e.data.format || "jpeg";
                        var mime = ext === "pdf" ? "application/pdf"
                                 : ext === "svg" ? "image/svg+xml"
                                 : "image/" + ext;
                        if (window.trame && window.trame.trigger) {
                            window.trame.trigger("download_export").then(function(result) {
                                if (result) window.trame.utils.download("figure." + ext, result, mime);
                            });
                        }
                    }
                });
            """)

            with vuetify.VMain(style="display:flex"):
                with vuetify.VContainer(fluid=True, classes="pa-0 fill-height", style="position: relative;"):
                    # Main viewer containers
                    with vuetify.VRow(classes="pa-0 fill-height", no_gutters=True):
                        _build_echarts_container(app, prefix)
                        _build_deckgl_container(app, prefix)
                        _build_vtk_container(app, prefix)
                        _build_graph_container(app, prefix)
                        _build_html_container(app, prefix)

                # Widget controls are rendered in React (WidgetPanel)


def _build_history_controls(app, prefix=""):
    """Build the history navigation sheet."""
    with vuetify.VSheet(
        style="position: absolute; display: flex; bottom: 10px; z-index: 1000; left: 10px; border-radius: 40px;",
        no_gutters=True,
    ):
        vuetify.VBtn(
            icon=MDI.CHEVRON_LEFT,
            variant="text",
            density="compact",
            disabled=(f"{prefix}current_history_index <= 0",),
            click=app.previous_viz,
        )
        vuetify.VLabel(
            f"{{{{ {prefix}current_history_index + 1 }}}} / {{{{ {prefix}history_files.length }}}}",
            classes="mx-2 text-caption",
        )
        vuetify.VBtn(
            icon=MDI.CHEVRON_RIGHT,
            variant="text",
            density="compact",
            disabled=(f"{prefix}current_history_index >= {prefix}history_files.length - 1",),
            click=app.next_viz,
        )


def _build_echarts_container(app, prefix="", ctx=None):
    """Build the Apache ECharts viewer container.

    Mounts a <v-chart> Vue component (served by trame_echarts) and binds
    its update() method onto the VizContext so backends can push fresh
    option dicts.
    """
    with vuetify.VContainer(
        v_if=f"{prefix}echarts_viewer_ready",
        fluid=True,
        classes="pt-0 px-0 fill-height echarts-fig-container",
        # ``position: relative`` gives the absolutely-positioned chart div
        # (see trame-echarts.js render()) a positioning context so it
        # resolves against THIS container's dimensions rather than
        # climbing further up the DOM. ``padding-bottom: 44px`` reserves
        # room for the widget toolbar below.
        # style="margin-bottom: 60px!important; position: relative;",
    ):
        # Cursor events are emitted in data-space by trame-echarts.js via a
        # zrender-level listener ({cursor: {x, y}}); the shared
        # on_viz_click/on_viz_hover triggers dispatch to per-mark handlers.
        widget = EChartsChart(
            auto_resize=True,
            click=("on_viz_click", "[$event]"),
            mousemove=("on_viz_hover", "[$event]"),
        )
        if ctx is not None:
            ctx.ctrl_echarts_update = widget.update
            ctx.ctrl_echarts_clear = widget.clear
        else:
            app.ctrl.echarts_update = widget.update
            app.ctrl.echarts_clear = widget.clear
            if hasattr(app, "_main_ctx"):
                app._main_ctx.ctrl_echarts_update = widget.update
                app._main_ctx.ctrl_echarts_clear = widget.clear


def _build_deckgl_container(app, prefix="", ctx=None):
    """Build the DeckGL map viewer container."""
    with vuetify.VContainer(
        v_show=f"{prefix}deckgl_viewer_ready",
        fluid=True,
        classes="pa-0 fill-height",
        style="position: relative;",
    ):
        deckMap = deckgl.Deck(
            style="width: 100vw;", classes="fill-height"
        )

        # Store reference for direct access if needed
        app._deckgl_widget = deckMap

        # Legend overlay - positioned absolutely in top-left using VSheet
        vuetify.VSheet(
            v_if=f"{prefix}deckgl_legend_html",
            v_html=(f"{prefix}deckgl_legend_html",),
            color="transparent",
            style="position: absolute; top: 20px; left: 20px; z-index: 1000; pointer-events: none;",
        )

        def deckupdate(new_deck):
            if hasattr(app.server.state, 'flush'):
                app.server.state.flush()
            deckMap.update(new_deck)

        if ctx is not None:
            ctx.ctrl_deck_update = deckupdate
        else:
            app.ctrl.deck_update = deckupdate
            if hasattr(app, "_main_ctx"):
                app._main_ctx.ctrl_deck_update = deckupdate


def _build_vtk_container(app, prefix="", ctx=None):
    """Build the VTK 3D viewer container with optional MPR sub-views."""
    with vuetify.VCol(
        v_if=f"{prefix}vtk_viewer_ready",
        classes="pa-0 fill-height",
        style="display: flex; flex-direction: row;",
    ):
        # --- MPR sub-views (left column) ---
        from dive.builder.vtk import _PLANES
        real_ctx = ctx if ctx else getattr(app, "_main_ctx", None)
        scene = real_ctx._vtk_scene if real_ctx else None
        with vuetify.VSheet(
            v_show=(f"{prefix}mpr_visible",),
            style="flex: 0 0 33%; display: flex; flex-direction: column; gap: 1px; background: #111;",
        ):
            if scene and scene.mpr_views:
                for plane in _PLANES:
                    view_data = scene.mpr_views.get(plane)
                    if view_data:
                        mpr_rw = view_data["render_window"]
                        with vuetify.VSheet(
                            style="flex: 1; min-height: 0; overflow: hidden; background: #0d0d0d;",
                        ):
                            mpr_view = vtk_widgets.VtkRemoteView(
                                mpr_rw,
                                ref=f"mpr_{plane}_{prefix}",
                                interactive_ratio=1,
                                style="width: 100%; height: 100%;",
                            )
                        real_ctx._mpr_ctrl = getattr(real_ctx, "_mpr_ctrl", {})
                        real_ctx._mpr_ctrl[plane] = mpr_view.update

        # --- Main 3D view ---
        with vuetify.VSheet(classes="pa-0 fill-height", style="flex: 1; min-width: 0;"):
            rw = scene.render_window if scene else None
            view = (
                vtk_widgets.VtkRemoteView(
                    rw,
                    ref=f"view_{prefix}",
                )
                if app.state[f"{prefix}use_remote"]
                else vtk_widgets.VtkLocalView(
                    rw,
                    ref=f"view_{prefix}",
                )
            )
            if ctx is not None:
                ctx.ctrl_view_update = view.update
                ctx.ctrl_view_reset_camera = view.reset_camera
            else:
                app.ctrl.view_update = view.update
                app.ctrl.view_reset_camera = view.reset_camera
                if hasattr(app, "_main_ctx"):
                    app._main_ctx.ctrl_view_update = view.update
                    app._main_ctx.ctrl_view_reset_camera = view.reset_camera


def _build_graph_container(app, prefix="", ctx=None):
    """Build the force-directed graph viewer container."""
    with vuetify.VContainer(
        v_if=f"{prefix}graph_viewer_ready",
        fluid=True,
        classes="pa-0 fill-height",
    ):
        force_graph.ForceGraph(
            server=app.server,
            graph_data=(f"{prefix}graph_data",),
            is_3d=(f"{prefix}is_3d",),
            node_rel_size=10,
            link_width=0.5,
            link_color="color",
            link_directional_arrows=True,
            d3_alpha_decay=0.02,
            cooldown_time=8000,
            enable_node_drag=True,
            enable_navigation_controls=True,
            style="width: 100%; height: 100%;",
        )


def _build_html_container(app, prefix="", ctx=None):
    """Build the HTML/Vuetify card viewer container for KPI-style displays.

    Supports grouped layout: cards are organized into groups (by primary category)
    with section headers, sub-label chips, and z-title captions.
    """
    with vuetify.VContainer(
        v_if=f"{prefix}html_viewer_ready",
        fluid=True,
        classes=(
            f"['pa-6', 'fill-height', 'nveil-kpi-container', "
            f"'nveil-theme-' + ({prefix}PlotTheme || 'deep_blue').replaceAll('_','-')]",
        ),
        style="background: transparent; overflow-y: auto;",
    ):
        with vuetify.VSheet(
            style="max-width: 1600px; margin: 0 auto; width: 100%; flex-direction: column; gap: 42px; display: flex;",
            color="transparent",
            elevation=0,
        ):
            # Iterate over groups
            with vuetify.VSheet(
                v_for=f"(group, gIdx) in {prefix}html_card_groups",
                key="gIdx",
                color="transparent",
                elevation=0,
                classes="mb-2",
            ):
                # Group header (visible only when group has a label)
                with vuetify.VRow(
                    v_if="group.group_label",
                    classes="mt-0 mb-0 px-3",
                    no_gutters=True,
                ):
                    with vuetify.VCol(cols=12):
                        vuetify.VLabel(
                            "{{ group.group_label }}",
                            classes="nveil-kpi-group-label",
                        )
                        vuetify.VDivider(
                            classes="mt-2 mb-1",
                            style="opacity: 0.15;",
                        )

                # Cards row within group
                with vuetify.VRow(
                    justify="space-evenly",
                    align="stretch",
                ):
                    with vuetify.VCol(
                        v_for="(card, cIdx) in group.cards",
                        key="cIdx",
                        cols="12", sm="6", md="4", lg="3",
                        classes="pa-3"
                    ):
                        with vuetify.VCard(
                            classes="nveil-kpi-card d-flex flex-column",
                            v_bind_style="'--card-color: ' + (card.color || 'rgba(99, 102, 241, 0.9)') + ';'",
                        ):
                            # 1. Text-Only Card Content
                            with vuetify.VCardText(
                                v_if="card.is_text_only",
                                classes="text-h5 font-weight-bold d-flex flex-column align-center justify-center fill-height",
                            ):
                                vuetify.VIcon(
                                    MDI.TEXT_BOX_OUTLINE,
                                    size="large",
                                    classes="mb-4 nveil-kpi-icon",
                                )
                                vuetify.VLabel(
                                    "{{ card.label }}",
                                    classes="nveil-kpi-text-label text-wrap text-center",
                                )

                            # 2. Standard KPI Card Content
                            with vuetify.Template(v_else=True):
                                with vuetify.VCardItem(classes="pt-5 px-5 pb-0 w-100"):
                                    # Card title (only when NOT in grouped mode)
                                    with vuetify.VCardTitle(
                                        v_if="!group.group_label",
                                        classes="d-flex justify-space-between align-start",
                                    ):
                                        vuetify.VLabel(
                                            "{{ card.label }}",
                                            classes="nveil-kpi-label text-wrap",
                                        )
                                        vuetify.VIcon(
                                            MDI.CHART_TIMELINE_VARIANT,
                                            size="small",
                                            classes="nveil-kpi-icon-sm opacity-60 ml-2",
                                        )

                                    # Sub-label as colored chip (secondary category)
                                    vuetify.VChip(
                                        "{{ card.sub_label }}",
                                        v_if="card.sub_label",
                                        size="small",
                                        variant="flat",
                                        v_bind_color="card.color || 'primary'",
                                        classes="mt-1 nveil-kpi-chip",
                                    )

                                # Body: The Main Value + z-title caption
                                with vuetify.VCardText(
                                    classes="d-flex flex-column align-center justify-center flex-grow-1 pb-4 pt-2",
                                ):
                                    # Dynamic font-size based on value length to prevent overflow
                                    # Formula: scales from 12cqi for short values down to smaller sizes for long values
                                    vuetify.VSheet(
                                        "{{ card.formatted_value || card.value }}",
                                        color="transparent",
                                        classes="nveil-kpi-value text-center",
                                        v_bind_style="'font-size: ' + Math.max(2.5, Math.min(12, 70 / String(card.formatted_value || card.value).length)) + 'cqi;'",
                                    )
                                    # Z-title: what the value represents
                                    vuetify.VLabel(
                                        "{{ card.z_title }}",
                                        v_if="card.z_title",
                                        classes="nveil-kpi-z-title mt-1",
                                    )




# NOTE: _build_controls_drawer was removed — widget controls are now rendered
# in React via WidgetPanel.  Export dialog will be re-added as a React component.


