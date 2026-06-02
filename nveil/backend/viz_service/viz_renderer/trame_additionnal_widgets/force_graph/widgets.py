# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

import random
import secrets

from trame_client.widgets.core import AbstractElement


class ForceGraph(AbstractElement):
    """
    A Trame widget for 2D and 3D force-directed graphs.
    
    Attributes:
        graph_data (dict): The nodes and links data for the graph
        is_3d (bool): Whether to render as a 3D graph
        node_color (str): Node color (CSS)
        node_auto_color_by (str): Field to automatically color nodes by
        node_rel_size (float): Node relative size
        node_val (str): Node value field for size
        link_color (str): Link color (CSS)
        link_auto_color_by (str): Field to automatically color links by
        link_width (float): Link line width
        link_directional_arrows (bool): Show directional arrows on links
        dag_mode (str): DAG layout mode (null, 'td', 'bu', 'lr', 'rl', 'radialout', 'radialin')
        dag_level_distance (float): Distance between DAG levels
        background_color (str): Background color (CSS)
        enable_navigation_controls (bool): Enable navigation controls
        enable_node_drag (bool): Enable node dragging
        cooldown_time (float): Simulation cooldown time
        
    Methods:
        update_data(): Updates the graph data with a new dataset
        toggle_3d(): Toggles between 2D and 3D visualization
        focus_on(node_id): Centers the graph on a specific node
        zoom_to_fit(duration): Adjusts zoom to fit all nodes
    """
    def __init__(self, **kwargs):
        # Set default values
        defaults = {
            # "node_rel_size": 6,
            
            "cooldown_time": 15000,
            "enable_node_drag": True,
            "enable_navigation_controls": True,
            "link_opacity": 1,
            "link_color":"white"
        }
        
        # Apply defaults if not provided in kwargs
        for key, value in defaults.items():
            if key not in kwargs:
                kwargs[key] = value
        
        # Initialize the widget
        super().__init__(
            "force-graph",
            **kwargs,
        )
        
        # Store server reference for controller methods
        self._server = kwargs.get("server", None)
        
        # Register attributes for binding to Vue component
        self._attr_names += [
            # Core attributes
            ("graph_data", ":graph-data"),
            ("is_3d", ":is-3d"),
            
            # Node styling
            ("node_color", ":node-color"),
            ("node_auto_color_by", ":node-auto-color-by"),
            ("node_rel_size", ":node-rel-size"),
            ("node_val", ":node-val"),
            
            # Link styling
            ("link_color", ":link-color"),
            ("link_auto_color_by", ":link-auto-color-by"),
            ("link_width", ":link-width"),
            ("link_directional_arrows", ":link-directional-arrows"),
            ("link_opacity", ":link-opacity"),  # <-- Add this line
            
            # Layout options
            ("dag_mode", ":dag-mode"),
            ("dag_level_distance", ":dag-level-distance"),
            
            # Physics options
            ("d3_alpha_decay", ":d3-alpha-decay"),
            ("d3_velocity_decay", ":d3-velocity-decay"),
            ("warmup_ticks", ":warmup-ticks"),
            ("cooldown_ticks", ":cooldown-ticks"),
            ("cooldown_time", ":cooldown-time"),
            
            # 3D specific options
            ("background_color", ":background-color"),
            ("enable_navigation_controls", ":enable-navigation-controls"),
            ("enable_node_drag", ":enable-node-drag"),
        ]

    def generate_random_data(self, node_count=20, link_count=30):
        """Generate random graph data for testing."""
        rng = secrets.SystemRandom() if "secrets" in globals() else random.SystemRandom()
        nodes = [{"id": i, "name": f"Node {i}"} for i in range(node_count)]
        links = [
            {"source": i, "target": rng.randint(0, node_count-1)} 
            for i in range(link_count)
        ]
        return {"nodes": nodes, "links": links}
    
    def update_data(self):
        """Update the graph with new random data."""
        if self._server is None:
            return
            
        # Find the state variable for graph_data
        state_var = None
        for attr in self._attributes:
            if attr.name == "graph_data" and isinstance(attr.value, str) and attr.value.startswith("("):
                # Extract variable name from ("variable_name",)
                state_var = attr.value.strip("()").strip("'\"")
                break
                
        if state_var:
            self._server.state[state_var] = self.generate_random_data()
    
    def toggle_3d(self):
        """Toggle between 2D and 3D visualization."""
        if self._server is None:
            return
            
        # Find the state variable for is_3d
        state_var = None
        
        # Properly iterate through the dictionary
        for attr, value in self._attributes.items():
            if attr == "is_3d" and isinstance(value, str):
                # Extract variable name from ":is-3d="is_3d""
                if '="' in value and '"' in value.split('="')[1]:
                    state_var = value.split('="')[1].split('"')[0]
                    break
                    
        if state_var:
            self._server.state[state_var] = not self._server.state[state_var]
    
    def zoom_to_fit(self, duration=1000):
        """Adjust zoom to fit all nodes in the view."""
        if self._server is None:
            return
            
        # Execute client-side method using proper Vue 3 component access
        self._server.js_call("(() => { const el = document.querySelector('force-graph'); if (el && el.__vue__) { el.__vue__.zoomToFit(" + str(duration) + "); }})()")
    
    def focus_on(self, node_id, duration=1000):
        """Focus the graph on a specific node."""
        if self._server is None:
            return
            
        # Execute client-side method using proper Vue 3 component access
        self._server.js_call("(() => { const el = document.querySelector('force-graph'); if (el && el.__vue__) { el.__vue__.focusOn(" + str(node_id) + ", " + str(duration) + "); }})()")
