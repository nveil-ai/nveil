# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for graph compilation — verify the UserRequest graph compiles and has expected nodes."""

import pytest
from unittest.mock import AsyncMock, MagicMock

langgraph = pytest.importorskip("langgraph", reason="langgraph not installed")

from llm_processing.graphs.workflow_request import UserRequest


def _mock_deps():
    """Create mock dependencies for Workflow constructors."""
    return dict(
        db=AsyncMock(),
        llm_manager=MagicMock(),
        http_client=AsyncMock(),
        checkpointer=None,  # None is valid — disables checkpoint persistence
    )


class TestUserRequestGraph:
    def test_compiles(self):
        graph = UserRequest(**_mock_deps())
        compiled = graph.compile()
        assert compiled is not None

    def test_has_expected_nodes(self):
        graph = UserRequest(**_mock_deps())
        compiled = graph.compile()
        node_names = set(compiled.nodes.keys())
        # Core nodes
        assert "initialize_processing_state" in node_names
        assert "entry_classif_message_type" in node_names
        assert "expand_shortcut_node" in node_names
        assert "planning_transformation_node" in node_names
        assert "transformation_clarification_gate" in node_names
        assert "trigger_choregraph_run_node" in node_names
        assert "exclusion_processing" in node_names
        assert "viz_processing_branch" in node_names
        assert "asp_solving_node" in node_names
        assert "viz_building_node" in node_names
        assert "feedback_node" in node_names
        assert "format_feedback" in node_names
        # Removed ceremony nodes must NOT exist
        assert "continue_processing" not in node_names
        assert "splitter_node" not in node_names
        assert "merge_parallel_results" not in node_names
        assert "feedback_gate" not in node_names
        assert "bypass_feedback_terminal_node" not in node_names
        assert "prepare_processing_state" not in node_names
        assert "prepare_color_palette_processing_state" not in node_names
        assert "prepare_artificial_processing_state" not in node_names
        assert "lambda_node_post_upload_router" not in node_names

    def test_entry_node(self):
        graph = UserRequest(**_mock_deps())
        compiled = graph.compile()
        assert "initialize_processing_state" in compiled.nodes
