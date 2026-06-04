# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Nveil Setup Wizard — web-based 3-step configuration for .env."""

import json
import re
import threading
from html import escape as html_escape
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import httpx

from compose_utils import (
    WORKSPACE,
    auto_generate,
    get_current_values,
    write_dot_env,
    write_langfuse_env,
)

# ── Field rendering ─────────────────────────────────────────────────────────


def _field(key, label, value, secret=False, optional=False, help_text=""):
    v = html_escape(str(value))
    opt = " (optional)" if optional else ""
    input_type = "password" if secret else "text"
    toggle = (
        '<button type="button" class="toggle-vis" onclick="toggleVis(this)">show</button>'
        if secret
        else ""
    )
    help_html = f'<div class="field-help">{help_text}</div>' if help_text else ""
    return (
        f'<div class="field">'
        f'<label for="{key}">{label}{opt} <span class="key">{key}</span></label>'
        f'{help_html}'
        f'<div class="input-wrap">'
        f'<input type="{input_type}" id="{key}" name="{key}" '
        f'value="{v}" autocomplete="off" spellcheck="false" '
        f"onblur=\"validateField('{key}')\">"
        f"{toggle}"
        f"</div>"
        f'<div class="field-status" id="status-{key}"></div>'
        f"</div>"
    )


def _select(key, label, value, options):
    opts = ""
    for o in options:
        sel = " selected" if o == value else ""
        opts += f'<option value="{o}"{sel}>{o}</option>'
    return (
        f'<div class="field">'
        f'<label for="{key}">{label} <span class="key">{key}</span></label>'
        f'<select id="{key}" name="{key}" '
        f"onchange=\"validateField('{key}')\">"
        f"{opts}</select>"
        f'<div class="field-status" id="status-{key}"></div>'
        f"</div>"
    )


def _dive_field(value):
    v = html_escape(str(value))
    return (
        '<div class="field">'
        '<label for="DATA_PATH">Data storage path '
        '<span class="key">DATA_PATH</span></label>'
        '<div class="dir-input-row">'
        f'<input type="text" id="DATA_PATH" name="DATA_PATH" '
        f'value="{v}" autocomplete="off" spellcheck="false" '
        f'placeholder="Volume name or absolute path (e.g. /home/user/data, C:\\\\Users\\\\me\\\\data)" '
        "onblur=\"validateField('DATA_PATH')\">"
        '<button type="button" class="btn-reset-path" onclick="resetDivePath()"'
        ' title="Reset to default Docker volume">Reset</button>'
        "</div>"
        '<p class="field-hint">Docker volume name (default) or absolute host path '
        "(Linux: /path, Windows: C:\\..., macOS: /Users/...).</p>"
        '<div class="field-status" id="status-DATA_PATH"></div>'
        "</div>"
    )


# ── Provider toggle rendering ──────────────────────────────────────────────

PROVIDERS = [
    {
        "id": "google",
        "name": "Google (Gemini)",
        "hint": (
            'Get a free key at <a href="https://aistudio.google.com/apikey" target="_blank">aistudio.google.com/apikey</a>. '
            "Gemini offers a generous free tier, making it a good default choice."
        ),
        "fields": [("GOOGLE_API_KEY", "API key", True)],
        "boot_order": 1,
    },
    {
        "id": "openai",
        "name": "OpenAI (GPT)",
        "hint": (
            'Get a key at <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com/api-keys</a>. '
            "Requires a paid account with API credits."
        ),
        "fields": [("OPENAI_API_KEY", "API key", True)],
        "boot_order": 2,
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "hint": (
            'Get a key at <a href="https://console.anthropic.com/settings/keys" target="_blank">console.anthropic.com/settings/keys</a>. '
            "Requires a paid account with API credits."
        ),
        "fields": [("ANTHROPIC_API_KEY", "API key", True)],
        "boot_order": 3,
    },
    {
        "id": "mistral",
        "name": "Mistral",
        "hint": (
            'Get a key at <a href="https://console.mistral.ai/api-keys" target="_blank">console.mistral.ai/api-keys</a>.'
        ),
        "fields": [("MISTRAL_API_KEY", "API key", True)],
        "boot_order": 4,
    },
    {
        "id": "ollama",
        "name": "Ollama (local)",
        "hint": (
            "Run LLMs locally on your machine. "
            '<a href="https://ollama.com" target="_blank">Install Ollama</a>, '
            "then <code>ollama pull &lt;model&gt;</code>. "
            "No API key needed &mdash; provide the base URL (e.g. <code>http://host.docker.internal:11434</code>) "
            "and a model tag (e.g. <code>llama3.1</code>)."
        ),
        "fields": [
            ("OLLAMA_BASE_URL", "Base URL", False),
            ("OLLAMA_MODEL", "Model tag", False),
        ],
        "boot_order": 5,
    },
    {
        "id": "llamacpp",
        "name": "llama.cpp (local)",
        "hint": (
            "Connect to a running "
            '<a href="https://github.com/ggerganov/llama.cpp" target="_blank">llama.cpp</a> server. '
            "Provide the base URL (e.g. <code>http://host.docker.internal:8080</code>) "
            "and the model alias configured on the server."
        ),
        "fields": [
            ("LLAMACPP_BASE_URL", "Base URL", False),
            ("LLAMACPP_MODEL", "Model alias", False),
        ],
        "boot_order": 6,
    },
    {
        "id": "custom",
        "name": "Custom (OpenAI-compatible)",
        "hint": (
            "Any OpenAI-compatible endpoint &mdash; OpenRouter, Nebius, Together AI, "
            "vLLM, Azure OpenAI, … Provide the base URL "
            "(e.g. <code>https://openrouter.ai/api/v1</code>), an API key, and the "
            "exact model name expected by that endpoint "
            "(e.g. <code>anthropic/claude-3.5-sonnet</code>)."
        ),
        "fields": [
            ("OPENAI_COMPAT_BASE_URL", "Base URL", False),
            ("OPENAI_COMPAT_API_KEY", "API key", True),
            ("OPENAI_COMPAT_MODEL", "Model name", False),
        ],
        "boot_order": 7,
    },
]

ALL_PROVIDER_FIELD_KEYS = []
for _p in PROVIDERS:
    for _fkey, _, _ in _p["fields"]:
        ALL_PROVIDER_FIELD_KEYS.append(_fkey)


def _render_provider(prov, values):
    pid = prov["id"]
    has_value = any(values.get(fk, "").strip() for fk, _, _ in prov["fields"])
    checked = " checked" if has_value else ""
    fields_html = ""
    for fkey, flabel, secret in prov["fields"]:
        fields_html += _field(fkey, flabel, values.get(fkey, ""), secret=secret)
    display = "block" if has_value else "none"
    order = prov["boot_order"]
    badge = (
        f'<span class="boot-badge">#{order} in boot order</span>'
        if order > 0
        else '<span class="boot-badge no-boot">not in boot order</span>'
    )
    return (
        f'<div class="provider-card" data-provider="{pid}">'
        f'<div class="provider-header">'
        f'<label class="toggle-switch">'
        f'<input type="checkbox" id="toggle-{pid}" onchange="toggleProvider(\'{pid}\')"{checked}>'
        f'<span class="toggle-slider"></span>'
        f'</label>'
        f'<span class="provider-name">{prov["name"]}</span>'
        f'{badge}'
        f'</div>'
        f'<div class="provider-body" id="body-{pid}" style="display:{display}">'
        f'<div class="provider-hint">{prov["hint"]}</div>'
        f'{fields_html}'
        f'<button type="button" class="btn-test" id="test-{pid}" onclick="testProvider(\'{pid}\')">Test connection</button>'
        f'<span class="test-result" id="test-result-{pid}"></span>'
        f'</div>'
        f'</div>'
    )


# ── Page content ────────────────────────────────────────────────────────────


def _page1_fields(values):
    return _dive_field(values.get("DATA_PATH", "nveil-data"))


def _page2_fields(values):
    html = PROVIDER_PAGE_HEADER
    for prov in PROVIDERS:
        html += _render_provider(prov, values)
    return html


def _langfuse_card(values):
    tracing_on = str(values.get("LANGFUSE_TRACING", "")).strip().lower() in (
        "1", "true", "yes", "on"
    )
    checked = " checked" if tracing_on else ""
    display = "block" if tracing_on else "none"
    hint = (
        "Self-hosted LLM tracing &amp; prompt management &mdash; off by default, "
        "nothing leaves your machine and no credentials are required. When enabled, "
        "start the tracing stack as its own Docker project with "
        "<code>docker compose -p langfuse --profile tracing up -d</code> "
        "(UI at http://localhost:3030, login dev@nveil.com / dev-password)."
    )
    return (
        '<div class="provider-card" data-provider="langfuse">'
        '<div class="provider-header">'
        '<label class="toggle-switch">'
        f'<input type="checkbox" id="toggle-langfuse" onchange="toggleLangfuse()"{checked}>'
        '<span class="toggle-slider"></span>'
        '</label>'
        '<span class="provider-name">LLM tracing (Langfuse)</span>'
        '</div>'
        f'<div class="provider-body" id="body-langfuse" style="display:{display}">'
        f'<div class="provider-hint">{hint}</div>'
        '</div>'
        '</div>'
    )


def _page3_fields(values):
    return (
        _field(
            "POSTGRES_USER", "Database user", values.get("POSTGRES_USER", "nveil"),
            help_text="PostgreSQL superuser name. Used by all services to connect to the database.",
        )
        + _field(
            "POSTGRES_PASSWORD", "Database password", values.get("POSTGRES_PASSWORD", ""), secret=True,
            help_text="Password for the main database user. Auto-generated on first setup.",
        )
        + _field(
            "POSTGRES_DB", "Database name", values.get("POSTGRES_DB", "nveil"),
            help_text="Name of the main PostgreSQL database.",
        )
        + _field(
            "AI_DB_PASSWORD", "AI service database password", values.get("AI_DB_PASSWORD", ""), secret=True,
            help_text="Separate password for the AI service's own database. Isolates AI state from the main DB.",
        )
        + _field(
            "DATABASE_SCHEMA", "Database schema", values.get("DATABASE_SCHEMA", "nveilseption"),
            help_text="PostgreSQL schema used for all application tables.",
        )
        + _field(
            "SECRET_KEY", "JWT secret key (64+ hex)", values.get("SECRET_KEY", ""), secret=True,
            help_text="Used to sign authentication tokens. Auto-generated on first setup. Must be at least 64 hex characters.",
        )
        + _select("ALGORITHM", "JWT algorithm", values.get("ALGORITHM", "HS512"), ["HS256", "HS512"])
        + '<div class="page-title" style="margin-top:1.25rem">LLM tracing (optional)</div>'
        + _langfuse_card(values)
    )


PAGES = [
    {
        "title": "General",
        "desc": "Where your data lives and basic instance settings.",
    },
    {
        "title": "AI Providers",
        "desc": (
            "Enable at least one provider. "
            "Boot order: Google &rarr; OpenAI &rarr; Anthropic &rarr; Mistral &rarr; Ollama "
            "&rarr; llama.cpp &rarr; Custom (OpenAI-compatible)."
        ),
    },
    {
        "title": "Ready to go!",
        "desc": "",
    },
]

PROVIDER_PAGE_HEADER = (
    '<div class="provider-explainer">'
    "<p><strong>Enable at least one AI provider</strong> to power the chat, "
    "analysis, and pipeline features.</p>"
    '<div class="fallback-box">'
    "<strong>How the fallback works:</strong> "
    "At startup, the AI service pings each configured provider in order: "
    "<em>Google &rarr; OpenAI &rarr; Anthropic &rarr; Mistral &rarr; Ollama &rarr; llama.cpp</em>. "
    "The first one that responds becomes the <strong>default provider</strong>."
    "</div>"
    '<p class="fallback-note">Tip: configure multiple providers for redundancy. '
    "If the default goes down, users can switch to another without restarting.</p>"
    "</div>"
)

PAGE_RENDERERS = [_page1_fields, _page2_fields, _page3_fields]


# ── CSS ─────────────────────────────────────────────────────────────────────

CSS = """\
:root {
  --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
  --text: #e1e4ed; --muted: #8b8fa3; --accent: #6c63ff;
  --accent-hover: #5a52e0; --success: #22c55e; --error: #ef4444;
  --input-bg: #12141c;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh;
  display: flex; justify-content: center; padding: 2rem 1rem;
}
.container { max-width: 680px; width: 100%; }
h1 { font-size: 1.6rem; font-weight: 600; margin-bottom: .25rem; }
.subtitle { color: var(--muted); font-size: .875rem; margin-bottom: 1.5rem; }

/* Step indicator */
.steps-bar {
  display: flex; align-items: center; justify-content: center;
  margin-bottom: 1.5rem; gap: 0;
}
.step-indicator {
  display: flex; align-items: center; gap: .4rem;
  padding: .4rem .8rem; border-radius: 20px;
  font-size: .78rem; font-weight: 500; color: var(--muted);
  transition: all .2s;
}
.step-indicator.active {
  background: rgba(108, 99, 255, .15); color: var(--accent);
}
.step-indicator.done { color: var(--success); }
.step-num {
  width: 22px; height: 22px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: .7rem; font-weight: 700;
  background: var(--border); color: var(--muted);
  transition: all .2s;
}
.step-indicator.active .step-num { background: var(--accent); color: #fff; }
.step-indicator.done .step-num { background: var(--success); color: #fff; }
.step-connector { width: 24px; height: 2px; background: var(--border); }

/* Pages */
.page { display: none; }
.page.active { display: block; }
.page-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; padding: 1.25rem;
}
.page-title {
  font-size: .8rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: .08em; color: var(--accent); margin-bottom: .15rem;
}
.page-desc {
  font-size: .8rem; color: var(--muted); margin-bottom: 1rem; line-height: 1.4;
}
.page-desc a { color: var(--accent); text-decoration: none; }
.page-desc a:hover { text-decoration: underline; }

/* Fields */
.field { margin-bottom: .85rem; }
.field:last-child { margin-bottom: 0; }
label {
  display: block; font-size: .78rem; color: var(--muted);
  margin-bottom: .3rem; font-weight: 500;
}
label .key {
  color: var(--text); font-family: 'SF Mono','Fira Code','Consolas',monospace;
  font-size: .72rem; opacity: .5; margin-left: .35rem;
}
input[type="text"], input[type="password"], select {
  width: 100%; padding: .55rem .75rem; font-size: .875rem;
  background: var(--input-bg); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px;
  font-family: 'SF Mono','Fira Code','Consolas',monospace;
  transition: border-color .15s;
}
input:focus, select:focus { outline: none; border-color: var(--accent); }
input.valid, select.valid { border-color: var(--success); }
input.invalid, select.invalid { border-color: var(--error); }
.input-wrap { position: relative; }
.toggle-vis {
  position: absolute; right: .5rem; top: 50%; transform: translateY(-50%);
  background: none; border: none; color: var(--muted); cursor: pointer;
  font-size: .75rem; padding: .2rem .4rem;
}
.toggle-vis:hover { color: var(--text); }
.field-status {
  font-size: .72rem; margin-top: .2rem; margin-left: .1rem; min-height: 1rem;
}
.field-status.valid { color: var(--success); }
.field-status.invalid { color: var(--error); }

/* Navigation */
.nav-bar {
  display: flex; justify-content: space-between;
  margin-top: 1rem; gap: .75rem;
}
.btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: .7rem 1.5rem; font-size: .95rem; font-weight: 600;
  border: none; border-radius: 8px; cursor: pointer;
  transition: background .15s, transform .1s;
}
.btn:active { transform: scale(.98); }
.btn-primary { background: var(--accent); color: #fff; flex: 1; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-secondary { background: var(--border); color: var(--text); }
.btn-secondary:hover { background: var(--surface); }
.btn:disabled { opacity: .4; cursor: not-allowed; }

/* Error banner */
.error-banner {
  display: none; background: rgba(239,68,68,.1);
  border: 1px solid rgba(239,68,68,.3); border-radius: 6px;
  padding: .6rem 1rem; margin-bottom: 1rem;
  font-size: .8rem; color: var(--error);
}
.error-banner.visible { display: block; }

/* Field help text */
.field-help {
  font-size: .72rem; color: var(--muted); margin-bottom: .35rem;
  line-height: 1.4; opacity: .85;
}

/* Provider explainer */
.provider-explainer { margin-bottom: 1rem; }
.provider-explainer p { font-size: .85rem; color: var(--text); line-height: 1.5; margin-bottom: .5rem; }
.fallback-box {
  background: rgba(108, 99, 255, .08); border: 1px solid rgba(108, 99, 255, .25);
  border-radius: 6px; padding: .75rem 1rem; margin: .75rem 0;
  font-size: .8rem; color: var(--text); line-height: 1.5;
}
.fallback-box strong { color: var(--accent); }
.fallback-box em { color: var(--muted); font-style: normal; }
.fallback-note { font-size: .75rem; color: var(--muted); }

/* Provider cards */
.provider-card {
  background: var(--input-bg); border: 1px solid var(--border);
  border-radius: 8px; margin-bottom: .75rem; overflow: hidden;
}
.provider-header {
  display: flex; align-items: center; gap: .75rem;
  padding: .7rem 1rem; cursor: pointer;
}
.provider-name {
  font-size: .9rem; font-weight: 600; color: var(--text);
}
.boot-badge {
  font-size: .65rem; font-weight: 600; padding: .15rem .5rem;
  border-radius: 10px; background: rgba(108, 99, 255, .15);
  color: var(--accent); margin-left: auto; white-space: nowrap;
}
.boot-badge.no-boot {
  background: rgba(139, 143, 163, .15); color: var(--muted);
}
.provider-body {
  padding: 0 1rem 1rem 1rem;
  border-top: 1px solid var(--border);
}
.provider-hint {
  font-size: .75rem; color: var(--muted); margin: .75rem 0;
  line-height: 1.4;
}
.provider-hint a { color: var(--accent); text-decoration: none; }
.provider-hint a:hover { text-decoration: underline; }
.provider-hint code {
  background: var(--border); padding: .1rem .35rem; border-radius: 3px;
  font-size: .72rem;
}

/* Test button */
.btn-test {
  display: inline-flex; align-items: center; margin-top: .5rem;
  padding: .4rem .85rem; font-size: .78rem; font-weight: 600;
  background: var(--border); color: var(--text); border: none;
  border-radius: 5px; cursor: pointer; transition: background .15s;
}
.btn-test:hover { background: var(--accent); color: #fff; }
.btn-test:disabled { opacity: .5; cursor: not-allowed; }
.test-result {
  font-size: .75rem; margin-left: .75rem; vertical-align: middle;
}
.test-result.ok { color: var(--success); }
.test-result.fail { color: var(--error); }

/* Toggle switch */
.toggle-switch {
  position: relative; display: inline-block;
  width: 40px; height: 22px; margin: 0;
}
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider {
  position: absolute; cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--border); border-radius: 22px;
  transition: background .2s;
}
.toggle-slider::before {
  content: ''; position: absolute;
  height: 16px; width: 16px; left: 3px; bottom: 3px;
  background: var(--muted); border-radius: 50%;
  transition: transform .2s, background .2s;
}
.toggle-switch input:checked + .toggle-slider { background: var(--accent); }
.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(18px); background: #fff;
}

/* Ready message (page 3) */
.ready-msg {
  text-align: center; padding: 1.5rem 1rem; margin-bottom: 1rem;
}
.ready-msg h2 {
  color: var(--success); font-size: 1.25rem; margin-bottom: .5rem;
}
.ready-msg p {
  color: var(--muted); font-size: .875rem; line-height: 1.5;
}

/* Unveil section */
.unveil-toggle {
  display: flex; align-items: center; gap: .5rem;
  padding: .75rem 1rem; cursor: pointer;
  background: var(--input-bg); border: 1px solid var(--border);
  border-radius: 8px; margin-bottom: .75rem;
  color: var(--accent); font-size: .85rem; font-weight: 600;
}
.unveil-toggle:hover { background: var(--border); }
.unveil-arrow { transition: transform .2s; }
.unveil-toggle.open .unveil-arrow { transform: rotate(90deg); }
.unveil-content { display: none; }
.unveil-content.open { display: block; }

/* Data path field */
.dir-input-row { display: flex; gap: .5rem; }
.dir-input-row input { flex: 1; }
.btn-reset-path {
  padding: .55rem .85rem; font-size: .8rem; font-weight: 500;
  background: var(--border); color: var(--text); border: none;
  border-radius: 6px; cursor: pointer; white-space: nowrap;
}
.btn-reset-path:hover { background: var(--accent); }
.field-hint {
  margin: .3rem 0 0; font-size: .72rem; color: var(--muted);
}

/* Success card */
.success-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 2.5rem; text-align: center;
  max-width: 500px; margin: 3rem auto;
}
.success-check {
  width: 56px; height: 56px; border-radius: 50%;
  background: rgba(34,197,94,.12); display: flex;
  align-items: center; justify-content: center;
  margin: 0 auto 1.25rem; font-size: 1.75rem; color: var(--success);
}
.success-card h2 { font-size: 1.25rem; margin-bottom: .5rem; }
.success-card p { color: var(--muted); font-size: .9rem; line-height: 1.5; margin-bottom: 1rem; }
.success-card code {
  display: block; background: var(--bg); padding: .6rem 1rem;
  border-radius: 6px; font-size: .85rem; margin: .75rem 0;
  font-family: 'SF Mono','Fira Code','Consolas',monospace; color: var(--text);
}
.success-steps { text-align: left; margin-top: 1.25rem; list-style: none; }
.success-steps li {
  color: var(--muted); font-size: .85rem; margin-bottom: .5rem;
  padding-left: 1.5rem; position: relative;
}
.success-steps li::before {
  content: attr(data-n); position: absolute; left: 0;
  color: var(--success); font-weight: 600;
}
"""

# ── JavaScript ──────────────────────────────────────────────────────────────

JS = """\
var currentPage = 0;
var totalPages = 3;

function isProviderEnabled(pid) {
  var t = document.getElementById('toggle-' + pid);
  return t && t.checked;
}

var validators = {
  DATA_PATH: function(v) {
    if (!v || !v.trim()) return 'Required.';
    v = v.trim();
    // Absolute Linux/macOS path
    if (/^\\/[^\\0]+/.test(v)) return '';
    // Absolute Windows path (C:\, D:\, etc.)
    if (/^[A-Za-z]:[\\\\\/]/.test(v)) return '';
    // Docker volume name (alphanumeric, dash, underscore, dot)
    if (/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(v)) return '';
    return 'Enter a valid absolute path (e.g. /home/user/data, C:\\\\Users\\\\me\\\\data) or a Docker volume name.';
  },
  GOOGLE_API_KEY: function(v) {
    if (!isProviderEnabled('google')) return '';
    if (!v || !v.trim()) return 'Required when Google is enabled.';
    if (!v.startsWith('AIza')) return "Google keys start with 'AIza'.";
    if (v.length < 35 || v.length > 45) return 'Expected ~39 characters.';
    return '';
  },
  OPENAI_API_KEY: function(v) {
    if (!isProviderEnabled('openai')) return '';
    if (!v || !v.trim()) return 'Required when OpenAI is enabled.';
    if (!v.startsWith('sk-')) return "OpenAI keys start with 'sk-'.";
    if (v.length < 20) return 'Key looks too short.';
    return '';
  },
  ANTHROPIC_API_KEY: function(v) {
    if (!isProviderEnabled('anthropic')) return '';
    if (!v || !v.trim()) return 'Required when Anthropic is enabled.';
    if (!v.startsWith('sk-ant-')) return "Anthropic keys start with 'sk-ant-'.";
    if (v.length < 20) return 'Key looks too short.';
    return '';
  },
  MISTRAL_API_KEY: function(v) {
    if (!isProviderEnabled('mistral')) return '';
    if (!v || !v.trim()) return 'Required when Mistral is enabled.';
    if (v.length < 20) return 'Key looks too short.';
    return '';
  },
  OLLAMA_BASE_URL: function(v) {
    if (!isProviderEnabled('ollama')) return '';
    if (!v || !v.trim()) return 'Required when Ollama is enabled.';
    if (!v.startsWith('http://') && !v.startsWith('https://'))
      return 'Must start with http:// or https://.';
    return '';
  },
  OLLAMA_MODEL: function(v) {
    if (!isProviderEnabled('ollama')) return '';
    if (!v || !v.trim()) return 'Required when Ollama is enabled.';
    return '';
  },
  LLAMACPP_BASE_URL: function(v) {
    if (!isProviderEnabled('llamacpp')) return '';
    if (!v || !v.trim()) return 'Required when llama.cpp is enabled.';
    if (!v.startsWith('http://') && !v.startsWith('https://'))
      return 'Must start with http:// or https://.';
    return '';
  },
  LLAMACPP_MODEL: function(v) {
    if (!isProviderEnabled('llamacpp')) return '';
    if (!v || !v.trim()) return 'Required when llama.cpp is enabled.';
    return '';
  },
  OPENAI_COMPAT_BASE_URL: function(v) {
    if (!isProviderEnabled('custom')) return '';
    if (!v || !v.trim()) return 'Required when the custom provider is enabled.';
    if (!v.startsWith('http://') && !v.startsWith('https://'))
      return 'Must start with http:// or https://.';
    return '';
  },
  OPENAI_COMPAT_API_KEY: function(v) {
    if (!isProviderEnabled('custom')) return '';
    if (!v || !v.trim()) return 'Required when the custom provider is enabled.';
    return '';
  },
  OPENAI_COMPAT_MODEL: function(v) {
    if (!isProviderEnabled('custom')) return '';
    if (!v || !v.trim()) return 'Required when the custom provider is enabled.';
    return '';
  },
  POSTGRES_USER: function(v) {
    if (!v) return 'Required.';
    if (!/^[a-zA-Z0-9_-]{1,63}$/.test(v)) return 'Alphanumeric, _ or - only (1-63 chars).';
    return '';
  },
  POSTGRES_PASSWORD: function(v) {
    if (v.length < 8) return 'Minimum 8 characters.';
    return '';
  },
  POSTGRES_DB: function(v) {
    if (!v) return 'Required.';
    if (!/^[a-zA-Z0-9_-]{1,63}$/.test(v)) return 'Alphanumeric, _ or - only (1-63 chars).';
    return '';
  },
  AI_DB_PASSWORD: function(v) {
    if (v.length < 8) return 'Minimum 8 characters.';
    return '';
  },
  DATABASE_SCHEMA: function(v) {
    if (!v) return 'Required.';
    if (!/^[a-zA-Z0-9_-]{1,63}$/.test(v)) return 'Alphanumeric, _ or - only (1-63 chars).';
    return '';
  },
  SECRET_KEY: function(v) {
    if (!/^[0-9a-fA-F]{64,}$/.test(v)) return 'Must be 64+ hexadecimal characters.';
    return '';
  },
  ALGORITHM: function(v) { return ''; }
};

var pageFields = [
  ['DATA_PATH'],
  [],
  ['POSTGRES_USER','POSTGRES_PASSWORD','POSTGRES_DB','AI_DB_PASSWORD',
   'DATABASE_SCHEMA','SECRET_KEY','ALGORITHM']
];

// Providers eligible as the server-wide boot default (first configured + responding wins)
var bootOrderProviders = ['google','openai','anthropic','mistral','ollama','llamacpp','custom'];

var providerFields = {
  google: ['GOOGLE_API_KEY'],
  openai: ['OPENAI_API_KEY'],
  anthropic: ['ANTHROPIC_API_KEY'],
  mistral: ['MISTRAL_API_KEY'],
  ollama: ['OLLAMA_BASE_URL','OLLAMA_MODEL'],
  llamacpp: ['LLAMACPP_BASE_URL','LLAMACPP_MODEL'],
  custom: ['OPENAI_COMPAT_BASE_URL','OPENAI_COMPAT_API_KEY','OPENAI_COMPAT_MODEL']
};

function validateField(key) {
  var el = document.getElementById(key);
  if (!el) return true;
  var statusEl = document.getElementById('status-' + key);
  var fn = validators[key];
  if (!fn) return true;
  var err = fn(el.value);
  if (err) {
    el.classList.remove('valid'); el.classList.add('invalid');
    if (statusEl) { statusEl.textContent = err; statusEl.className = 'field-status invalid'; }
    return false;
  } else {
    el.classList.remove('invalid'); el.classList.add('valid');
    if (statusEl) { statusEl.textContent = 'Valid'; statusEl.className = 'field-status valid'; }
    return true;
  }
}

function validatePage(idx) {
  var fields = pageFields[idx];
  var ok = true;
  for (var i = 0; i < fields.length; i++) {
    if (!validateField(fields[i])) ok = false;
  }

  if (idx === 1) {
    // Validate enabled providers
    var anyBootProvider = false;
    var providers = ['google','openai','anthropic','mistral','ollama','llamacpp','custom'];
    for (var p = 0; p < providers.length; p++) {
      var pid = providers[p];
      var toggle = document.getElementById('toggle-' + pid);
      if (!toggle || !toggle.checked) continue;
      var flds = providerFields[pid];
      for (var f = 0; f < flds.length; f++) {
        if (!validateField(flds[f])) ok = false;
      }
      if (bootOrderProviders.indexOf(pid) !== -1) anyBootProvider = true;
    }
    if (!anyBootProvider) {
      ok = false;
      var b = document.getElementById('error-banner');
      b.textContent = 'Enable at least one provider (Google, OpenAI, Anthropic, Mistral, Ollama, llama.cpp, or a custom OpenAI-compatible endpoint).';
      b.classList.add('visible');
      return false;
    }
  }

  return ok;
}

function toggleProvider(pid) {
  var toggle = document.getElementById('toggle-' + pid);
  var body = document.getElementById('body-' + pid);
  if (toggle.checked) {
    body.style.display = 'block';
  } else {
    body.style.display = 'none';
    // Clear validation states when disabling
    var flds = providerFields[pid];
    for (var f = 0; f < flds.length; f++) {
      var el = document.getElementById(flds[f]);
      if (el) { el.classList.remove('valid','invalid'); }
      var st = document.getElementById('status-' + flds[f]);
      if (st) { st.textContent = ''; st.className = 'field-status'; }
    }
  }
}

function toggleUnveil() {
  var btn = document.getElementById('unveil-btn');
  var content = document.getElementById('unveil-content');
  btn.classList.toggle('open');
  content.classList.toggle('open');
}

function toggleLangfuse() {
  var toggle = document.getElementById('toggle-langfuse');
  var body = document.getElementById('body-langfuse');
  if (body) body.style.display = toggle && toggle.checked ? 'block' : 'none';
}

function showPage(idx) {
  var pages = document.querySelectorAll('.page');
  for (var i = 0; i < pages.length; i++) pages[i].classList.remove('active');
  document.querySelector('.page[data-page="' + idx + '"]').classList.add('active');

  var steps = document.querySelectorAll('.step-indicator');
  for (var i = 0; i < steps.length; i++) {
    steps[i].classList.remove('active', 'done');
    if (i < idx) steps[i].classList.add('done');
    else if (i === idx) steps[i].classList.add('active');
  }

  document.getElementById('prev-btn').style.visibility = idx === 0 ? 'hidden' : 'visible';
  var nextBtn = document.getElementById('next-btn');
  if (idx === totalPages - 1) {
    nextBtn.textContent = 'Save configuration';
    nextBtn.onclick = saveConfig;
  } else {
    nextBtn.textContent = 'Next';
    nextBtn.onclick = nextPage;
  }

  document.getElementById('error-banner').classList.remove('visible');
  currentPage = idx;
}

function nextPage() {
  if (!validatePage(currentPage)) {
    var b = document.getElementById('error-banner');
    if (!b.classList.contains('visible')) {
      b.textContent = 'Please fix the errors above before continuing.';
      b.classList.add('visible');
    }
    return;
  }
  if (currentPage < totalPages - 1) showPage(currentPage + 1);
}

function prevPage() {
  if (currentPage > 0) showPage(currentPage - 1);
}

function saveConfig() {
  // Validate all pages
  for (var p = 0; p < totalPages; p++) {
    if (!validatePage(p)) {
      showPage(p);
      var b = document.getElementById('error-banner');
      b.textContent = 'Please fix the errors on this page before saving.';
      b.classList.add('visible');
      return;
    }
  }

  var values = {};

  // Page 1 fields
  var p1 = pageFields[0];
  for (var i = 0; i < p1.length; i++) {
    var el = document.getElementById(p1[i]);
    if (el) values[p1[i]] = el.value;
  }

  // Page 2: collect from all providers (empty string for disabled)
  var providers = ['google','openai','anthropic','mistral','ollama','llamacpp','custom'];
  for (var p = 0; p < providers.length; p++) {
    var pid = providers[p];
    var toggle = document.getElementById('toggle-' + pid);
    var enabled = toggle && toggle.checked;
    var flds = providerFields[pid];
    for (var f = 0; f < flds.length; f++) {
      var el = document.getElementById(flds[f]);
      values[flds[f]] = enabled && el ? el.value : '';
    }
  }

  // Page 3 fields
  var p3 = pageFields[2];
  for (var i = 0; i < p3.length; i++) {
    var el = document.getElementById(p3[i]);
    if (el) values[p3[i]] = el.tagName === 'SELECT' ? el.value : el.value;
  }

  // Langfuse tracing: on/off only, no credentials
  var lfToggle = document.getElementById('toggle-langfuse');
  values['LANGFUSE_TRACING'] = (lfToggle && lfToggle.checked) ? '1' : '';

  var btn = document.getElementById('next-btn');
  btn.disabled = true; btn.textContent = 'Saving...';

  fetch('/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(values)
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.ok) {
      document.querySelector('.container').innerHTML = data.html;
    } else {
      btn.disabled = false; btn.textContent = 'Save configuration';
      var b = document.getElementById('error-banner');
      b.textContent = data.error || 'Failed to save.';
      b.classList.add('visible');
    }
  })
  .catch(function(e) {
    btn.disabled = false; btn.textContent = 'Save configuration';
    var b = document.getElementById('error-banner');
    b.textContent = 'Connection error: ' + e.message;
    b.classList.add('visible');
  });
}

function toggleVis(btn) {
  var inp = btn.parentElement.querySelector('input');
  if (inp.type === 'password') { inp.type = 'text'; btn.textContent = 'hide'; }
  else { inp.type = 'password'; btn.textContent = 'show'; }
}

function resetDivePath() {
  document.getElementById('DATA_PATH').value = 'nveil-data';
  validateField('DATA_PATH');
}

function testProvider(pid) {
  var btn = document.getElementById('test-' + pid);
  var result = document.getElementById('test-result-' + pid);
  var flds = providerFields[pid];
  var payload = {provider: pid};
  for (var i = 0; i < flds.length; i++) {
    var el = document.getElementById(flds[i]);
    payload[flds[i]] = el ? el.value : '';
  }
  btn.disabled = true; btn.textContent = 'Testing...';
  result.textContent = ''; result.className = 'test-result';
  fetch('/test-key', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    btn.disabled = false; btn.textContent = 'Test connection';
    if (data.ok) {
      result.textContent = '\\u2713 ' + (data.message || 'Connection successful');
      result.className = 'test-result ok';
    } else {
      result.textContent = '\\u2717 ' + (data.error || 'Connection failed');
      result.className = 'test-result fail';
    }
  })
  .catch(function(e) {
    btn.disabled = false; btn.textContent = 'Test connection';
    result.textContent = '\\u2717 Network error';
    result.className = 'test-result fail';
  });
}
"""

# ── Page rendering ──────────────────────────────────────────────────────────

STEP_LABELS = ["General", "AI Providers", "Advanced"]


def render_wizard(values):
    steps_html = ""
    for i, label in enumerate(STEP_LABELS):
        active = " active" if i == 0 else ""
        steps_html += (
            f'<div class="step-indicator{active}" data-step="{i}">'
            f'<span class="step-num">{i + 1}</span>'
            f'<span class="step-label">{label}</span>'
            f"</div>"
        )
        if i < len(STEP_LABELS) - 1:
            steps_html += '<div class="step-connector"></div>'

    pages_html = ""
    for i, page in enumerate(PAGES):
        active = " active" if i == 0 else ""
        fields = PAGE_RENDERERS[i](values)

        if i == 2:
            pages_html += (
                f'<div class="page{active}" data-page="{i}">'
                f'<div class="ready-msg">'
                f'<h2>You\'re ready!</h2>'
                f'<p>But if you want to configure more, there is this toggle list you can unveil.</p>'
                f'</div>'
                f'<div class="unveil-toggle" id="unveil-btn" onclick="toggleUnveil()">'
                f'<span class="unveil-arrow">&#9656;</span> Unveil advanced settings'
                f'</div>'
                f'<div class="unveil-content" id="unveil-content">'
                f'<div class="page-card">{fields}</div>'
                f'</div>'
                f'</div>'
            )
        else:
            pages_html += (
                f'<div class="page{active}" data-page="{i}">'
                f'<div class="page-card">'
                f'<div class="page-title">{page["title"]}</div>'
                f'<div class="page-desc">{page["desc"]}</div>'
                f"{fields}"
                f"</div></div>"
            )

    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Nveil Setup</title>"
        f"<style>{CSS}</style>"
        "</head><body>"
        '<div class="container">'
        "<h1>Nveil Setup</h1>"
        '<p class="subtitle">Configure your community edition before first start.</p>'
        f'<div class="steps-bar">{steps_html}</div>'
        '<div id="error-banner" class="error-banner"></div>'
        f'<form id="wizard-form" onsubmit="return false;">{pages_html}</form>'
        '<div class="nav-bar">'
        '<button class="btn btn-secondary" id="prev-btn" onclick="prevPage()" style="visibility:hidden">Previous</button>'
        '<button class="btn btn-primary" id="next-btn" onclick="nextPage()">Next</button>'
        "</div></div>"
        f"<script>{JS}</script>"
        "</body></html>"
    )


SUCCESS_HTML = (
    '<div class="success-card">'
    '<div class="success-check">&#10003;</div>'
    "<h2>Configuration saved</h2>"
    "<p>Your <strong>.env</strong> file "
    "has been updated with your new configuration.</p>"
    '<ol class="success-steps">'
    '<li data-n="1.">Start the application: '
    "<code>docker compose up --build -d</code></li>"
    '<li data-n="2.">Open <strong>https://localhost:8000</strong></li>'
    "</ol></div>"
)

# ── Server-side validation ──────────────────────────────────────────────────

_VOLUME_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_ABS_LINUX_RE = re.compile(r"^/[^\0]+")
_ABS_WIN_RE = re.compile(r"^[A-Za-z]:[\\\/]")

_IDENT_RE = re.compile(r"^[a-zA-Z0-9_-]{1,63}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]{64,}$")


def validate_all(values):
    errors = {}

    dive = values.get("DATA_PATH", "").strip()
    if not dive:
        errors["DATA_PATH"] = "Required."
    elif not (_ABS_LINUX_RE.match(dive) or _ABS_WIN_RE.match(dive) or _VOLUME_NAME_RE.match(dive)):
        errors["DATA_PATH"] = "Enter a valid absolute path or Docker volume name."

    for key in ("POSTGRES_USER", "POSTGRES_DB", "DATABASE_SCHEMA"):
        v = values.get(key, "")
        if not v or not _IDENT_RE.match(v):
            errors[key] = "Alphanumeric, _ or - only (1-63 chars)."

    for key in ("POSTGRES_PASSWORD", "AI_DB_PASSWORD"):
        if len(values.get(key, "")) < 8:
            errors[key] = "Minimum 8 characters."

    if not _HEX_RE.match(values.get("SECRET_KEY", "")):
        errors["SECRET_KEY"] = "Must be 64+ hexadecimal characters."

    if values.get("ALGORITHM") not in ("HS256", "HS512"):
        errors["ALGORITHM"] = "Must be HS256 or HS512."

    google = values.get("GOOGLE_API_KEY", "").strip()
    if google:
        if not google.startswith("AIza") or len(google) < 35:
            errors["GOOGLE_API_KEY"] = "Google keys start with 'AIza', ~39 chars."

    openai_key = values.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        if not openai_key.startswith("sk-"):
            errors["OPENAI_API_KEY"] = "OpenAI keys start with 'sk-'."
        elif len(openai_key) < 20:
            errors["OPENAI_API_KEY"] = "Key looks too short."

    anthropic = values.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic:
        if not anthropic.startswith("sk-ant-"):
            errors["ANTHROPIC_API_KEY"] = "Anthropic keys start with 'sk-ant-'."
        elif len(anthropic) < 20:
            errors["ANTHROPIC_API_KEY"] = "Key looks too short."

    mistral = values.get("MISTRAL_API_KEY", "").strip()
    if mistral and len(mistral) < 20:
        errors["MISTRAL_API_KEY"] = "Key looks too short."

    ollama_url = values.get("OLLAMA_BASE_URL", "").strip()
    if ollama_url and not (ollama_url.startswith("http://") or ollama_url.startswith("https://")):
        errors["OLLAMA_BASE_URL"] = "Must start with http:// or https://."

    llamacpp_url = values.get("LLAMACPP_BASE_URL", "").strip()
    if llamacpp_url and not (llamacpp_url.startswith("http://") or llamacpp_url.startswith("https://")):
        errors["LLAMACPP_BASE_URL"] = "Must start with http:// or https://."

    # Generic OpenAI-compatible provider: all three fields go together.
    compat_url = values.get("OPENAI_COMPAT_BASE_URL", "").strip()
    compat_key = values.get("OPENAI_COMPAT_API_KEY", "").strip()
    compat_model = values.get("OPENAI_COMPAT_MODEL", "").strip()
    compat_any = bool(compat_url or compat_key or compat_model)
    has_compat = bool(compat_url and compat_key and compat_model)
    if compat_url and not (compat_url.startswith("http://") or compat_url.startswith("https://")):
        errors["OPENAI_COMPAT_BASE_URL"] = "Must start with http:// or https://."
    if compat_any and not has_compat:
        if not compat_url:
            errors["OPENAI_COMPAT_BASE_URL"] = "Required for the custom provider."
        if not compat_key:
            errors["OPENAI_COMPAT_API_KEY"] = "Required for the custom provider."
        if not compat_model:
            errors["OPENAI_COMPAT_MODEL"] = "Required for the custom provider."

    has_commercial = any(
        values.get(k, "").strip()
        for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "MISTRAL_API_KEY")
    )
    has_ollama = bool(
        values.get("OLLAMA_BASE_URL", "").strip() and values.get("OLLAMA_MODEL", "").strip()
    )
    has_llamacpp = bool(
        values.get("LLAMACPP_BASE_URL", "").strip() and values.get("LLAMACPP_MODEL", "").strip()
    )
    if not (has_commercial or has_ollama or has_llamacpp or has_compat):
        errors["_provider"] = (
            "At least one boot-order provider required "
            "(Google, OpenAI, Anthropic, Mistral, Ollama, llama.cpp, "
            "or a custom OpenAI-compatible endpoint)."
        )

    return errors


# ── API key testing ────────────────────────────────────────────────────────

_TEST_TIMEOUT = 15.0

# Wizard provider id → provider config filename under llm_processing/configs/.
_PROVIDER_CONFIG_FILE = {
    "google": "google_genai",
    "openai": "openai",
    "anthropic": "anthropic",
    "mistral": "mistralai",
}

# Fallback cheap models used only if the config yaml can't be read.
# KEEP IN SYNC with the `minimal:` blocks in
# nveil/backend/ai_service/llm_processing/configs/*.yaml.
_FALLBACK_MINIMAL_MODEL = {
    "google": "gemini-3-flash-preview",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
    "mistral": "mistral-small-latest",
}

_CONFIGS_DIR = (
    WORKSPACE / "nveil" / "backend" / "ai_service" / "llm_processing" / "configs"
)


def _minimal_model(provider: str) -> str:
    """Resolve the cheap model the AI service will use for *provider*.

    Reads the `minimal:` block from the provider's config yaml — the single
    source of truth shared with choregraph and the csv_characterization node.
    Falls back to a hard-coded map if the yaml is missing.
    """
    fname = _PROVIDER_CONFIG_FILE.get(provider)
    if fname:
        try:
            from ruamel.yaml import YAML

            with open(_CONFIGS_DIR / f"{fname}.yaml") as f:
                cfg = YAML(typ="safe").load(f) or {}
            model = (cfg.get("minimal") or {}).get("model")
            if model:
                return str(model)
        except Exception:
            pass
    return _FALLBACK_MINIMAL_MODEL.get(provider, "")


def _ping_error(r: "httpx.Response") -> str:
    """Extract a compact error message from a failed ping response."""
    try:
        err = r.json().get("error", r.json())
        msg = err.get("message") if isinstance(err, dict) else str(err)
    except Exception:
        msg = r.text[:160]
    return f"HTTP {r.status_code}: {msg or r.text[:160]}"


def _ping_openai_chat(base_url: str, key: str | None, model: str) -> tuple[bool, str]:
    """OpenAI-style chat-completion ping (OpenAI, Mistral, llama.cpp, custom).

    A real 1-shot completion (not a /models listing) so it exercises auth,
    quota, and access to the exact model. Any 2xx is success regardless of
    output content. Reasoning/thinking is never enabled.
    """
    r = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {key}"} if key else {},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 16,
        },
        timeout=_TEST_TIMEOUT,
    )
    if r.is_success:
        return True, f"OK — '{model}' responded"
    return False, _ping_error(r)


def test_provider_key(provider: str, values: dict) -> tuple[bool, str]:
    """Test a provider by pinging its configured model with a tiny completion.

    Unlike a `/models` listing (which only checks the key authenticates),
    this performs a real inference call so it also covers quota and access to
    the exact model the AI service will use. Thinking/reasoning is never
    enabled — a low token budget would otherwise collide with the thinking
    budget (e.g. Anthropic returns 400 when max_tokens <= budget_tokens).
    Returns (ok, message).
    """
    try:
        if provider == "google":
            key = values.get("GOOGLE_API_KEY", "").strip()
            if not key:
                return False, "API key is empty."
            model = _minimal_model("google")
            r = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                json={
                    "contents": [{"parts": [{"text": "ping"}]}],
                    "generationConfig": {"maxOutputTokens": 8},
                },
                timeout=_TEST_TIMEOUT,
            )
            if r.is_success:
                return True, f"OK — '{model}' responded"
            return False, _ping_error(r)

        elif provider == "openai":
            key = values.get("OPENAI_API_KEY", "").strip()
            if not key:
                return False, "API key is empty."
            return _ping_openai_chat("https://api.openai.com/v1", key, _minimal_model("openai"))

        elif provider == "anthropic":
            key = values.get("ANTHROPIC_API_KEY", "").strip()
            if not key:
                return False, "API key is empty."
            model = _minimal_model("anthropic")
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                json={
                    "model": model,
                    "max_tokens": 16,
                    "messages": [{"role": "user", "content": "ping"}],
                },
                timeout=_TEST_TIMEOUT,
            )
            if r.is_success:
                return True, f"OK — '{model}' responded"
            return False, _ping_error(r)

        elif provider == "mistral":
            key = values.get("MISTRAL_API_KEY", "").strip()
            if not key:
                return False, "API key is empty."
            return _ping_openai_chat("https://api.mistral.ai/v1", key, _minimal_model("mistral"))

        elif provider == "ollama":
            url = values.get("OLLAMA_BASE_URL", "").strip().rstrip("/")
            model = values.get("OLLAMA_MODEL", "").strip()
            if not url:
                return False, "Base URL is empty."
            if not model:
                return False, "Model tag is empty."
            r = httpx.post(
                f"{url}/api/generate",
                json={
                    "model": model,
                    "prompt": "ping",
                    "stream": False,
                    "options": {"num_predict": 8},
                },
                timeout=_TEST_TIMEOUT,
            )
            if r.is_success:
                return True, f"OK — model '{model}' responded"
            # Ollama returns 404 with a helpful message when the tag isn't pulled.
            return False, _ping_error(r)

        elif provider == "llamacpp":
            url = values.get("LLAMACPP_BASE_URL", "").strip().rstrip("/")
            model = values.get("LLAMACPP_MODEL", "").strip()
            if not url:
                return False, "Base URL is empty."
            if not model:
                return False, "Model alias is empty."
            return _ping_openai_chat(f"{url}/v1", None, model)

        elif provider == "custom":
            url = values.get("OPENAI_COMPAT_BASE_URL", "").strip().rstrip("/")
            key = values.get("OPENAI_COMPAT_API_KEY", "").strip()
            model = values.get("OPENAI_COMPAT_MODEL", "").strip()
            if not url:
                return False, "Base URL is empty."
            if not key:
                return False, "API key is empty."
            if not model:
                return False, "Model name is empty."
            return _ping_openai_chat(url, key, model)

        else:
            return False, f"Unknown provider: {provider}"

    except httpx.ConnectError:
        return False, "Connection refused — is the service running?"
    except httpx.TimeoutException:
        return False, f"Timeout after {_TEST_TIMEOUT}s — is the URL correct?"
    except Exception as e:
        return False, str(e)[:120]


# ── HTTP handler ────────────────────────────────────────────────────────────


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            values = auto_generate(get_current_values())
            body = render_wizard(values).encode()
            self._respond(200, "text/html", body)

        else:
            self.send_error(404)

    def do_POST(self):
        if self.path not in ("/save", "/test-key"):
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode()

        if self.path == "/test-key":
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                body = json.dumps({"ok": False, "error": "Invalid request."}).encode()
                self._respond(400, "application/json", body)
                return
            provider = payload.get("provider", "")
            ok, msg = test_provider_key(provider, payload)
            body = json.dumps({"ok": ok, **({"message": msg} if ok else {"error": msg})}).encode()
            self._respond(200, "application/json", body)
            return

        try:
            values = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            body = json.dumps({"ok": False, "error": "Invalid request body."}).encode()
            self._respond(400, "application/json", body)
            return

        errors = validate_all(values)
        if errors:
            msg = "Validation errors: " + "; ".join(f"{k}: {v}" for k, v in errors.items())
            body = json.dumps({"ok": False, "error": msg}).encode()
            self._respond(422, "application/json", body)
            return

        try:
            write_dot_env(values)
            write_langfuse_env(values)
        except Exception as e:
            body = json.dumps({"ok": False, "error": f"Failed to write .env: {e}"}).encode()
            self._respond(500, "application/json", body)
            return

        body = json.dumps({"ok": True, "html": SUCCESS_HTML}).encode()
        self._respond(200, "application/json", body)

        threading.Timer(1.0, self.server.shutdown).start()

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[setup] {fmt % args}")


if __name__ == "__main__":
    if not WORKSPACE.exists():
        print(f"[error] {WORKSPACE} not found. Run this from the setup container.")
        raise SystemExit(1)
    server = HTTPServer(("0.0.0.0", 3000), Handler)
    print()
    print("[setup] ════════════════════════════════════════════════")
    print("[setup]  Nveil Setup Wizard")
    print("[setup]  Open http://localhost:3000 in your browser")
    print("[setup] ════════════════════════════════════════════════")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[setup] Shutting down.")
