# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for workflow_request_classify — mark scoring and threshold computation."""

import numpy as np
import pandas as pd
import pytest

from llm_processing.graphs.workflow_request_classify import (
    compute_mark_scores,
    normalize_scores,
    compute_adaptative_threshold,
)


# ── Small weights fixture ────────────────────────────────────────────────

@pytest.fixture
def small_df():
    """A 3-keyword x 4-mark test weights matrix."""
    return pd.DataFrame(
        {
            "Point": [1, 0, 1],
            "Line": [0, 1, 1],
            "Bar": [1, 1, 0],
            "Area": [0, 0, 1],
        },
        index=["scatter", "trend", "compare"],
    )


class _FakeKeyword:
    """Mimics an Enum member with a .name attribute."""
    def __init__(self, name):
        self.name = name

class FakeClassification:
    """Mimics LLMResponseClassification with keyword (Enum-like) + confidence."""
    def __init__(self, keyword, confidence):
        self.keyword = _FakeKeyword(keyword)
        self.confidence = confidence


# ── compute_mark_scores ──────────────────────────────────────────────────


class TestComputeMarkScores:
    def test_empty_list(self, small_df):
        result = compute_mark_scores([], df=small_df)
        assert result == {}

    def test_single_keyword(self, small_df):
        items = [FakeClassification("scatter", 0.9)]
        result = compute_mark_scores(items, df=small_df)
        assert "Point" in result
        assert "Bar" in result
        assert "Line" not in result  # scatter maps to Point + Bar

    def test_multiple_keywords_sum(self, small_df):
        items = [
            FakeClassification("scatter", 0.8),
            FakeClassification("compare", 0.6),
        ]
        result = compute_mark_scores(items, df=small_df, agg="sum")
        # scatter → Point(0.8), Bar(0.8)
        # compare → Point(0.6), Line(0.6), Area(0.6)
        # sum: Point=1.4, Bar=0.8, Line=0.6, Area=0.6
        assert result["Point"] == pytest.approx(1.4)
        assert result["Bar"] == pytest.approx(0.8)

    def test_unknown_keyword_skipped(self, small_df):
        items = [FakeClassification("nonexistent", 0.9)]
        result = compute_mark_scores(items, df=small_df)
        assert result == {}

    def test_with_best_stats(self, small_df):
        items = [FakeClassification("scatter", 0.9)]
        scores, best_marks, count_min = compute_mark_scores(
            items, df=small_df, with_best_stats=True
        )
        assert isinstance(scores, dict)
        assert isinstance(best_marks, list)
        assert len(best_marks) > 0

    def test_max_aggregation(self, small_df):
        items = [
            FakeClassification("scatter", 0.8),
            FakeClassification("compare", 0.6),
        ]
        result = compute_mark_scores(items, df=small_df, agg="max")
        # Point: max(0.8, 0.6) = 0.8
        assert result["Point"] == pytest.approx(0.8)


# ── normalize_scores ─────────────────────────────────────────────────────


class TestNormalizeScores:
    def test_empty_dict(self):
        assert normalize_scores({}) == {}

    def test_single_value(self):
        result = normalize_scores({"Point": 5.0})
        assert result["Point"] == 1.0

    def test_range_mapping(self):
        result = normalize_scores({"A": 0, "B": 50, "C": 100})
        # Inverse scaling: lowest raw score → highest normalized
        assert result["A"] == pytest.approx(10.0)
        assert result["C"] == pytest.approx(1.0)


# ── compute_adaptative_threshold ─────────────────────────────────────────


class TestComputeAdaptativeThreshold:
    def test_below_min_returns_zero(self):
        assert compute_adaptative_threshold(0.3, min_score=0.5) == 0

    def test_at_min_returns_small(self):
        result = compute_adaptative_threshold(0.5, min_score=0.5)
        assert result >= 0
        assert result <= 0.5

    def test_high_score_returns_close_to_input(self):
        result = compute_adaptative_threshold(1.0, min_score=0.5)
        assert result > 0.8
        assert result <= 1.0
