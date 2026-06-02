# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ExclusionFactBuilder — ASP exclusion fact generation."""

from llm_processing.graphs.workflow_request_exclusion import ExclusionFactBuilder


class TestExclusionFactBuilder:
    def setup_method(self):
        self.builder = ExclusionFactBuilder()

    def test_build_fieldid_valid(self):
        facts = self.builder.build_fieldid("1,2", "mark")
        assert len(facts) == 1
        assert 'exclusion_field(1,2,"mark").' in facts[0]

    def test_build_fieldid_no_comma(self):
        facts = self.builder.build_fieldid("invalid", "mark")
        # Should handle gracefully — either empty list or generic fallback
        assert isinstance(facts, list)

    def test_build_dataid(self):
        facts = self.builder.build_dataid("5", "mark")
        assert len(facts) == 1
        assert 'exclusion_data(5,"mark").' in facts[0]

    def test_build_discrete_true(self):
        facts = self.builder.build_discrete("true", "mark")
        assert len(facts) == 1
        assert "exclusion_discrete" in facts[0]

    def test_build_discrete_false(self):
        facts = self.builder.build_discrete("false", "mark")
        assert facts == []

    def test_build_scaletype(self):
        facts = self.builder.build_scaletype("linear", "mark")
        assert len(facts) == 1
        assert "exclusion_scaleType" in facts[0]
        assert "linear" in facts[0]

    def test_build_marktype(self):
        facts = self.builder.build_marktype("Point", "mark")
        assert len(facts) == 1
        assert "exclusion_markType" in facts[0]
        assert "Point" in facts[0]

    def test_build_asp_fact_dispatches(self):
        facts = self.builder.build_asp_fact("dataid", "5", "mark")
        assert len(facts) >= 1
        assert "exclusion_data" in facts[0]

    def test_build_asp_fact_unknown_selector(self):
        facts = self.builder.build_asp_fact("unknown_selector", "val", "scope")
        assert len(facts) >= 1
        # Should use generic fallback
        assert "exclusion_" in facts[0]

    def test_build_asp_fact_empty_scope_defaults_to_star(self):
        facts = self.builder.build_asp_fact("dataid", "5", "")
        assert len(facts) >= 1
        assert '"*"' in facts[0] or "'*'" in facts[0]
