# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for pure helper functions — linkable_filenames, temporal info, etc."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

from services.file_manager import linkable_filenames, temporal_subdir
from routes.rooms import (
    _build_temporal_info,
    _get_choregraph_input_ids,
    _resolve_active_pair,
    _extract_url_sources,
)


def _make_uf(name, companions=None, collection_time_mode=None):
    """Create a minimal UserFile-like object."""
    uf = MagicMock()
    uf.original_name = name
    uf.companion_files = json.dumps(companions) if companions else None
    uf.collection_time_mode = collection_time_mode
    return uf


class TestLinkableFilenames:
    def test_single_csv(self):
        uf = _make_uf("data.csv")
        assert linkable_filenames(uf) == ["data.csv"]

    def test_mhd_with_zraw(self):
        uf = _make_uf("scan.mhd", companions=["scan.zraw"])
        result = linkable_filenames(uf)
        assert "scan.mhd" in result
        assert "scan.zraw" in result

    def test_excel_with_parquet_companions(self):
        uf = _make_uf("report.xlsx", companions=["sheet1.parquet", "sheet2.parquet"])
        result = linkable_filenames(uf)
        # Excel is preprocessed — only companions linked
        assert "report.xlsx" not in result
        assert "sheet1.parquet" in result
        assert "sheet2.parquet" in result

    def test_dicom_series(self):
        uf = _make_uf("brain.dcm", companions=["slice1.dcm", "slice2.dcm"])
        result = linkable_filenames(uf)
        assert result == ["brain.dicom"]

    def test_connector_xml_with_csv_companions(self):
        uf = _make_uf("config.xml", companions=["output1.csv", "output2.csv"])
        result = linkable_filenames(uf)
        assert "config.xml" not in result
        assert "output1.csv" in result

    def test_no_companions(self):
        uf = _make_uf("plain.json")
        assert linkable_filenames(uf) == ["plain.json"]

    def test_invalid_companion_json(self):
        uf = MagicMock()
        uf.original_name = "data.csv"
        uf.companion_files = "not-valid-json"
        uf.collection_time_mode = None
        result = linkable_filenames(uf)
        assert result == ["data.csv"]


# ---------------------------------------------------------------------------
# _resolve_active_pair — filesystem + regex, no mocks
# ---------------------------------------------------------------------------


class TestResolveActivePair:
    def test_default_pair_when_no_spec(self, tmp_path):
        cg, spec = _resolve_active_pair(tmp_path, None)
        assert cg == "choregraph.xml"
        assert spec == "specifications.xml"

    def test_default_pair_for_base_spec(self, tmp_path):
        cg, spec = _resolve_active_pair(tmp_path, "specifications.xml")
        assert cg == "choregraph.xml"
        assert spec == "specifications.xml"

    def test_enhanced_spec_with_matching_choregraph(self, tmp_path):
        # Create the timestamped choregraph file
        (tmp_path / "choregraph_20260315_143000.xml").write_text("<cg/>")
        cg, spec = _resolve_active_pair(
            tmp_path, "specificationsEnhanced_20260315_143000.xml"
        )
        assert cg == "choregraph_20260315_143000.xml"
        assert spec == "specificationsEnhanced_20260315_143000.xml"

    def test_enhanced_spec_falls_back_to_base_choregraph(self, tmp_path):
        # No timestamped choregraph exists
        cg, spec = _resolve_active_pair(
            tmp_path, "specificationsEnhanced_20260315_143000.xml"
        )
        assert cg == "choregraph.xml"
        assert spec == "specificationsEnhanced_20260315_143000.xml"

    def test_enhanced_spec_bad_format_returns_default(self, tmp_path):
        cg, spec = _resolve_active_pair(tmp_path, "specificationsEnhanced_bad.xml")
        assert cg == "choregraph.xml"
        assert spec == "specifications.xml"


# ---------------------------------------------------------------------------
# _get_choregraph_input_ids — real XML parsing, no mocks
# ---------------------------------------------------------------------------


class TestGetChoregraphInputIds:
    def test_parses_input_ids(self, tmp_path):
        xml = """<choregraph>
          <inputs>
            <input id="inp_1" location="/ws/sales.csv" />
            <input id="inp_2" location="/ws/inventory.parquet" />
          </inputs>
        </choregraph>"""
        (tmp_path / "choregraph.xml").write_text(xml)
        result = _get_choregraph_input_ids(tmp_path)
        assert result == {"sales": "inp_1", "inventory": "inp_2"}

    def test_missing_file_returns_empty(self, tmp_path):
        assert _get_choregraph_input_ids(tmp_path) == {}

    def test_malformed_xml_returns_empty(self, tmp_path):
        (tmp_path / "choregraph.xml").write_text("not xml at all")
        assert _get_choregraph_input_ids(tmp_path) == {}

    def test_no_location_skipped(self, tmp_path):
        xml = """<choregraph>
          <inputs><input id="x" /></inputs>
        </choregraph>"""
        (tmp_path / "choregraph.xml").write_text(xml)
        assert _get_choregraph_input_ids(tmp_path) == {}


# ---------------------------------------------------------------------------
# _extract_url_sources — real XML parsing, no mocks
# ---------------------------------------------------------------------------


class TestExtractUrlSources:
    def test_extracts_urls(self, tmp_path):
        xml = """<choregraph>
          <inputs>
            <input id="u1" url="https://example.com/data.csv" name="remote" />
            <input id="u2" location="/local/file.csv" />
          </inputs>
        </choregraph>"""
        (tmp_path / "choregraph.xml").write_text(xml)
        result = _extract_url_sources(tmp_path)
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/data.csv"
        assert result[0]["input_id"] == "u1"
        assert result[0]["name"] == "remote"

    def test_no_urls_returns_empty(self, tmp_path):
        xml = """<choregraph>
          <inputs><input id="x" location="/local.csv" /></inputs>
        </choregraph>"""
        (tmp_path / "choregraph.xml").write_text(xml)
        assert _extract_url_sources(tmp_path) == []

    def test_missing_file_returns_empty(self, tmp_path):
        assert _extract_url_sources(tmp_path) == []

    def test_malformed_xml_returns_empty(self, tmp_path):
        (tmp_path / "choregraph.xml").write_text("<<garbage>>")
        assert _extract_url_sources(tmp_path) == []


# ---------------------------------------------------------------------------
# _build_temporal_info — real filesystem grouping, no mocks
# ---------------------------------------------------------------------------


class TestBuildTemporalInfo:
    def test_groups_temporal_files(self, tmp_path):
        uf = _make_uf(
            "timeseries.csv",
            companions=["output00000000_cells.csv", "output00000001_cells.csv",
                         "output00000002_cells.csv"],
            collection_time_mode="index",
        )
        uf.collection_time_delta = None
        uf.file_id = "abc"
        result = _build_temporal_info({"abc": uf}, tmp_path)
        # Should find one group (the _cells.csv suffix)
        assert len(result) >= 1
        first_key = next(iter(result))
        info = result[first_key]
        assert info["time_mode"] == "index"
        assert len(info["all_paths"]) >= 2

    def test_skips_non_temporal(self, tmp_path):
        uf = _make_uf("data.csv")
        uf.collection_time_mode = None
        assert _build_temporal_info({"x": uf}, tmp_path) == {}

    def test_skips_single_file(self, tmp_path):
        uf = _make_uf("data.csv", collection_time_mode="index")
        uf.collection_time_delta = None
        uf.file_id = "x"
        # Only 1 linkable file — no temporal group
        assert _build_temporal_info({"x": uf}, tmp_path) == {}

    def test_empty_dict_returns_empty(self, tmp_path):
        assert _build_temporal_info({}, tmp_path) == {}
