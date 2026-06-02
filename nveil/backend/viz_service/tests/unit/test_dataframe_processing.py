# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for dataframe_processing — pure pandas logic."""

import pandas as pd
import numpy as np
import pytest

from helpers.dataframe_processing import (
    aggregate_by_unique_values,
    create_base_dataframe,
    stringify_datetime_columns,
)


# ── aggregate_by_unique_values ───────────────────────────────────────────


class TestAggregate:
    def test_avg(self):
        df = pd.DataFrame({"cat": ["A", "A", "B"], "val": [10, 20, 30]})
        result = aggregate_by_unique_values(df, "cat", func="avg")
        assert len(result) == 2
        a_row = result[result["cat"] == "A"]
        assert a_row["val"].iloc[0] == pytest.approx(15.0)

    def test_sum(self):
        df = pd.DataFrame({"cat": ["A", "A", "B"], "val": [10, 20, 30]})
        result = aggregate_by_unique_values(df, "cat", func="sum")
        assert result[result["cat"] == "A"]["val"].iloc[0] == 30

    def test_count(self):
        df = pd.DataFrame({"cat": ["A", "A", "B"], "val": [10, 20, 30]})
        result = aggregate_by_unique_values(df, "cat", func="count")
        assert result[result["cat"] == "A"]["count"].iloc[0] == 2

    def test_unknown_func_raises(self):
        df = pd.DataFrame({"cat": ["A"], "val": [1]})
        with pytest.raises(ValueError, match="Unknown"):
            aggregate_by_unique_values(df, "cat", func="median")

    def test_missing_column_raises(self):
        df = pd.DataFrame({"x": [1]})
        with pytest.raises(ValueError, match="does not exist"):
            aggregate_by_unique_values(df, "nonexistent")


# ── stringify_datetime_columns ───────────────────────────────────────────


class TestStringifyDatetime:
    def test_converts_datetime(self):
        df = pd.DataFrame({"dt": pd.to_datetime(["2024-01-15", "2024-06-30"])})
        result = stringify_datetime_columns(df)
        assert result["dt"].iloc[0] == "2024-01-15 00:00:00"
        assert not pd.api.types.is_datetime64_any_dtype(result["dt"])

    def test_no_datetime_unchanged(self):
        df = pd.DataFrame({"x": [1, 2], "y": ["a", "b"]})
        result = stringify_datetime_columns(df)
        assert result["x"].dtype == np.int64


# ── create_base_dataframe ────────────────────────────────────────────────


class _FakeFrame:
    """Minimal mock of a VizFrame for testing create_base_dataframe."""

    def __init__(self, n=3, discrete_x=False, discrete_color=False, has_size=False):
        self.x = list(range(n))
        self.y = list(range(n))
        self.z = [0.0] * n
        self.color = list(range(n))
        self.size = list(range(n)) if has_size else []

        self.isXDiscrete = discrete_x
        self.xDiscreteLabels = [f"label_{i}" for i in range(n)] if discrete_x else []
        self.isYDiscrete = False
        self.yDiscreteLabels = []
        self.isZDiscrete = False
        self.zDiscreteLabels = []
        self.useDiscreteColor = discrete_color
        self.labelToColor = {i: f"color_{i}" for i in range(n)} if discrete_color else {}


class TestCreateBaseDataframe:
    def test_numeric(self):
        frame = _FakeFrame(n=5)
        df = create_base_dataframe(frame)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5
        assert set(df.columns) >= {"x", "y", "z", "color"}

    def test_discrete_x_labels(self):
        frame = _FakeFrame(n=3, discrete_x=True)
        df = create_base_dataframe(frame)
        assert df["x"].iloc[0] == "label_0"
        assert df["x"].iloc[2] == "label_2"

    def test_discrete_color_mapping(self):
        frame = _FakeFrame(n=3, discrete_color=True)
        df = create_base_dataframe(frame)
        assert df["color"].iloc[0] == "color_0"

    def test_with_size(self):
        frame = _FakeFrame(n=3, has_size=True)
        df = create_base_dataframe(frame)
        assert "size" in df.columns

    def test_without_size(self):
        frame = _FakeFrame(n=3, has_size=False)
        df = create_base_dataframe(frame)
        assert "size" not in df.columns
