# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the Langfuse circuit breaker + boot seeding in prompt.py.

These exercise the resilience logic added to keep node latency bounded when
Langfuse is unreachable (the ~117s-per-message regression), and the idempotent
boot-time seeding. They monkeypatch the Langfuse client so they never touch the
network and don't require a configured Langfuse / installed SDK.
"""
import llm_processing.prompt as pm


def _reset_breaker():
    pm._LF_DOWN_UNTIL = 0.0


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------
def test_circuit_breaker_marks_down_then_expires(monkeypatch):
    monkeypatch.setenv("LANGFUSE_DOWN_COOLDOWN", "60")
    _reset_breaker()
    assert pm._lf_is_down() is False

    pm._lf_mark_down("test reason")
    assert pm._lf_is_down() is True

    # Simulate the cooldown window elapsing.
    pm._LF_DOWN_UNTIL = pm.time.monotonic() - 1
    assert pm._lf_is_down() is False


def test_cooldown_reads_env_override(monkeypatch):
    monkeypatch.setenv("LANGFUSE_DOWN_COOLDOWN", "123")
    assert pm._lf_down_cooldown_seconds() == 123
    monkeypatch.setenv("LANGFUSE_DOWN_COOLDOWN", "not-a-number")
    assert pm._lf_down_cooldown_seconds() == 60  # falls back to default


def test_langfuse_client_none_when_circuit_open(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING", "1")
    pm._LF_DOWN_UNTIL = pm.time.monotonic() + 999
    assert pm._langfuse_client() is None
    _reset_breaker()


# ---------------------------------------------------------------------------
# fragment() fallback + breaker tripping
# ---------------------------------------------------------------------------
def test_fragment_falls_back_to_yaml_and_trips_breaker(monkeypatch):
    _reset_breaker()
    monkeypatch.setenv("LANGFUSE_TRACING", "1")
    pm.Prompt._templates = {"_fragments": {"tones": {"friendly": "be nice"}}}

    class _FallbackPrompt:
        is_fallback = True
        prompt = "be nice"

    class _FakeClient:
        def get_prompt(self, *a, **k):
            return _FallbackPrompt()

    monkeypatch.setattr(pm, "_langfuse_client", lambda: _FakeClient())

    out = pm.Prompt.fragment("tones", "friendly")
    assert out == "be nice"            # yaml text returned
    assert pm._lf_is_down() is True    # breaker opened on is_fallback
    _reset_breaker()


def test_fragment_undeclared_key_returns_empty_without_network(monkeypatch):
    _reset_breaker()
    monkeypatch.setenv("LANGFUSE_TRACING", "1")
    pm.Prompt._templates = {"_fragments": {"tones": {"friendly": "be nice"}}}

    def _boom():
        raise AssertionError("must not reach Langfuse for an undeclared key")

    monkeypatch.setattr(pm, "_langfuse_client", _boom)
    assert pm.Prompt.fragment("tones", "missing") == ""


# ---------------------------------------------------------------------------
# Boot seeding
# ---------------------------------------------------------------------------
def test_seed_noop_when_tracing_disabled(monkeypatch):
    monkeypatch.setenv("LANGFUSE_TRACING", "")

    def _boom(*a, **k):
        raise AssertionError("reachability must not be probed when tracing is off")

    monkeypatch.setattr(pm, "_langfuse_reachable", _boom)
    pm.seed_langfuse_prompts_if_missing()  # returns cleanly


def test_seed_skips_and_trips_breaker_when_unreachable(monkeypatch):
    _reset_breaker()
    monkeypatch.setenv("LANGFUSE_TRACING", "1")
    pm.Prompt._templates = {"feedback": {"type": "chat", "messages": []}}
    monkeypatch.setattr(pm, "_langfuse_reachable", lambda *a, **k: False)

    reached = {"client": False}
    monkeypatch.setattr(
        pm, "_langfuse_client", lambda: reached.__setitem__("client", True)
    )

    pm.seed_langfuse_prompts_if_missing()
    assert reached["client"] is False   # never built a client
    assert pm._lf_is_down() is True      # breaker opened so runtime fails fast too
    _reset_breaker()


def test_seed_creates_only_missing_prompts(monkeypatch):
    _reset_breaker()
    monkeypatch.setenv("LANGFUSE_TRACING", "1")
    pm.Prompt._templates = {
        "feedback": {"type": "chat", "messages": [{"role": "system", "content": "hi"}]},
        "_fragments": {"tones": {"friendly": "be nice", "formal": "be formal"}},
        "_xml_mapping_rules": {"ignored": 1},  # yaml-only, must be skipped
    }
    monkeypatch.setattr(pm, "_langfuse_reachable", lambda *a, **k: True)

    already_present = {"shared/tones/friendly"}
    created: list[str] = []

    class _FakeClient:
        def get_prompt(self, name, **k):
            class _P:
                is_fallback = name not in already_present
            return _P()

        def create_prompt(self, name, **k):
            created.append(name)

    monkeypatch.setattr(pm, "_langfuse_client", lambda: _FakeClient())

    pm.seed_langfuse_prompts_if_missing()

    assert "feedback" in created                 # missing chat prompt seeded
    assert "shared/tones/formal" in created      # missing fragment seeded
    assert "shared/tones/friendly" not in created  # already present, no version bump
    assert "_xml_mapping_rules" not in created   # yaml-only section skipped
    _reset_breaker()
