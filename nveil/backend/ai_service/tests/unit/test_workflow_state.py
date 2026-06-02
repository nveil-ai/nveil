# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for workflow_state.merge_dicts — the core state merging function."""

from llm_processing.graphs.workflow_state import merge_dicts


class TestMergeDictsBasic:
    def test_both_empty(self):
        assert merge_dicts({}, {}) == {}

    def test_a_empty(self):
        assert merge_dicts({}, {"x": 1}) == {"x": 1}

    def test_b_empty(self):
        assert merge_dicts({"x": 1}, {}) == {"x": 1}

    def test_disjoint_keys(self):
        result = merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}


class TestMergeDictsLists:
    def test_list_concatenation(self):
        result = merge_dicts({"items": [1, 2]}, {"items": [3, 4]})
        assert set(result["items"]) == {1, 2, 3, 4}

    def test_list_dedup_hashable(self):
        result = merge_dicts({"items": [1, 2, 3]}, {"items": [2, 3, 4]})
        assert sorted(result["items"]) == [1, 2, 3, 4]

    def test_list_dedup_unhashable_dicts(self):
        d1 = {"items": [{"id": 1}]}
        d2 = {"items": [{"id": 1}, {"id": 2}]}
        result = merge_dicts(d1, d2)
        assert {"id": 1} in result["items"]
        assert {"id": 2} in result["items"]


class TestMergeDictsStrings:
    def test_string_prefers_b(self):
        result = merge_dicts({"msg": "old"}, {"msg": "new"})
        assert result["msg"] == "new"

    def test_string_b_empty_keeps_a(self):
        result = merge_dicts({"msg": "value"}, {"msg": ""})
        assert result["msg"] == "value"


class TestMergeDictsNested:
    def test_recursive_nested_dicts(self):
        a = {"outer": {"inner": "a_val", "only_a": True}}
        b = {"outer": {"inner": "b_val", "only_b": False}}
        result = merge_dicts(a, b)
        assert result["outer"]["inner"] == "b_val"
        assert result["outer"]["only_a"] is True
        assert result["outer"]["only_b"] is False


class TestMergeDictsOther:
    def test_other_type_b_overrides(self):
        result = merge_dicts({"val": 10}, {"val": 20})
        assert result["val"] == 20

    def test_none_value_keeps_a(self):
        result = merge_dicts({"val": 10}, {"val": None})
        assert result["val"] == 10
