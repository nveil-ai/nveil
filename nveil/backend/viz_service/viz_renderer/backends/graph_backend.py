# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Force-directed graph visualization backend."""


def show_graph_viz(ctx, fig):
    """Render force-directed graph visualization.

    Args:
        ctx: VizContext (or App for backward compat) with state.
        fig: List containing graph data objects.
    """
    # Resolve state: prefer VizContext's state_proxy, fall back to app.state
    state = ctx.state_proxy if hasattr(ctx, "state_proxy") and ctx.state_proxy else ctx.state

    state.graph_data = fig[0]["graph_object"]
    state.is_3d = fig[0]["is_3d"]
    state.trigger_update_data += 1
    state.dirty("graph_data", "trigger_update_data")
