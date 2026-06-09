# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import logging
import os
import shutil
import sys
import pathlib
from contextlib import asynccontextmanager

# Ensure ai_service dir is on sys.path for local subpackage imports.
ai_service_path = os.path.abspath(os.path.dirname(__file__))
if ai_service_path not in sys.path:
    sys.path.insert(0, ai_service_path)

backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.append(backend_path)
from typing import List

import httpx
from database.database import db
from database.model import Base
from database.repository import StateRepository
from shared.secrets import get_secret
from shared.workspace import user_file_path, write_metadata
from fastapi import (FastAPI, HTTPException, Request)
from llm_processing.graphs.workflow_postprocess_nodes import (
    convert_feedback_to_html,
)
from llm_processing.graphs.workflow_request import UserRequest
from llm_processing.graphs.workflow_state import WorkflowState
from llm_processing.graphs.workflow_utils import (get_additional_info,
                                                  set_additional_info)
from llm_processing.checkpointer import get_checkpointer, close_checkpointer, clear_thread
from llm_processing.managers import RouterLLMManager
from llm_processing.prompt import Prompt, seed_langfuse_prompts_if_missing
from shared.llm_config import (
    LLMConfig,
    LLMProvider,
)
from llm_processing.turn_metrics import TurnMetrics, set_turn_metrics
from logger import DEBUG, ERROR, INFO, SUCCESS, WARNING, logger
from pydantic import BaseModel
from sqlalchemy.schema import CreateSchema

from dive import Project
from shared.security import safe_path, sanitize_filename

logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# When the Langfuse backend is unreachable, the langfuse SDK and its underlying
# OpenTelemetry exporter emit a flood of ERROR/WARNING lines per request
# (prompt-fetch fallbacks, OTLP "Failed to export span batch" timeouts). The
# circuit breaker in prompt.py already surfaces a single concise warning when
# Langfuse goes down, so silence the noisy library loggers. Tune for debugging
# via LANGFUSE_LOG_LEVEL / OTEL_LOG_LEVEL (e.g. "DEBUG").
def _log_level(env_name: str, default: str = "CRITICAL") -> int:
    return getattr(logging, os.getenv(env_name, default).upper(), logging.CRITICAL)

logging.getLogger("langfuse").setLevel(_log_level("LANGFUSE_LOG_LEVEL"))
logging.getLogger("opentelemetry").setLevel(_log_level("OTEL_LOG_LEVEL"))

logger(service="AI", service_id="MAIN")  # logger is the nveil logging system


LOCAL = get_secret("LOCAL")
DIVE_PATH = get_secret("DIVE_PATH", "/root/DIVE") 

SERVER_HOST = get_secret("SERVER_HOST")
SERVER_PORT = int(8000)

# Global HTTP client — initialized in lifespan, reused for all outbound requests
httpx_client: httpx.AsyncClient = None

# Holds references to fire-and-forget startup tasks so they aren't GC'd mid-run.
_background_tasks: set = set()


async def init_db():
    db.initialize(
        url=get_secret("STATE_DATABASE_URL"),
        echo=False,
    )
    schema = get_secret("STATE_DATABASE_SCHEMA")
    async with db.engine.begin() as conn:
        await conn.execute(CreateSchema(schema, if_not_exists=True))
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the startup and shutdown lifecycle of the AI service.
    """
    logger().logp(INFO, "AI Service is starting...")
    Prompt.load_templates()

    # Seed Langfuse with any missing yaml prompts (best-effort, non-blocking).
    # Runs in a worker thread so the blocking SDK/HTTP calls never stall the
    # event loop, and fails fast when Langfuse is unreachable so a down host
    # can't delay startup. No-op when LANGFUSE_TRACING is off.
    _seed_task = asyncio.create_task(asyncio.to_thread(seed_langfuse_prompts_if_missing))
    _background_tasks.add(_seed_task)
    _seed_task.add_done_callback(_background_tasks.discard)

    # Create shared HTTP client before graphs so nodes can use it for async calls
    global httpx_client
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    httpx_client = httpx.AsyncClient(limits=limits, verify=True)

    global llm_manager, default_llm_config, main_graph, state_repo, checkpointer
    # Server-wide default — used when an SDK request doesn't carry user
    # credentials in headers (the SaaS frontend path). We walk
    # `PROVIDER_BOOT_ORDER` and pick the first provider whose env-level
    # config (api_key for commercial, base_url+model for local) passes a
    # one-token smoke-test. No NVEIL fallback — if nothing works, we
    # refuse to start so the operator sees the failure immediately.
    candidates = LLMConfig.from_env_ordered()
    if not candidates:
        raise RuntimeError(
            "No LLM provider configured. Run the setup TUI and provide at least one "
            "of: GOOGLE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, MISTRAL_API_KEY, "
            "OLLAMA_BASE_URL+OLLAMA_MODEL, LLAMACPP_BASE_URL+LLAMACPP_MODEL, "
            "or OPENAI_COMPAT_BASE_URL+OPENAI_COMPAT_API_KEY+OPENAI_COMPAT_MODEL."
        )
    default_llm_config = await _select_first_responding_provider(candidates)
    if default_llm_config is None:
        raise RuntimeError(
            "All configured LLM providers failed the boot smoke-test. "
            "Check the keys/endpoints in your .env / docker-compose.yaml."
        )
    logger().logp(
        SUCCESS,
        f"✅ LLM provider selected: {default_llm_config.provider}",
    )
    llm_manager = RouterLLMManager()

    checkpointer = await get_checkpointer()
    logger().logp(SUCCESS, "✅ LangGraph checkpointer initialized.")

    state_repo = StateRepository()
    main_graph = UserRequest(db=state_repo, llm_manager=llm_manager, http_client=httpx_client, checkpointer=checkpointer)

    try:
        await init_db()
        logger().logp(SUCCESS, "✅ Database initialized.")
    except Exception as e:
        logger().logp(ERROR, f"❌ Database initialization failed: {e}")

    # Clean up stale API sessions from previous runs
    try:
        await _cleanup_stale_api_sessions()
    except Exception as e:
        logger().logp(WARNING, f"Stale API session cleanup failed: {e}")

    yield
    # SHUTDOWN
    logger().logp(INFO, "AI Service is shutting down...")
    if httpx_client:
        await httpx_client.aclose()
    await close_checkpointer()


# Create FastAPI app with lifespan manager
ai_app = FastAPI(lifespan=lifespan)


def get_llm_config() -> LLMConfig:
    """Return the server's configured LLM provider.

    The provider, credentials and endpoint are fixed at setup time (the
    operator's ``.env``) and selected once at boot — ``default_llm_config``
    is the first provider in ``PROVIDER_BOOT_ORDER`` that passes the
    startup smoke-test. There is no per-request override: the SDK and web
    paths both run on this single server-side config.
    """
    if default_llm_config is None:
        raise HTTPException(
            status_code=503,
            detail="No LLM provider configured. Run the setup and set a provider key.",
        )
    return default_llm_config


# Cheap, widely-available validation models per provider. Used by the
# boot-time smoke-test (`_smoke_test_llm`) when a provider's config has no
# explicit model_override. Picked for low cost and high availability — the
# goal is just to confirm auth + endpoint work.
_VALIDATION_MODELS: dict[str, str] = {
    "google_genai": "gemini-2.5-flash",
    "openai":      "gpt-4o-mini",
    # Anthropic SDK rejects undated aliases; use the dated id matching
    # llm_processing/configs/anthropic.yaml.
    "anthropic":   "claude-haiku-4-5-20251001",
    "mistralai":   "mistral-small-latest",
    # ollama / llamacpp: no sensible default — the operator must set
    # <PROVIDER>_MODEL in .env (Ollama tag, or llama-server --alias).
}

# Per-provider timeout for the validation ping. Local models need a
# larger budget — Ollama cold-loads a multi-GB model from disk to VRAM on
# the first request (30-60s before any token). llama.cpp pre-loads at
# `llama-server` startup, so the first ping is fast.
_VALIDATION_TIMEOUTS: dict[str, float] = {
    "google_genai": 10.0,
    "openai":       30.0,
    "anthropic":    10.0,
    "mistralai":    10.0,
    "ollama":       120.0,
    "llamacpp":     30.0,
}
_DEFAULT_VALIDATION_TIMEOUT_S = 10.0


def _categorize_validation_error(exc: Exception) -> tuple[str, str]:
    """Map an arbitrary provider exception to (error_code, user_message).

    Never include the raw provider message in the returned `user_message`
    — some providers echo the API key prefix or the base_url in their
    error strings, which we don't want to leak through to the frontend.
    """
    msg = str(exc).lower()
    if any(k in msg for k in ("invalid api key", "incorrect api key", "unauthorized", "401", "403", "permission_denied", "authentication")):
        return "invalid_api_key", "Invalid API key for this provider."
    if any(k in msg for k in ("not found", "404", "model_not_found", "does not exist")):
        return "model_not_available", "The specified model is not available for this provider."
    if any(k in msg for k in ("connect", "dns", "name resolution", "unreachable", "network")):
        return "connection_failed", "Cannot reach the provider endpoint. Check the base URL."
    if "timeout" in msg or isinstance(exc, asyncio.TimeoutError):
        return "timeout", "Provider didn't respond in time."
    if any(k in msg for k in ("rate limit", "429", "quota")):
        return "rate_limited", "Provider is rate-limiting; please try again in a moment."
    return "validation_failed", "Provider rejected the configuration."


async def _smoke_test_llm(cfg: LLMConfig) -> tuple[bool, str, str]:
    """Run a one-token completion against ``cfg`` to verify it works.

    Returns ``(ok, error_code, message)``. On success, error_code and
    message are empty strings. On failure, message is sanitized — never
    contains the raw provider exception (some SDKs echo the API key or
    base_url back in errors).

    Used by the boot-time provider selection in `lifespan()`.
    """
    test_model = cfg.model_override or _VALIDATION_MODELS.get(cfg.provider)
    if not test_model:
        return False, "model_required", (
            f"Provider {cfg.provider!r} requires an explicit model "
            f"name; please specify one."
        )

    # Provider-specific build kwargs. For Ollama we force `think: false` and a
    # tiny num_ctx so the validation ping doesn't burn its budget on a Qwen3
    # thinking loop or on KV-cache allocation for a huge context window.
    build_kwargs: dict = {}
    if cfg.provider == "ollama":
        build_kwargs["extra_body"] = {
            "think": False,
            "options": {"num_ctx": 2048},
        }
    timeout_s = _VALIDATION_TIMEOUTS.get(cfg.provider, _DEFAULT_VALIDATION_TIMEOUT_S)

    try:
        from shared.llm_config import build_chat_model
        llm = build_chat_model(cfg, model=test_model, max_retries=0, **build_kwargs)
        await asyncio.wait_for(llm.ainvoke("ping"), timeout=timeout_s)
    except Exception as exc:
        error_code, message = _categorize_validation_error(exc)
        logger().logp(
            INFO,
            f"LLM config validation failed (provider={cfg.provider} "
            f"model={test_model}): code={error_code} type={type(exc).__name__}",
        )
        return False, error_code, message

    return True, "", ""


async def _select_first_responding_provider(
    candidates: list[LLMConfig],
) -> LLMConfig | None:
    """Iterate candidates in order, return the first one that passes the
    smoke-test. Returns None if all fail."""
    for cfg in candidates:
        ok, error_code, _ = await _smoke_test_llm(cfg)
        if ok:
            return cfg
        logger().logp(
            WARNING,
            f"Provider {cfg.provider} failed boot smoke-test "
            f"(code={error_code}); trying next.",
        )
    return None


@ai_app.post("/ai/process_user_message")
async def chat_endpoint(input_data: Request):
    """
    Handles chat requests by parsing incoming JSON data and processing through AI service
    """
    data = await input_data.json()
    user_id = data.get("user_id")
    message = data.get("message")

    if not message:
        raise HTTPException(status_code=400, detail="No message provided in request")
    logger().logp(DEBUG, f"====== IS_UPLOAD: {data.get('is_upload', False)} ======")
    tm = TurnMetrics()
    set_turn_metrics(tm)
    tm.set_context(
        room_id=data.get("room_id", ""),
        owner_id=data.get("owner_id", ""),
        user_id=data.get("user_id", ""),
    )

    # TODO: get additional info in graph (requires to modify workflow to run async get_additional_info)
    try:
        additional_info = await get_additional_info(
            data.get("user_id"), data.get("room_id"), state_repo
        )
    except Exception as e:
        additional_info = {}
        logger().logp(WARNING, f"⚠️ Could not retrieve additional info: {e}")
    # --- Invokation of the unified graph (classification → ASP → viz → feedback) ---
    await post_stage(
        data.get("room_token"), "ai_processing", "Processing AI request"
    )

    room_id = data.get("room_id")
    llm_cfg = get_llm_config()
    graph_config = {
        "configurable": {
            "thread_id": str(room_id),
            "llm_config": llm_cfg,
        }
    }

    # --- Check for pending interrupt (clarification in progress) ---
    is_selection = data.get("is_selection", False)
    has_pending_interrupt = False
    try:
        prior_state = await main_graph.aget_state(graph_config)
        has_pending_interrupt = bool(prior_state and prior_state.next)
    except Exception as e:
        logger().logp(DEBUG, f"Could not check graph state: {e}")

    if has_pending_interrupt and is_selection:
        # --- CASE A: Resume — user responded to clarification ---
        logger().logp(INFO, f"Resuming interrupted graph for room {room_id} with selection: {message[:80]}")
        graph_result = await main_graph.aresume(message, config=graph_config)
    else:
        if has_pending_interrupt:
            # --- CASE B: Abandon — user sent a different message, discard pending interrupt ---
            logger().logp(INFO, f"Abandoning pending interrupt for room {room_id}, starting fresh.")
        # --- CASE B or C: Fresh invocation (after optional abandon) ---
        await clear_thread(str(room_id))  # Safety: ensure no stale checkpoint leaks state
        state_forward = WorkflowState()
        state_forward.input = {
            "raw_user_input": message,
            "room_id": room_id,
            "owner_id": data.get("owner_id"),
            "user_id": data.get("user_id"),
            "is_an_upload_message": data.get("is_upload", False),
            "is_selection": is_selection and not has_pending_interrupt,
            "cookies": dict(input_data.cookies),
            "additional_info": additional_info,
            "room_token": data.get("room_token"),
            "message_history": data.get("message_history", []),
            "user_language": data.get("user_language", "en"),
        }
        graph_result = await main_graph.arun(state_forward, config=graph_config)

    # --- Check if graph was interrupted (clarification needed) ---
    try:
        post_state = await main_graph.aget_state(graph_config)
        if post_state and post_state.next:
            # Graph paused at an interrupt — extract clarification data
            interrupt_data = _extract_interrupt_data(post_state)
            logger().logp(INFO, f"Graph interrupted — returning clarification prompt to frontend.")
            logger().logp(INFO, tm.format_table())
            await tm.persist_to_db()
            return interrupt_data
    except Exception as e:
        logger().logp(WARNING, f"Could not inspect post-invoke graph state: {e}")

    # --- Graph completed normally — clean up checkpoint ---
    try:
        await clear_thread(str(room_id))
    except Exception:
        pass

    graph_processing = graph_result.get("processing", {}) or {}
    feedback_material = dict(graph_processing.get("feedback_material", {}) or {})
    # TODO: set_additional_info in graph (requires to modify workflow to run async set_additional_info)
    try:
        if feedback_material.get("additional_information"):
            logger().logp(
                DEBUG,
                f"INFO TO STORE IN METADATA: {feedback_material['additional_information']}",
            )
            await set_additional_info(
                data.get("user_id"),
                data.get("room_id"),
                graph_processing.get("persistent_additional_information"),
                state_repo,
            )
    except Exception as e:
        logger().logp(WARNING, f"⚠️ Could not set additional info: {e}")

    # The unified graph's terminal node (format_feedback) has assembled
    # the response; #bypass_feedback flows through the same formatter.
    response = (graph_result.get("output") or {}).get("response") or {
        "text": "",
        "suggestions": [],
    }
    logger().logp(INFO, tm.format_table())
    await tm.persist_to_db()
    return response


def _extract_interrupt_data(graph_state) -> dict:
    """Extract clarification data from an interrupted graph state.

    When the graph pauses at an ``interrupt(pending)`` call, the *pending*
    value is available in the state snapshot's tasks.  This helper
    converts it into the JSON response the frontend expects.
    """
    pending = {}
    # LangGraph exposes interrupt values via state_snapshot.tasks[].interrupts[].value
    try:
        for task in (graph_state.tasks or []):
            for intr in (task.interrupts or []):
                pending = intr.value
                break
            if pending:
                break
    except Exception:
        pass

    feedback_text = pending.get("feedback_text", "") if isinstance(pending, dict) else str(pending)
    selection_prompt = pending.get("selection_prompt") if isinstance(pending, dict) else None

    # Serialize Pydantic models if needed
    if selection_prompt and hasattr(selection_prompt, "model_dump"):
        selection_prompt = selection_prompt.model_dump()

    result = {
        "text": convert_feedback_to_html(feedback_text) if feedback_text else "",
        "suggestions": [],
    }
    if selection_prompt:
        result["selection_prompt"] = selection_prompt
    return result


@ai_app.get("/ai/health")
async def health_check():
    """
    Checks the health status of the AI API server.
    """
    return {"status": "healthy", "message": "AI API is running"}


@ai_app.post("/ai/characterize_csv")
async def characterize_csv_ai(request: Request):
    """LLM-based CSV characterization, delegated here by file_service.

    file_service offloads the CSV LLM step to this endpoint (see file_service's
    ``characterize_csv_via_ai``) so provider credentials stay confined to the
    ai_service — the same pattern as Excel tidying via ``/ai/preprocess_excel``.

    Runs choregraph's single CSV LLM function (``_llm_characterize_csv``),
    passing the server's boot-selected provider config so choregraph does not
    re-resolve the provider — the same pattern as Excel tidying via
    ``/ai/preprocess_excel``. Accepts a binary CSV sample and returns the dict
    shape choregraph's ``characterize_csv`` expects: ``{header, fieldSeparator,
    recordSeparator, skipLines, modified}``.
    """
    body = await request.body()
    sample_lines = body.decode("utf-8", errors="replace").splitlines(keepends=True)
    llm_cfg = get_llm_config()
    try:
        from choregraph.loaders import _llm_characterize_csv
        result = _llm_characterize_csv(
            sample_lines,
            provider=llm_cfg.provider,
            api_key=llm_cfg.api_key,
            base_url=llm_cfg.base_url,
            model_override=llm_cfg.model_override,
        )
        if result is not None:
            return result
        logger().logp(WARNING, "AI CSV characterization returned no result — using defaults")
    except Exception as e:
        logger().logp(ERROR, f"AI CSV characterization failed: {e}")
    return {
        "header": True,
        "fieldSeparator": ",",
        "recordSeparator": "\n",
        "skipLines": 0,
        "modified": False,
    }


@ai_app.post("/ai/preprocess_excel")
async def preprocess_excel(request: Request):
    """Pre-process an Excel file using LLM sheet cartography.

    Called by file_service as a background task after XLSX upload.
    Runs tidy_excel_data() to detect tables in sheets and produce
    companion parquet files in the same data store directory.

    Request body: {"file_path": "...", "owner_id": "...", "file_id": "..."}
    Returns: {"status": "ok", "companion_files": ["table1.parquet", ...]}
    """
    data = await request.json()
    owner_id = sanitize_filename(data.get("owner_id", ""))
    file_id = sanitize_filename(data.get("file_id", ""))
    file_path = data.get("file_path")
    previous_names = data.get("previous_names")  # hint for reupload name stability

    if not file_path or not file_id:
        raise HTTPException(status_code=400, detail="file_path and file_id are required")
    
    # Ensure file_path is safe within DIVE_PATH
    try:
        file_path = str(safe_path(user_file_path(owner_id, file_id), os.path.basename(file_path)))
    except Exception as e:
        logger().logp(ERROR, f"Invalid file_path for excel preprocessing: {e}")
        raise HTTPException(status_code=400, detail="Invalid file_path")

    llm_cfg = get_llm_config()
    try:
        from choregraph.collection.excel.main import tidy_excel_data
        import pandas as pd

        logger().logp(INFO, f"[preprocess_excel] Starting for {file_path}")
        result_dict = tidy_excel_data(
            path_excel=file_path,
            provider=llm_cfg.provider,
            api_key=llm_cfg.api_key,
            base_url=llm_cfg.base_url,
            model_override=llm_cfg.model_override,
            previous_table_names=previous_names,
        )

        # Write companion parquets alongside the original file
        from choregraph.dtype_inference import infer_dtypes

        store_dir = pathlib.Path(file_path).parent
        companion_files = []
        for table_name, df in result_dict.items():
            if not isinstance(df, pd.DataFrame) or df.empty:
                continue
            infer_dtypes(df)
            # Coerce remaining object columns to str so pyarrow doesn't
            # fail on mixed-type columns (e.g. int + str in same column).
            for col in df.select_dtypes(include=["object"]).columns:
                df[col] = df[col].astype(str)
            parquet_name = f"{table_name}.parquet"
            parquet_path = store_dir / parquet_name
            df.to_parquet(parquet_path, index=False)
            companion_files.append(parquet_name)
            logger().logp(INFO, f"[preprocess_excel] Wrote {parquet_name} ({len(df)} rows)")

        logger().logp(INFO, f"[preprocess_excel] Done: {len(companion_files)} parquet(s)")
        return {"status": "ok", "companion_files": companion_files}

    except Exception as e:
        logger().logp(ERROR, f"[preprocess_excel] Failed for {file_path}: {e}")
        return {"status": "error", "message": str(e), "companion_files": []}


@ai_app.get("/ai/user/settings")
async def get_user_settings(user_id: str):
    """
    Endpoint to get user-specific AI settings.
    Returns a dict so the server can safely .update().
    """
    try:
        user_tone = await state_repo.get_user_tone(user_id)
        settings = {}
        if user_tone:
            settings["ai_tone"] = user_tone

        user_compl_info = await state_repo.get_user_compl_info(user_id)
        if user_compl_info:
            settings["ai_compl_info"] = user_compl_info
        return {"status": "success", "settings": settings}
    except Exception as e:
        logger().logp(ERROR, f"Error retrieving user settings: {e}")
        return {"status": "error", "message": str(e), "settings": {}}

@ai_app.post("/ai/user/settings")
async def update_user_settings(request: Request):
    """
    Update AI-specific user settings (currently only ai_tone).
    Expected body: { "user_id": "<uuid>", "settings": { "ai_tone": "friendly" } }
    """
    try:
        data = await request.json()
        user_id = data.get("user_id")
        settings = data.get("settings", {})
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        # Accept either ai_tone or tone as key
        if "ai_tone" in settings:
            tone = settings.get("ai_tone")
            await state_repo.set_user_tone(user_id, tone)
        if "compl_info" in settings:
            compl_info = settings.get("compl_info")
            await state_repo.set_user_compl_info(user_id, compl_info)
        return {
            "status": "success",
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger().logp(ERROR, f"Error updating user settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user settings")


async def post_stage(room_token: str, stage: str, label: str):
    """Fire-and-forget stage notification to the server."""
    host_srv = SERVER_HOST or "localhost"
    try:
        await httpx_client.post(
            f"https://{host_srv}:{SERVER_PORT}/server/stage",
            json={"room_token": room_token, "stage": stage, "label": label},
            timeout=3.0,
        )
    except Exception:
        pass  # Stage updates are non-critical; don't block the pipeline


# ========================================================================
# Public API endpoint for the SDK — /ai/sdk/process
#
# The SDK builds workspace files locally (choregraph.xml, specifications.xml,
# catalogue_stats.json) using dive + choregraph libraries, then sends them
# here. The server writes them to a temp workspace and runs the same graph
# as the web flow (is_api=True). The graph pauses at
# ``trigger_choregraph_run_node`` so the SDK can execute choregraph locally
# against the user's data (raw data never leaves the user's machine).
#
# Single endpoint, polymorphic on ``session_id`` — mirrors chat_endpoint's
# arun/aresume dispatch:
#
#   * POST /ai/sdk/process  (no session_id)
#       → fresh arun; graph interrupts at trigger_choregraph_run_node
#       → response {status:"awaiting_choregraph", session_id, choregraph_xml,
#                    visualization_plan}
#   * POST /ai/sdk/process  (session_id + post-transform artifacts)
#       → aresume; graph runs viz_processing_branch + asp_solving_node,
#         skips viz_building_node (route_to_viz sees is_api=True)
#       → response {status:"complete", visuspec_xml, explanation, warnings}
#
# Two HTTP calls remain because choregraph executes on the client, but both
# hit the same endpoint and the same graph.
# ========================================================================

def _provision_api_workspace(
    session_id: str,
    owner_id: str,
    choregraph_xml: str = "",
    specifications_xml: str = "",
    catalogue_stats_json: str = "",
) -> pathlib.Path:
    """Write SDK-provided files to a temp workspace.

    The graph nodes read from ``workspace_path / choregraph.xml`` etc.
    so we need them on disk. No file building — just writing what the
    SDK already built.
    """
    from shared.workspace import workspace_path, write_metadata
    from choregraph.metadata import Metadata

    owner_id = sanitize_filename(owner_id)
    session_id = sanitize_filename(session_id)
    ws = workspace_path(owner_id, session_id)
    ws.mkdir(parents=True, exist_ok=True)

    if choregraph_xml:
        (ws / "choregraph.xml").write_text(choregraph_xml, encoding="utf-8")
    if specifications_xml:
        (ws / "specifications.xml").write_text(specifications_xml, encoding="utf-8")
    if catalogue_stats_json:
        metadata = Metadata(ws)
        metadata.write_raw_cache(catalogue_stats_json)

    write_metadata(owner_id, session_id, {"datasets": []})
    return ws


async def _cleanup_stale_api_sessions():
    """Clean up stale API checkpoints and workspaces on startup.

    API sessions (thread_id starting with ``api-``) cannot survive a
    service restart — the graph state is lost. This removes orphaned
    checkpoint rows and temp workspace directories.
    """
    try:
        from llm_processing.checkpointer import _pool
        async with _pool.connection() as conn:
            await conn.execute(
                "DELETE FROM checkpoints WHERE thread_id LIKE 'api-%'"
            )
            await conn.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id LIKE 'api-%'"
            )
            await conn.execute(
                "DELETE FROM checkpoint_blobs WHERE thread_id LIKE 'api-%'"
            )
        logger().logp(INFO, "Cleaned up stale API checkpoints.")
    except Exception as e:
        logger().logp(WARNING, f"Failed to clean API checkpoints: {e}")

    # Clean up stale API workspaces
    try:
        api_ws_root = pathlib.Path(DIVE_PATH)
        for owner_dir in api_ws_root.iterdir():
            if not owner_dir.is_dir():
                continue
            ws_dir = owner_dir / "workspaces"
            if not ws_dir.exists():
                continue
            for ws in ws_dir.iterdir():
                if ws.is_dir() and ws.name.startswith("api-"):
                    shutil.rmtree(ws, ignore_errors=True)
        logger().logp(INFO, "Cleaned up stale API workspaces.")
    except Exception as e:
        logger().logp(WARNING, f"Failed to clean API workspaces: {e}")


def _cleanup_api_workspace(session_id: str, owner_id: str) -> None:
    from shared.workspace import workspace_path
    ws = workspace_path(owner_id, session_id)
    if ws.exists():
        shutil.rmtree(ws, ignore_errors=True)


@ai_app.post("/ai/sdk/process")
async def api_sdk_process(request: Request):
    """Single SDK endpoint — polymorphic on ``session_id``.

    Fresh turn (no ``session_id``):
        body: ``{prompt, choregraph_xml, catalogue_stats, owner_id}``
        → fresh ``main_graph.arun`` with ``is_api=True``.
        → graph interrupts at ``trigger_choregraph_run_node``.
        → response ``{status:"awaiting_choregraph", session_id,
                       choregraph_xml, visualization_plan}``.

    Resume (``session_id`` + post-transform artifacts):
        body: ``{session_id, owner_id, choregraph_xml, specifications_xml,
                 catalogue_stats}``
        → ``main_graph.aresume``.
        → graph runs ``viz_processing_branch`` + ``asp_solving_node``;
          ``route_to_viz`` ends at END for ``is_api=True``.
        → response ``{status:"complete", visuspec_xml, explanation,
                       warnings}``.

    The checkpoint + session workspace are cleaned on completion.
    """
    import uuid

    data = await request.json()
    session_id = data.get("session_id") or ""
    owner_id = data.get("owner_id", "anonymous")
    is_resume = bool(session_id)

    tm = TurnMetrics()
    set_turn_metrics(tm)
    tm.set_context(
        room_id=session_id or "fresh",
        owner_id=owner_id,
        user_id="api",
        source="sdk",
    )

    if is_resume:
        specifications_xml = data.get("specifications_xml", "")
        choregraph_xml = data.get("choregraph_xml", "")
        catalogue_stats = data.get("catalogue_stats", "")
        if not specifications_xml:
            raise HTTPException(
                status_code=400,
                detail="specifications_xml is required when resuming with a session_id",
            )
    else:
        prompt = data.get("prompt", "")
        choregraph_xml = data.get("choregraph_xml", "")
        catalogue_stats = data.get("catalogue_stats", "")
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt is required")
        if not choregraph_xml:
            raise HTTPException(status_code=400, detail="choregraph_xml is required")
        session_id = f"api-{uuid.uuid4()}"
        tm.set_context(room_id=session_id, owner_id=owner_id, user_id="api", source="sdk")

    llm_cfg = get_llm_config()
    graph_config = {
        "configurable": {
            "thread_id": session_id,
            "llm_config": llm_cfg,
        }
    }

    try:
        if is_resume:
            ws = _provision_api_workspace(
                session_id, owner_id,
                choregraph_xml=choregraph_xml,
                specifications_xml=specifications_xml,
                catalogue_stats_json=catalogue_stats,
            )
            await main_graph.aresume(
                {"reason": "sdk_processing_complete"},
                config=graph_config,
            )
        else:
            ws = _provision_api_workspace(
                session_id, owner_id,
                choregraph_xml=choregraph_xml,
                catalogue_stats_json=catalogue_stats,
            )
            state = WorkflowState()
            state.input = {
                "raw_user_input": data.get("prompt", ""),
                "room_id": session_id,
                "owner_id": owner_id,
                "user_id": None,
                "is_an_upload_message": False,
                "is_selection": False,
                "cookies": {},
                "additional_info": {},
                "room_token": None,
                "message_history": [],
                "is_api": True,
            }
            await main_graph.arun(state, config=graph_config)

        # --- Did the graph pause at an interrupt? ---
        try:
            post_state = await main_graph.aget_state(graph_config)
            paused = bool(post_state and post_state.next)
        except Exception:
            post_state = None
            paused = False

        if paused:
            processing = (post_state.values or {}).get("processing", {}) if post_state else {}
            completed_choregraph = ""
            cg_path = ws / "choregraph.xml"
            if cg_path.exists():
                completed_choregraph = cg_path.read_text(encoding="utf-8")
            logger().logp(INFO, tm.format_table())
            if is_resume:
                await tm.update_in_db()
            else:
                await tm.persist_to_db()
            # Do NOT clean up workspace or checkpoint — resume needs them.
            return {
                "status": "awaiting_choregraph",
                "session_id": session_id,
                "choregraph_xml": completed_choregraph,
                "visualization_plan": processing.get("plan", ""),
            }

        # --- Graph completed. Read the final spec + ASP status from state. ---
        try:
            final_state = await main_graph.aget_state(graph_config)
            final_processing = (final_state.values or {}).get("processing", {}) if final_state else {}
        except Exception:
            final_processing = {}

        asp = final_processing.get("asp") or {}
        spec_path = ws / "specifications.xml"
        visuspec_xml = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""

        if not visuspec_xml:
            raise HTTPException(status_code=500, detail="No visualization XML generated")

        explanation = "Visualization generated"
        warnings: list[str] = []
        if asp and not asp.get("success", True):
            warnings.append(f"ASP optimization failed: {asp.get('log', '')}")
            explanation = "Visualization generated with reduced optimization"

        logger().logp(INFO, tm.format_table())
        if is_resume:
            await tm.update_in_db()
        else:
            await tm.persist_to_db()

        _cleanup_api_workspace(session_id, owner_id)
        try:
            await clear_thread(session_id)
        except Exception:
            pass

        return {
            "status": "complete",
            "session_id": session_id,
            "visuspec_xml": visuspec_xml,
            "explanation": explanation,
            "warnings": warnings,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger().logp(ERROR, f"SDK process failed ({'resume' if is_resume else 'fresh'}): {e}")
        try:
            if is_resume:
                await tm.update_in_db()
            else:
                await tm.persist_to_db()
        except Exception:
            pass
        _cleanup_api_workspace(session_id, owner_id)
        try:
            await clear_thread(session_id)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed: {e}")
