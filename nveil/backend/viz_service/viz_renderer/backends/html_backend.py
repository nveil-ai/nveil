# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""HTML/Vuetify card backend for text/KPI display.

This backend renders data as styled Vuetify cards directly in the Trame layout,
providing elegant KPI-style visualizations with dynamic colors and responsive grid.
"""
from logger import INFO, logger


def show_html_viz(ctx, cards_data, figure_title=""):
    """Render Vuetify card widgets by pushing grouped data to state.

    Args:
        ctx: VizContext (or App for backward compat) with state.
        cards_data: List of group dicts, each with:
            - group_label: Header text for the group (empty string = no header)
            - z_title: Label for the value axis
            - cards: List of card dicts (label, sub_label, value, color, etc.)
        figure_title: Optional title string to display above the cards.
    """
    # Resolve state: prefer VizContext's state_proxy, fall back to app.state
    state = ctx.state_proxy if hasattr(ctx, "state_proxy") and ctx.state_proxy else ctx.state

    if not cards_data:
        logger().logp(INFO, "No cards data to render")
        state["html_card_groups"] = []
        state["html_figure_title"] = ""
        return

    total_cards = sum(len(g.get("cards", [])) for g in cards_data)
    logger().logp(INFO, f"Rendering {total_cards} HTML cards in {len(cards_data)} groups")

    state["html_figure_title"] = figure_title or ""
    state["html_card_groups"] = cards_data
    state.dirty("html_card_groups")
