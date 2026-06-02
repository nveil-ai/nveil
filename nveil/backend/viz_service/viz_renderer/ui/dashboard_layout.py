# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Dashboard layout builder for multi-iframe panel display."""

from trame.widgets import client, iframe
from trame_vuetify.ui.vuetify3 import VAppLayout
from trame_vuetify.widgets import vuetify3 as vuetify
from trame.widgets import deckgl
from trame.widgets import vtk as vtk_widgets
from trame_additionnal_widgets import force_graph
from .icons import MDI

from .layout import (
    CSS_FILE,
    VUETIFY_CONFIG,
    _build_echarts_container,
    _build_deckgl_container,
    _build_vtk_container,
    _build_graph_container,
    _build_html_container,
)

# Vuetify config for dashboard panels: transparent background via theme colors.
# Setting "background" to "0,0,0" with near-zero opacity via CSS ensures
# the Vuetify theme layer doesn't paint an opaque background.
PANEL_VUETIFY_CONFIG = {
    "theme": {
        "defaultTheme": "dark",
        "themes": {
            "dark": {
                "colors": {
                    "background": "#00000000",
                    "surface": "#00000000",
                },
            },
        },
    },
}


def build_dashboard_layout(app):
    """Minimal default layout for dashboard mode.

    Panels are rendered in separate iframes via ?ui=dock_{panel_id}.
    Uses a named template to avoid overwriting the default chat layout.
    """
    with VAppLayout(app.server, template_name="dashboard_shell", vuetify_config=VUETIFY_CONFIG) as app_layout:
        client.Style(CSS_FILE.read_text(), type="text/css")
        from shared.secrets import get_secret
        _gcp = get_secret("GCP", "0")
        _port = "" if _gcp == "1" else ":8000"
        _target_origin = f"https://localhost{_port}"
        comm = iframe.Communicator(enable_rpc=True, target_origin=_target_origin)
        app.ctrl.react_send_event = comm.post_message
        with vuetify.VMain(style="display:flex; height:100vh;"):
            vuetify.VContainer(fluid=True, classes="pa-0 fill-height")
    return app_layout


def create_panel_template(app, ctx):
    """Create a VAppLayout page for one dashboard panel.

    Each panel is a full standalone Vuetify page accessible via
    ``?ui=dock_{panel_id}``.  This is necessary because each panel
    is loaded in its own iframe and Vuetify components (VContainer,
    VSheet, etc.) require a ``<v-app>`` ancestor to render.

    Args:
        app: The main App instance.
        ctx: VizContext for this panel.

    Returns:
        template_name: The layout name (used as ``?ui=`` value).
    """
    template_name = f"dock_{ctx.panel_id}"
    prefix = ctx.prefix  # e.g. "panel_1_"

    # CSS override: make the panel iframe background transparent so the
    # dashboard's own backdrop shows through instead of the gradient.
    # Must target every layer: html/body, Vue mount (#app), Vuetify theme
    # (.v-theme--dark sets background-color), .v-application, its inner
    # wrapper (.v-application__wrap), and VMain (.v-main).
    PANEL_CSS_OVERRIDE = """
        html, body { background: transparent !important; }
        #app { background: transparent !important; background-image: none !important; }
        .v-theme--dark, .v-theme--light { background: transparent !important; background-color: transparent !important; }
        .v-application { background: transparent !important; background-color: transparent !important; backdrop-filter: none !important; }
        .v-application__wrap { background: transparent !important; }
        .v-main { background: transparent !important; }
    """

    PANEL_ERROR_CSS = """
        .panel-error-overlay {
            position: absolute;
            inset: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: rgba(0, 0, 0, 0.6);
            z-index: 10;
            padding: 24px;
            text-align: center;
        }
        .panel-error-overlay .error-icon {
            font-size: 2rem;
            margin-bottom: 8px;
            opacity: 0.5;
        }
        .panel-error-overlay .error-msg {
            color: #bbb;
            font-size: 0.85rem;
            max-width: 280px;
            line-height: 1.4;
        }
    """

    PANEL_LOADING_CSS = """
        .panel-loading-overlay {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 5;
        }
    """

    with VAppLayout(
        app.server,
        template_name=template_name,
        vuetify_config=PANEL_VUETIFY_CONFIG,
    ) as layout:
        client.Style(CSS_FILE.read_text(), type="text/css")
        client.Style(PANEL_CSS_OVERRIDE, type="text/css")
        client.Style(PANEL_ERROR_CSS, type="text/css")
        client.Style(PANEL_LOADING_CSS, type="text/css")
        with vuetify.VMain(style="display:flex; height:100vh;"):
            with vuetify.VContainer(
                fluid=True,
                classes="pa-0 fill-height",
                style="position:relative; overflow:hidden;",
            ):
                # Loading spinner — shown while no viewer is ready and no error
                no_viewer = (
                    f"!{prefix}vtk_viewer_ready"
                    f" && !{prefix}echarts_viewer_ready && !{prefix}deckgl_viewer_ready"
                    f" && !{prefix}graph_viewer_ready && !{prefix}html_viewer_ready"
                    f" && !{prefix}viz_error"
                )
                with vuetify.VSheet(
                    v_if=no_viewer,
                    classes="panel-loading-overlay",
                    color="transparent",
                ):
                    vuetify.VProgressCircular(
                        indeterminate=True,
                        size=32,
                        width=3,
                        color="grey",
                    )

                # Error overlay — shown when viz_error is set
                with vuetify.VSheet(
                    v_if=f"{prefix}viz_error",
                    classes="panel-error-overlay",
                    color="transparent",
                ):
                    vuetify.VIcon(
                        MDI.ALERT_CIRCLE_OUTLINE,
                        size="36",
                        color="grey",
                        classes="error-icon",
                    )
                    vuetify.VLabel(
                        f"{{{{ {prefix}viz_error }}}}",
                        classes="error-msg",
                    )

                _build_echarts_container(app, prefix=prefix, ctx=ctx)
                _build_deckgl_container(app, prefix=prefix, ctx=ctx)
                _build_vtk_container(app, prefix=prefix, ctx=ctx)
                _build_graph_container(app, prefix=prefix, ctx=ctx)
                _build_html_container(app, prefix=prefix, ctx=ctx)

    return template_name
