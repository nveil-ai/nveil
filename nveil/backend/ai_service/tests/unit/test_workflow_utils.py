# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for workflow_utils — text cleaning and message formatting."""

from llm_processing.graphs.workflow_utils import (
    approximate_tokens,
    clean_message_content,
    format_message_history,
    combine_inputs,
    merge_additional_info,
)


class TestCleanMessageContent:
    def test_empty_string(self):
        assert clean_message_content("") == ""

    def test_none_returns_empty(self):
        assert clean_message_content(None) == ""

    def test_plain_text_unchanged(self):
        assert clean_message_content("Hello world") == "Hello world"

    def test_br_tags_to_newline(self):
        result = clean_message_content("line1<br>line2<br/>line3")
        assert "line1\nline2\nline3" == result

    def test_paragraphs(self):
        result = clean_message_content("<p>First</p><p>Second</p>")
        assert "First" in result
        assert "Second" in result

    def test_headings(self):
        result = clean_message_content("<h1>Title</h1><p>Body</p>")
        assert "Title" in result
        assert "Body" in result
        assert "<h1>" not in result

    def test_lists(self):
        result = clean_message_content("<ul><li>item1</li><li>item2</li></ul>")
        assert "- item1" in result
        assert "- item2" in result

    def test_html_entities(self):
        result = clean_message_content("&amp; &lt; &gt; &quot;")
        assert "& < > \"" == result

    def test_strips_all_remaining_tags(self):
        result = clean_message_content("<div><span>text</span></div>")
        assert result == "text"

    def test_multiple_newlines_collapsed(self):
        result = clean_message_content("a\n\n\n\n\nb")
        assert "\n\n\n" not in result  # 3+ newlines should be collapsed


class TestApproximateTokens:
    def test_empty_string(self):
        assert approximate_tokens("") == 1  # min(1, ...)

    def test_short_string(self):
        assert approximate_tokens("abcd") == 1  # 4 chars → 1 token

    def test_known_length(self):
        assert approximate_tokens("a" * 400) == 100  # 400 chars → 100 tokens

    def test_returns_at_least_one(self):
        assert approximate_tokens("x") == 1


class TestFormatMessageHistory:
    def _msg(self, author, content):
        return {"author_email": author, "content": content}

    def test_basic(self):
        msgs = [self._msg("user@test.com", "Hello")]
        result = format_message_history(msgs)
        assert "[USER]: Hello" in result

    def test_bot_as_ai(self):
        msgs = [self._msg("bot@nveil.bob", "Hi there")]
        result = format_message_history(msgs)
        assert "[AI]:" in result

    def test_nb_message_limit(self):
        msgs = [self._msg("user@test.com", f"msg{i}") for i in range(10)]
        result = format_message_history(msgs, nb_message_to_keep=2)
        assert "msg8" in result
        assert "msg9" in result
        assert "msg0" not in result

    def test_clean_flag_false(self):
        msgs = [self._msg("bot@nveil.bob", "<b>bold</b>")]
        result = format_message_history(msgs, clean=False)
        assert "<b>bold</b>" in result

    def test_clean_flag_true_strips_html(self):
        msgs = [self._msg("bot@nveil.bob", "<b>bold</b>")]
        result = format_message_history(msgs, clean=True)
        assert "<b>" not in result
        assert "bold" in result

    def test_max_tokens_selects_most_recent(self):
        # Each message content is 40 chars → ~10 tokens. Budget of 25 tokens → 2 messages.
        msgs = [self._msg("user@test.com", "a" * 40) for _ in range(5)]
        result = format_message_history(msgs, max_tokens=25)
        # Should include the last 2 messages (~20 tokens), not all 5 (~50 tokens)
        lines = [l for l in result.strip().splitlines() if l.startswith("[USER]:")]
        assert len(lines) == 2

    def test_max_tokens_chronological_order(self):
        msgs = [self._msg("user@test.com", f"msg{i}") for i in range(5)]
        result = format_message_history(msgs, max_tokens=10)
        # Most recent selected messages must appear in chronological order
        idx3 = result.find("msg3")
        idx4 = result.find("msg4")
        assert idx3 < idx4

    def test_max_tokens_always_includes_at_least_one(self):
        # A single message that far exceeds the budget must still be included
        msgs = [self._msg("user@test.com", "x" * 4000)]  # ~1000 tokens
        result = format_message_history(msgs, max_tokens=5)
        assert "[USER]:" in result

    def test_max_tokens_empty_history(self):
        assert format_message_history([], max_tokens=100) == ""

    def test_max_tokens_takes_precedence_over_nb_message_to_keep(self):
        # nb_message_to_keep=1 would keep only last msg; max_tokens=10000 keeps all
        msgs = [self._msg("user@test.com", f"msg{i}") for i in range(5)]
        result = format_message_history(msgs, nb_message_to_keep=1, max_tokens=10000)
        assert "msg0" in result  # all messages present

    def test_max_tokens_counts_on_cleaned_text_for_bot(self):
        # Bot message: 40 meaningful chars wrapped in HTML tags → ~10 tokens after cleaning.
        # If we counted raw HTML the tag overhead would inflate the estimate and exclude it wrongly.
        html_content = "<p>" + "a" * 40 + "</p>"  # raw: 48 chars, cleaned: 40 chars
        msgs = [self._msg("bot@nveil.bob", html_content)]
        # Budget of 12 tokens comfortably covers 10 cleaned tokens but not 12 raw tokens
        result = format_message_history(msgs, max_tokens=12)
        assert "[AI]:" in result

    def test_nb_message_to_keep_still_works_without_max_tokens(self):
        msgs = [self._msg("user@test.com", f"msg{i}") for i in range(5)]
        result = format_message_history(msgs, nb_message_to_keep=2)
        assert "msg3" in result
        assert "msg4" in result
        assert "msg0" not in result


class TestCombineInputs:
    def test_none_returns_empty(self):
        assert combine_inputs(None) == ""

    def test_empty_dict(self):
        assert combine_inputs({}) == ""

    def test_single_value(self):
        result = combine_inputs({"key": "value"})
        assert result == "value"

    def test_multiple_values_joined(self):
        result = combine_inputs({"a": "x", "b": "y"})
        assert "x" in result
        assert "y" in result

    def test_empty_values_filtered(self):
        result = combine_inputs({"a": "x", "b": "", "c": "z"})
        assert result == "x;z"


class TestMergeAdditionalInfo:
    def test_d1_none(self):
        assert merge_additional_info(None, {"a": "1"}) == {"a": "1"}

    def test_d2_none(self):
        assert merge_additional_info({"a": "1"}, None) == {"a": "1"}

    def test_disjoint_keys(self):
        result = merge_additional_info({"a": "1"}, {"b": "2"})
        assert result == {"a": "1", "b": "2"}

    def test_overlapping_keys_concatenated(self):
        result = merge_additional_info({"a": "old"}, {"a": "new"})
        assert "old" in result["a"]
        assert "new" in result["a"]
        assert " ; " in result["a"]
