# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""DeckGL map visualization backend."""
import pandas as pd
import pydeck as pdk


def show_deckgl_viz(ctx, deck_layers, figure_title="", figure_description=""):
    """Render DeckGL map visualization.

    Args:
        ctx: VizContext (or App for backward compat) with state and ctrl_deck_update.
        deck_layers: List of DeckGL layer objects to display.
        figure_title: Optional title string for the map.
        figure_description: Optional description string.
    """
    # Resolve state: prefer VizContext's state_proxy, fall back to app.state
    state = ctx.state_proxy if hasattr(ctx, "state_proxy") and ctx.state_proxy else ctx.state

    # Ensure deck_layers is a flat list (mark builders may return a list of layers
    # as a single markObjects, leading to [[layer1, layer2]] nesting).
    if not isinstance(deck_layers, list):
        deck_layers = [deck_layers]
    flat = []
    for item in deck_layers:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    deck_layers = flat

    # Filter out any None layers and validate data
    valid_layers = []
    legend_html = None

    for layer in deck_layers:
        if layer is None:
            continue
        # Validate layer has data
        layer_data = layer.data
        if layer_data is None:
            continue
        # Check for empty data
        if isinstance(layer_data, pd.DataFrame) and layer_data.empty:
            continue
        if isinstance(layer_data, list) and len(layer_data) == 0:
            continue
        valid_layers.append(layer)

        # Extract legend HTML from layer description if present
        if legend_html is None and hasattr(layer, 'description') and layer.description:
            legend_html = layer.description

    # Always update the legend, even if we have no layers (clears the old one)
    state["deckgl_legend_html"] = legend_html or ""

    # Update legend HTML in state
    state["deckgl_legend_html"] = legend_html or ""

    # Add title overlay HTML if present
    title_html = ""
    if figure_title:
        title_html = f'<div style="position:absolute;top:10px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.6);color:white;padding:6px 16px;border-radius:6px;font-size:16px;font-weight:600;z-index:10;pointer-events:none;">{figure_title}'
        if figure_description:
            title_html += f'<div style="font-size:12px;font-weight:400;opacity:0.85;margin-top:2px;">{figure_description}</div>'
        title_html += '</div>'
    state["deckgl_title_html"] = title_html

    # Extract points for view calculation from the first valid layer.
    # Different layer types store positions under different keys:
    #   ScatterplotLayer / generic : "position"
    #   LineLayer                  : "source" / "target"
    #   PathLayer  (streamlines)   : "path"  (list of [lon, lat] points)
    #   PolygonLayer               : "polygon" (list of [lon, lat] vertices)
    points = []
    if valid_layers:
        deck_data = valid_layers[0].data
        if isinstance(deck_data, pd.DataFrame):
            if "position" in deck_data.columns:
                points = deck_data["position"].tolist()
        elif isinstance(deck_data, list) and deck_data:
            first = deck_data[0]
            if isinstance(first, dict):
                if "position" in first:
                    points = [d["position"] for d in deck_data if d and "position" in d]
                elif "source" in first:
                    points = [d["source"] for d in deck_data if d and "source" in d]
                elif "path" in first:
                    # PathLayer: use first coordinate of each path
                    points = [d["path"][0] for d in deck_data if d and "path" in d and d["path"]]
                elif "polygon" in first:
                    # PolygonLayer: use first vertex of each polygon
                    points = [d["polygon"][0] for d in deck_data if d and "polygon" in d and d["polygon"]]

    # Only compute view state on first render; subsequent updates keep
    # the user's current pan/zoom/tilt by omitting initial_view_state.
    is_first_render = not getattr(ctx, "_deckgl_view_initialized", False)

    if is_first_render:
        if points:
            view = pdk.data_utils.compute_view(points)
        else:
            view = pdk.ViewState(latitude=0, longitude=0, zoom=1)
        # Ensure bearing/pitch are set (required for deck.gl transitions)
        if not hasattr(view, "bearing") or view.bearing is None:
            view.bearing = 0
        if not hasattr(view, "pitch") or view.pitch is None:
            view.pitch = 0
        # Validate: if lat/lon are out of WGS84 range the map will crash.
        # Don't cache the bad view — let the next render recompute it
        # (e.g. after the AI rescales the coordinates).
        lat = getattr(view, "latitude", 0) or 0
        lon = getattr(view, "longitude", 0) or 0
        if abs(lat) > 90 or abs(lon) > 180:
            view = pdk.ViewState(latitude=0, longitude=0, zoom=1, bearing=0, pitch=0)
        else:
            ctx._deckgl_view_initialized = True
        ctx._deckgl_last_view = view
        pdkdeck = pdk.Deck(initial_view_state=view, layers=valid_layers)
    else:
        # Layer-only update: reuse last view state so bearing/pitch are
        # always present (pydeck's default omits them, causing deck.gl
        # "bearing is required for transition" errors).
        view = getattr(ctx, "_deckgl_last_view", pdk.ViewState(
            latitude=0, longitude=0, zoom=1, bearing=0, pitch=0))
        pdkdeck = pdk.Deck(initial_view_state=view, layers=valid_layers)

    # Support both VizContext and legacy App
    if hasattr(ctx, "ctrl_deck_update") and ctx.ctrl_deck_update:
        ctx.ctrl_deck_update(pdkdeck)
    elif hasattr(ctx, "ctrl") and ctx.ctrl:
        ctx.ctrl.deck_update(pdkdeck)
    else:
        raise RuntimeError("No ctrl_deck_update available — VizContext not bound to UI")
