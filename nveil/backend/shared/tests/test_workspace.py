# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for shared.workspace — path construction, symlinks, metadata, cleanup.

Real filesystem via tmp_path + monkeypatched DIVE_PATH. No mocks.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

import shared.workspace as ws_mod


@pytest.fixture(autouse=True)
def set_dive_path(tmp_path, monkeypatch):
    """Redirect DIVE_PATH to tmp_path for all tests."""
    monkeypatch.setattr(ws_mod, "DIVE_PATH", str(tmp_path))


# ---------------------------------------------------------------------------
# Path construction
# ---------------------------------------------------------------------------


class TestPathConstruction:
    def test_workspace_path(self, tmp_path):
        p = ws_mod.workspace_path("owner1", "room1")
        assert p == tmp_path / "owner1" / "workspaces" / "room1"

    def test_panel_workspace_path(self, tmp_path):
        p = ws_mod.panel_workspace_path("o", "dash", "p1")
        assert p == tmp_path / "o" / "workspaces" / "dash" / "panels" / "p1"

    def test_user_file_path(self, tmp_path):
        p = ws_mod.user_file_path("owner1", "file-uuid")
        assert p == tmp_path / "owner1" / "data" / "file-uuid"

    def test_temporal_data_path(self, tmp_path):
        ws = tmp_path / "ws"
        p = ws_mod.temporal_data_path(ws, "_temporal_data")
        assert p == ws / "pipeline" / "inputs" / "_temporal_data"

    def test_metadata_path(self, tmp_path):
        p = ws_mod.metadata_path("o", "r")
        assert p == tmp_path / "o" / "workspaces" / "r" / "metadata.json"

    def test_specs_xml_path(self, tmp_path):
        p = ws_mod.specs_xml_path("o", "r")
        assert p.name == "specifications.xml"

    def test_choregraph_xml_path(self, tmp_path):
        p = ws_mod.choregraph_xml_path("o", "r")
        assert p.name == "choregraph.xml"


# ---------------------------------------------------------------------------
# Symlink operations
# ---------------------------------------------------------------------------


class TestLinkDataFile:
    def test_creates_symlink(self, tmp_path):
        # Set up data store with a real file
        store = ws_mod.user_file_path("owner", "fid")
        store.mkdir(parents=True)
        (store / "data.csv").write_text("a,b\n1,2")

        links = ws_mod.link_data_file("owner", "room", "fid", ["data.csv"])
        assert len(links) == 1
        assert links[0].is_symlink()
        assert links[0].read_text() == "a,b\n1,2"

    def test_creates_workspace_dir(self, tmp_path):
        store = ws_mod.user_file_path("owner", "fid")
        store.mkdir(parents=True)
        (store / "x.csv").write_text("data")

        ws_mod.link_data_file("owner", "newroom", "fid", ["x.csv"])
        ws = ws_mod.workspace_path("owner", "newroom")
        assert ws.exists()

    def test_raises_if_store_missing(self, tmp_path):
        with pytest.raises(OSError, match="Data store directory not found"):
            ws_mod.link_data_file("owner", "room", "nonexistent", ["f.csv"])

    def test_skips_missing_companion(self, tmp_path):
        store = ws_mod.user_file_path("owner", "fid")
        store.mkdir(parents=True)
        (store / "main.mhd").write_text("header")
        # companion .zraw doesn't exist

        links = ws_mod.link_data_file("owner", "room", "fid", ["main.mhd", "main.zraw"])
        assert len(links) == 1  # only main.mhd linked

    def test_replaces_existing_symlink(self, tmp_path):
        store = ws_mod.user_file_path("owner", "fid")
        store.mkdir(parents=True)
        (store / "data.csv").write_text("v1")

        ws_mod.link_data_file("owner", "room", "fid", ["data.csv"])
        # Update content and re-link
        (store / "data.csv").write_text("v2")
        ws_mod.link_data_file("owner", "room", "fid", ["data.csv"])

        ws = ws_mod.workspace_path("owner", "room")
        assert (ws / "data.csv").read_text() == "v2"

    def test_subdir_creates_temporal_path(self, tmp_path):
        store = ws_mod.user_file_path("owner", "fid")
        store.mkdir(parents=True)
        (store / "frame.csv").write_text("t,v")

        links = ws_mod.link_data_file("owner", "room", "fid", ["frame.csv"], subdir="_temporal_ts")
        assert "pipeline" in str(links[0])
        assert "inputs" in str(links[0])

    def test_dicom_symlinks_to_directory(self, tmp_path):
        store = ws_mod.user_file_path("owner", "fid")
        store.mkdir(parents=True)
        (store / "slice.dcm").write_text("dicom")

        links = ws_mod.link_data_file("owner", "room", "fid", ["brain.dicom"])
        assert len(links) == 1
        # .dicom symlinks to the store directory itself
        assert links[0].resolve() == store.resolve()


class TestUnlinkDataFile:
    def test_removes_symlink(self, tmp_path):
        store = ws_mod.user_file_path("owner", "fid")
        store.mkdir(parents=True)
        (store / "data.csv").write_text("data")
        ws_mod.link_data_file("owner", "room", "fid", ["data.csv"])

        ws_mod.unlink_data_file("owner", "room", ["data.csv"])
        ws = ws_mod.workspace_path("owner", "room")
        assert not (ws / "data.csv").exists()

    def test_noop_if_not_exists(self, tmp_path):
        ws = ws_mod.workspace_path("owner", "room")
        ws.mkdir(parents=True)
        ws_mod.unlink_data_file("owner", "room", ["nonexistent.csv"])  # no error


# ---------------------------------------------------------------------------
# retarget_xml_paths
# ---------------------------------------------------------------------------


class TestRetargetXmlPaths:
    def test_replaces_prefix(self, tmp_path):
        f = tmp_path / "spec.xml"
        f.write_text('<input location="/old/path/data.csv" />')
        changed = ws_mod.retarget_xml_paths(f, "/old/path", "/new/path")
        assert changed is True
        assert "/new/path/data.csv" in f.read_text()

    def test_no_match_returns_false(self, tmp_path):
        f = tmp_path / "spec.xml"
        f.write_text('<input location="/other/data.csv" />')
        changed = ws_mod.retarget_xml_paths(f, "/old", "/new")
        assert changed is False

    def test_missing_file_returns_false(self, tmp_path):
        assert ws_mod.retarget_xml_paths(tmp_path / "nope.xml", "/a", "/b") is False


# ---------------------------------------------------------------------------
# Metadata I/O
# ---------------------------------------------------------------------------


class TestMetadata:
    def test_read_missing_returns_empty(self, tmp_path):
        assert ws_mod.read_metadata("o", "r") == {}

    def test_read_field_missing_returns_none(self, tmp_path):
        assert ws_mod.read_metadata("o", "r", "key") == {"key": None}

    def test_write_then_read(self, tmp_path):
        ws_mod.write_metadata("o", "r", {"version": 2, "name": "test"})
        data = ws_mod.read_metadata("o", "r")
        assert data["version"] == 2
        assert data["name"] == "test"

    def test_write_merges(self, tmp_path):
        ws_mod.write_metadata("o", "r", {"a": 1})
        ws_mod.write_metadata("o", "r", {"b": 2})
        data = ws_mod.read_metadata("o", "r")
        assert data == {"a": 1, "b": 2}

    def test_read_field(self, tmp_path):
        ws_mod.write_metadata("o", "r", {"x": 42, "y": 99})
        assert ws_mod.read_metadata("o", "r", "x") == {"x": 42}

    def test_read_corrupt_json(self, tmp_path):
        path = ws_mod.metadata_path("o", "r")
        path.parent.mkdir(parents=True)
        path.write_text("not json{{{")
        assert ws_mod.read_metadata("o", "r") == {}


# ---------------------------------------------------------------------------
# Pipeline cleanup
# ---------------------------------------------------------------------------


class TestCleanPipelineOutputs:
    def test_removes_data_and_cache(self, tmp_path):
        ws = ws_mod.workspace_path("o", "r")
        for sub in ("pipeline/data", "pipeline/cache"):
            (ws / sub).mkdir(parents=True)
            (ws / sub / "output.parquet").write_text("data")

        ws_mod.clean_pipeline_outputs("o", "r")
        # Dirs recreated but empty
        assert (ws / "pipeline" / "data").exists()
        assert not list((ws / "pipeline" / "data").iterdir())
        assert (ws / "pipeline" / "cache").exists()
        assert not list((ws / "pipeline" / "cache").iterdir())

    def test_noop_if_no_pipeline(self, tmp_path):
        ws_mod.clean_pipeline_outputs("o", "nonexistent")  # no error


# ---------------------------------------------------------------------------
# Workspace versioning
# ---------------------------------------------------------------------------


class TestVersioning:
    def test_default_version_is_1(self, tmp_path):
        assert ws_mod.get_workspace_version("o", "r") == 1

    def test_stamp_and_read(self, tmp_path):
        ws_mod.stamp_workspace_version("o", "r")
        assert ws_mod.get_workspace_version("o", "r") == ws_mod.CURRENT_WORKSPACE_VERSION
