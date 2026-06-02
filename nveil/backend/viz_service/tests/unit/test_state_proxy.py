# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for StateProxy — key-prefixing wrapper.

Unit tests use a dict-like stand-in to isolate prefix routing logic.
VizContext integration tests (test_viz_context.py) use real Trame state.
"""

import pytest

vtk = pytest.importorskip("vtk", reason="vtk not installed")
from viz_context import StateProxy


class _DictState:
    """Minimal dict-like object that mimics trame app.state for testing."""

    def __init__(self):
        self._data = {}
        self._dirty_keys = []

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def __contains__(self, key):
        return key in self._data

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        return self._data.get(key)

    def __setattr__(self, key, value):
        if key.startswith("_"):
            object.__setattr__(self, key, value)
        else:
            self._data[key] = value

    def dirty(self, *keys):
        self._dirty_keys.extend(keys)

    def flush(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestStateProxyPrefix:
    def test_getitem_prefixes(self):
        state = _DictState()
        state["panel1_resolution"] = 30
        sp = StateProxy(state, "panel1_")
        assert sp["resolution"] == 30

    def test_setitem_prefixes(self):
        state = _DictState()
        sp = StateProxy(state, "panel1_")
        sp["resolution"] = 50
        assert state["panel1_resolution"] == 50

    def test_getattr_prefixes(self):
        state = _DictState()
        state._data["px_foo"] = "bar"
        sp = StateProxy(state, "px_")
        assert sp.foo == "bar"

    def test_setattr_prefixes(self):
        state = _DictState()
        sp = StateProxy(state, "px_")
        sp.foo = "bar"
        assert state._data["px_foo"] == "bar"

    def test_contains_prefixed(self):
        state = _DictState()
        state["p_key"] = 1
        sp = StateProxy(state, "p_")
        assert "key" in sp
        assert "missing" not in sp

    def test_dirty_prefixes_keys(self):
        state = _DictState()
        sp = StateProxy(state, "p_")
        sp.dirty("a", "b")
        assert state._dirty_keys == ["p_a", "p_b"]

    def test_raw_returns_underlying(self):
        state = _DictState()
        sp = StateProxy(state, "p_")
        assert sp.raw is state


class TestStateProxyEdgeCases:
    def test_empty_prefix_passthrough(self):
        state = _DictState()
        state["resolution"] = 10
        sp = StateProxy(state, "")
        assert sp["resolution"] == 10
        sp["resolution"] = 20
        assert state["resolution"] == 20

    def test_private_attr_not_prefixed(self):
        state = _DictState()
        sp = StateProxy(state, "p_")
        with pytest.raises(AttributeError):
            _ = sp._internal

    def test_clear_all_resets_defaults(self):
        state = _DictState()
        state["p_a"] = 100
        state["p_b"] = 200
        sp = StateProxy(state, "p_")
        sp.clear_all({"a": 0, "b": 0})
        assert state["p_a"] == 0
        assert state["p_b"] == 0
