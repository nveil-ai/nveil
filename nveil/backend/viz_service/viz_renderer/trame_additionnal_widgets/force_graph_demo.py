# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
from pathlib import Path

# Add parent directory to path to allow for package discovery
# This MUST be at the top before other project imports.
sys.path.insert(0, str(Path(__file__).parent.absolute()))

import force_graph  # Single, clean import
from trame.app import get_server
from trame_vuetify.ui.vuetify3 import SinglePageLayout
from trame_vuetify.widgets import vuetify3 as vuetify

# 1. Get a server and set up the module immediately
server = get_server(client_type="vue3")
force_graph.setup(server)

# 2. Get state and controller AFTER setup
state, ctrl = server.state, server.controller

# 3. Initialize state variables
state.graph_data = {
    "nodes": [{"id": i, "name": f"Node {i}"} for i in range(20)],
    "links": [{"source": i, "target": (i+1) % 20} for i in range(20)]
}
state.is_3d = False

# Add trigger state variables for each action
state.trigger_toggle_3d = 0
state.trigger_update_data = 0
state.trigger_zoom_to_fit = 0
state.trigger_focus_on = 0

# 5. Create UI
with SinglePageLayout(server) as layout:
    layout.title.set_text("Enhanced Force Graph Widget Test")

    # Create toolbar buttons that update state variables
    with layout.toolbar:
        vuetify.VSpacer()
        vuetify.VBtn("2D/3D", click="trigger_toggle_3d += 1")
        vuetify.VBtn("Random Data", click="trigger_update_data += 1")
        vuetify.VBtn("Zoom To Fit", click="trigger_zoom_to_fit += 1")
        vuetify.VBtn("Focus on Node 5", click="trigger_focus_on += 1")

    with layout.content:
        with vuetify.VContainer(fluid=True, classes="pa-0 fill-height"):
            # Create the graph widget
            graph = force_graph.ForceGraph(
                server=server,
                graph_data=("graph_data",),
                is_3d=("is_3d",),
                
                # Node styling
                node_color="blue", 
                node_rel_size=8,
                
                # Link styling
                link_width=2,
                link_directional_arrows=True,
                
                # Physics options
                d3_alpha_decay=0.02,
                cooldown_time=3000,
                
                # Other options
                enable_node_drag=True,
                enable_navigation_controls=True,
                
                style="width: 100%; height: 100%;",
            )
            
            # Register state change handlers that call graph methods
            @state.change("trigger_toggle_3d")
            def on_toggle_3d(trigger_toggle_3d, **kwargs):
                if trigger_toggle_3d > 0:
                    graph.toggle_3d()
            
            @state.change("trigger_update_data")
            def on_update_data(trigger_update_data, **kwargs):
                if trigger_update_data > 0:
                    graph.update_data()
            
            @state.change("trigger_zoom_to_fit")
            def on_zoom_to_fit(trigger_zoom_to_fit, **kwargs):
                if trigger_zoom_to_fit > 0:
                    graph.zoom_to_fit()
            
            @state.change("trigger_focus_on")
            def on_focus_on(trigger_focus_on, **kwargs):
                if trigger_focus_on > 0:
                    graph.focus_on(5)

# 6. Start server
if __name__ == "__main__":
    server.start()
