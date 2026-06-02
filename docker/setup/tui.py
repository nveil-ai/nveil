# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Nveil Setup Wizard — Textual TUI for configuring .env."""

import re
import sys
from dataclasses import dataclass
from typing import Callable, Tuple

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Collapsible, Footer, Header, Input, Label, Select, Static

from compose_utils import (
    WORKSPACE,
    auto_generate,
    get_current_values,
    write_dot_env,
)

# ── Validators ───────────────────────────────────────────────────────────────

Validation = Tuple[bool, str]

_IDENT_RE = re.compile(r"^[a-zA-Z0-9_-]{1,63}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]{64,}$")
def validate_identifier(value: str) -> Validation:
    if not value:
        return False, "Required."
    if not _IDENT_RE.match(value):
        return False, "Alphanumeric, _ or - only (1-63 chars)."
    return True, ""


def validate_password(value: str) -> Validation:
    if len(value) < 8:
        return False, "Minimum 8 characters."
    return True, ""


def validate_hex_key(value: str) -> Validation:
    if not _HEX_RE.match(value):
        return False, "Must be 64+ hexadecimal characters."
    return True, ""


def validate_algorithm(value: str) -> Validation:
    if value not in ("HS256", "HS512"):
        return False, "Must be HS256 or HS512."
    return True, ""


def validate_path(value: str) -> Validation:
    if not value or not value.strip():
        return False, "Required."
    return True, ""


def validate_api_key(value: str) -> Validation:
    if not value:
        return True, ""
    if len(value) < 10:
        return False, "Key looks too short."
    return True, ""


_TRACING_ON = {"1", "true", "yes", "on"}
_TRACING_OFF = {"", "0", "false", "no", "off"}


def validate_tracing_toggle(value: str) -> Validation:
    if value.strip().lower() in _TRACING_ON | _TRACING_OFF:
        return True, ""
    return False, "Use 1/0 (or yes/no, on/off, empty)."


def validate_langfuse_key(value: str) -> Validation:
    if not value:
        return True, ""
    if len(value) < 8:
        return False, "Key looks too short."
    return True, ""


# ── Field definitions ────────────────────────────────────────────────────────


@dataclass
class FieldDef:
    key: str
    label: str
    default: str
    validator: Callable[[str], Validation]
    group: str = "main"
    secret: bool = False
    optional: bool = False
    auto: bool = False


FIELD_DEFS = [
    FieldDef("POSTGRES_USER", "Database user", "nveil", validate_identifier),
    FieldDef("POSTGRES_PASSWORD", "Database password", "", validate_password, secret=True, auto=True),
    FieldDef("POSTGRES_DB", "Database name", "nveil", validate_identifier),
    FieldDef("AI_DB_PASSWORD", "AI service DB password", "", validate_password, secret=True, auto=True),
    FieldDef("GOOGLE_API_KEY", "Gemini API key (optional)", "", validate_api_key, secret=True, optional=True),
    FieldDef("DATABASE_SCHEMA", "Database schema", "nveilseption", validate_identifier, group="advanced"),
    FieldDef("SECRET_KEY", "JWT secret key (64+ hex)", "", validate_hex_key, group="advanced", secret=True, auto=True),
    FieldDef("ALGORITHM", "JWT algorithm", "HS512", validate_algorithm, group="advanced"),
    FieldDef("DIVE_DATA_PATH", "Data storage path", "nveil-dive-data", validate_path, group="advanced"),
    # ── Langfuse (LLM tracing + prompt management) ─ optional, off by default
    FieldDef(
        "LANGFUSE_TRACING",
        "Enable LLM tracing (1=on, empty=off)",
        "",
        validate_tracing_toggle,
        group="langfuse",
        optional=True,
    ),
    FieldDef(
        "LANGFUSE_PUBLIC_KEY",
        "Langfuse public key",
        "",
        validate_langfuse_key,
        group="langfuse",
        optional=True,
        auto=True,
    ),
    FieldDef(
        "LANGFUSE_SECRET_KEY",
        "Langfuse secret key",
        "",
        validate_langfuse_key,
        group="langfuse",
        secret=True,
        optional=True,
        auto=True,
    ),
]


# ── Custom widgets ───────────────────────────────────────────────────────────


class EnvInputField(Vertical):
    """Input field with label and validation status."""

    def __init__(self, field_def: FieldDef, initial_value: str = ""):
        super().__init__()
        self.field_def = field_def
        self.initial_value = initial_value or field_def.default

    def compose(self) -> ComposeResult:
        optional = " (optional)" if self.field_def.optional else ""
        yield Label(
            f"[bold]{self.field_def.label}[/bold]  [dim]{self.field_def.key}{optional}[/dim]",
            classes="field-label",
        )
        if self.field_def.key == "ALGORITHM":
            yield Select(
                [("HS256", "HS256"), ("HS512", "HS512")],
                value=self.initial_value,
                id=f"select-{self.field_def.key}",
            )
        else:
            yield Input(
                value=self.initial_value,
                password=self.field_def.secret,
                placeholder=f"Enter {self.field_def.key}...",
                id=f"input-{self.field_def.key}",
            )
        yield Label("", classes="status-label", id=f"status-{self.field_def.key}")

    def on_mount(self) -> None:
        if self.initial_value:
            self._run_validation(self.initial_value)

    def _run_validation(self, value: str) -> bool:
        status = self.query_one(f"#status-{self.field_def.key}", Label)
        ok, msg = self.field_def.validator(value)

        inp = None
        try:
            inp = self.query_one(f"#input-{self.field_def.key}", Input)
        except Exception:
            pass

        if ok:
            status.update("[#a6e3a1]Valid[/#a6e3a1]")
            if inp:
                inp.remove_class("state-invalid", "state-prefilled")
                inp.add_class("state-valid")
        else:
            status.update(f"[#f38ba8]{msg}[/#f38ba8]")
            if inp:
                inp.remove_class("state-valid", "state-prefilled")
                inp.add_class("state-invalid")
        return ok

    def get_value(self) -> str:
        if self.field_def.key == "ALGORITHM":
            sel = self.query_one(f"#select-{self.field_def.key}", Select)
            return str(sel.value) if sel.value != Select.BLANK else "HS512"
        return self.query_one(f"#input-{self.field_def.key}", Input).value

    def validate_field(self) -> bool:
        return self._run_validation(self.get_value())


# ── Success screen ───────────────────────────────────────────────────────────


class SuccessScreen(Screen):
    BINDINGS = [Binding("escape", "dismiss", "Close")]

    CSS = """
    SuccessScreen {
        align: center middle;
    }
    #success-card {
        width: 70;
        height: auto;
        background: #1e1e2e;
        border: tall #a6e3a1;
        padding: 2 4;
    }
    #success-card Static {
        text-align: center;
        margin-bottom: 1;
    }
    #success-card Button {
        width: 100%;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="success-card"):
            yield Static("[bold #a6e3a1]Configuration saved[/bold #a6e3a1]")
            yield Static("")
            yield Static("[bold]Next steps:[/bold]")
            yield Static("1. Stop this container (or it exits automatically)")
            yield Static("2. Build the base image (first time only):")
            yield Static("[dim]docker build -f deploy/docker/base/dockerfile -t nveil-base:latest .[/dim]")
            yield Static("3. Start Nveil:")
            yield Static("[dim]docker compose up --build -d[/dim]")
            yield Static("4. Open [bold]https://localhost:8000[/bold]")
            yield Static("")
            yield Button("Exit", variant="success", id="exit-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "exit-btn":
            self.app.exit()


# ── Main app ─────────────────────────────────────────────────────────────────


class NveilSetup(App):
    TITLE = "Nveil Setup"
    BINDINGS = [
        Binding("ctrl+s", "save_config", "Save"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        background: #1e1e2e;
        color: #cdd6f4;
    }
    #banner {
        text-align: center;
        color: #cba6f7;
        background: #11111b;
        padding: 1;
        margin-bottom: 1;
        border-bottom: solid #cba6f7;
    }
    #subtitle {
        text-align: center;
        color: #a6adc8;
        margin-bottom: 1;
    }
    .section-title {
        margin: 1 2;
        color: #89b4fa;
    }
    EnvInputField {
        margin: 0 2 1 2;
        height: auto;
    }
    .field-label {
        margin-left: 1;
        margin-bottom: 0;
    }
    Input {
        background: #313244;
        color: #cdd6f4;
        border: tall #45475a;
        margin: 0;
    }
    Input.state-valid {
        border: tall #a6e3a1;
    }
    Input.state-invalid {
        border: tall #f38ba8;
    }
    Input.state-prefilled {
        border: tall #f9e2af;
    }
    Select {
        background: #313244;
        margin: 0;
    }
    .status-label {
        margin-left: 1;
        color: #a6adc8;
    }
    Collapsible {
        margin: 1 2;
        background: #181825;
        border: none;
    }
    CollapsibleTitle {
        color: #fab387;
        background: #313244;
    }
    #action-bar {
        margin: 1 2;
        height: 3;
    }
    #action-bar Button {
        margin-right: 1;
    }
    """

    def __init__(self):
        super().__init__()
        self._values: dict = {}

    def compose(self) -> ComposeResult:
        yield Header()
        banner = r"""
 _   _          _ _   ____       _
| \ | |_   _____(_) | / ___|  ___| |_ _   _ _ __
|  \| \ \ / / _ \ | | \___ \ / _ \ __| | | | '_ \
| |\  |\ V /  __/ | |  ___) |  __/ |_| |_| | |_) |
|_| \_| \_/ \___|_|_| |____/ \___|\__|\__,_| .__/
                                            |_|
"""
        yield Static(banner, id="banner")
        yield Static("Configure your community edition before first start.", id="subtitle")

        with ScrollableContainer():
            yield Label("DATABASE", classes="section-title")
            for fd in FIELD_DEFS:
                if fd.group == "main":
                    yield EnvInputField(fd, self._values.get(fd.key, ""))

            with Collapsible(title="ADVANCED SETTINGS", collapsed=True):
                for fd in FIELD_DEFS:
                    if fd.group == "advanced":
                        yield EnvInputField(fd, self._values.get(fd.key, ""))

            with Collapsible(title="LLM TRACING (LANGFUSE — OPTIONAL)", collapsed=True):
                yield Static(
                    "Off by default. When enabled, start the tracing stack as\n"
                    "its own project from the same file:\n"
                    "  docker compose -p langfuse --profile tracing up -d\n"
                    "UI at http://localhost:3030 (login dev@nveil.com / dev-password).",
                    classes="section-help",
                )
                for fd in FIELD_DEFS:
                    if fd.group == "langfuse":
                        yield EnvInputField(fd, self._values.get(fd.key, ""))

            with Horizontal(id="action-bar"):
                yield Button("Save configuration", variant="primary", id="save-btn")
                yield Button("Quit", variant="error", id="quit-btn")

        yield Footer()

    def on_mount(self) -> None:
        try:
            self._values = auto_generate(get_current_values())
        except Exception as e:
            self.notify(f"Could not load .env: {e}", severity="error")
            self._values = {}
            return

        for field_widget in self.query(EnvInputField):
            key = field_widget.field_def.key
            val = self._values.get(key, field_widget.field_def.default)
            if not val:
                continue
            try:
                if key == "ALGORITHM":
                    field_widget.query_one(f"#select-{key}", Select).value = val
                else:
                    field_widget.query_one(f"#input-{key}", Input).value = val
            except Exception:
                pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        for field_widget in self.query(EnvInputField):
            try:
                inp = field_widget.query_one(Input)
                if inp is event.input:
                    field_widget.validate_field()
                    return
            except Exception:
                continue

    def on_select_changed(self, event: Select.Changed) -> None:
        for field_widget in self.query(EnvInputField):
            if field_widget.field_def.key == "ALGORITHM":
                field_widget.validate_field()
                return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save_config()
        elif event.button.id == "quit-btn":
            self.action_quit()

    def action_save_config(self) -> None:
        all_valid = True
        collected = {}

        for fd in FIELD_DEFS:
            for field_widget in self.query(EnvInputField):
                if field_widget.field_def.key == fd.key:
                    if not field_widget.validate_field():
                        all_valid = False
                    collected[fd.key] = field_widget.get_value()
                    break

        if not all_valid:
            self.notify("Some fields have errors. Fix them before saving.", severity="error")
            return

        try:
            write_dot_env(collected)
        except Exception as e:
            self.notify(f"Failed to write .env: {e}", severity="error")
            return

        self.push_screen(SuccessScreen())

    def action_quit(self) -> None:
        self.exit()


if __name__ == "__main__":
    if not WORKSPACE.exists():
        print(f"[error] {WORKSPACE} not found. Run this from the setup container.")
        sys.exit(1)
    app = NveilSetup()
    app.run()
