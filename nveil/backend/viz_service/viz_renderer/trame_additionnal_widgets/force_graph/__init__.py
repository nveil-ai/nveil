# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys

from . import module
from .widgets import ForceGraph

# Expose the module attributes at the package level
serve = module.serve
scripts = module.scripts

__all__ = [
    "ForceGraph",
]

def setup(server, **kwargs):
    """
    Setup the force_graph module.
    """
    server.enable_module(sys.modules[__name__])

def bind_force_graph_controls(ctrl, state, graph):
    """Register force graph controllers with Trame's controller."""
    @ctrl.add("toggle_3d")
    def toggle_3d():
        graph.toggle_3d()
        
    @ctrl.add("update_data")
    def update_data():
        graph.update_data()
        
    @ctrl.add("zoom_to_fit")
    def zoom_to_fit():
        graph.zoom_to_fit()
        
    @ctrl.add("focus_on")
    def focus_on(node_id=5):
        graph.focus_on(node_id)
    
    # Return something if you need to reference these controllers later
    return {
        "toggle_3d": toggle_3d,
        "update_data": update_data,
        "zoom_to_fit": zoom_to_fit,
        "focus_on": focus_on,
    }
