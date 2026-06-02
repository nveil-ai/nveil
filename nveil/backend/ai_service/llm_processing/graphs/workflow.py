# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import atexit
import datetime
import os

from langgraph.types import Command
from logger import DEBUG, logger

from .workflow_state import WorkflowState


def _build_langfuse_handler():
    """Instantiate a Langfuse CallbackHandler when tracing is enabled, else None.

    Reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from env.
    Opt-in via LANGFUSE_TRACING so default/prod runs pay zero cost.
    """
    if os.getenv("LANGFUSE_TRACING", "").lower() not in ("1", "true", "yes", "on"):
        return None
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception as e:
        logger().logp(DEBUG, f"Langfuse tracing disabled: {e}")
        return None


# Singleton used only as an "is tracing enabled" flag and for flush-on-exit.
# Never passed directly to LangChain callbacks — a fresh handler is created
# per request in _with_tracing() so each invocation gets its own Langfuse
# trace root instead of being nested as a span inside the first trace.
_LANGFUSE_HANDLER = _build_langfuse_handler()
_LANGFUSE_ENABLED = _LANGFUSE_HANDLER is not None


def _new_langfuse_handler():
    """Return a fresh CallbackHandler for a single request."""
    try:
        from langfuse.langchain import CallbackHandler
        return CallbackHandler()
    except Exception:
        return None


def _flush_langfuse_on_exit():
    """Flush pending spans on interpreter shutdown so no traces are lost
    when the AI container is restarted. Best-practice per Langfuse docs."""
    if _LANGFUSE_HANDLER is None:
        return
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception:
        pass


async def _aflush_langfuse() -> None:
    """Flush pending spans at the end of a request. Required because uvicorn
    --reload sends SIGTERM (atexit unreliable) and the OTEL BatchSpanProcessor
    only auto-flushes on a ~5s/15-event threshold — short turns would otherwise
    sit in the buffer until the next restart kills them.

    Langfuse v4 `flush()` is synchronous; we offload it to a thread so the
    event loop is not blocked while the OTEL exporter ships the batch."""
    if not _LANGFUSE_ENABLED:
        return
    try:
        from langfuse import get_client
        await asyncio.to_thread(get_client().flush)
    except Exception as e:
        logger().logp(DEBUG, f"Langfuse flush failed: {e}")


if _LANGFUSE_HANDLER is not None:
    atexit.register(_flush_langfuse_on_exit)


def tag_current_trace(tags: list[str]) -> None:
    """Update the Langfuse trace's `tags` list in-place from inside a
    LangGraph node. No-op when tracing is disabled or the call fails.

    Called from nodes that know more about the request shape than the
    graph root does (classification, planning, feedback) so the trace
    surfaces granular categories — `visualization_request`, `user_question`,
    `upload`, `color_palette_request`, `transformation_feedback`, etc —
    instead of just a static `request` channel tag.

    Tags are ADDITIVE here (cumulative set), so nodes that append to
    `list_steps` can call this each time and the final trace carries the
    union of all categories seen during the turn.
    """
    if not _LANGFUSE_ENABLED:
        return
    try:
        from langfuse import LangfuseOtelSpanAttributes
        from opentelemetry import trace as otel_trace
        # Deduplicate while preserving order
        seen: set[str] = set()
        uniq: list[str] = []
        for t in tags:
            if t and t not in seen:
                seen.add(t)
                uniq.append(t)
        # Langfuse v4 no longer exposes `update_current_trace`; trace-level
        # attributes are set on the active OTEL span via documented attribute
        # keys. Setting TRACE_TAGS rewrites the full list — callers already
        # pass the cumulative set, so this matches the previous semantics.
        span = otel_trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(LangfuseOtelSpanAttributes.TRACE_TAGS, uniq)
    except Exception as e:
        logger().logp(DEBUG, f"Langfuse tag update failed: {e}")


class Workflow:
    # Subclasses override to give Langfuse traces meaningful names and tags.
    trace_name: str = "workflow"
    trace_tags: tuple[str, ...] = ()

    def __init__(self, db, llm_manager, http_client=None, checkpointer=None):
        self.db = db
        self.llm_manager = llm_manager
        self.http_client = http_client
        self.checkpointer = checkpointer
        self.graph = self.compile()

    def compile(self):
        """Must be overridden by subclasses."""
        raise NotImplementedError

    def _with_tracing(self, config):
        """Merge Langfuse callback, session_id, tags, and run_name into a RunnableConfig.

        Pulls `thread_id` from the incoming `configurable` block so multi-turn
        conversations surface as a single Session in the Langfuse UI.
        A fresh CallbackHandler is created per call so each invocation produces
        its own top-level trace rather than being nested inside the first one.
        """
        if not _LANGFUSE_ENABLED:
            return config
        handler = _new_langfuse_handler()
        if handler is None:
            return config
        merged = dict(config or {})

        merged["callbacks"] = [*(merged.get("callbacks") or []), handler]
        merged.setdefault("run_name", self.trace_name)

        metadata = dict(merged.get("metadata") or {})
        configurable = merged.get("configurable") or {}
        thread_id = configurable.get("thread_id")
        if thread_id and "langfuse_session_id" not in metadata:
            metadata["langfuse_session_id"] = str(thread_id)
        if self.trace_tags and "langfuse_tags" not in metadata:
            metadata["langfuse_tags"] = list(self.trace_tags)
        merged["metadata"] = metadata

        return merged

    def run(self, state: WorkflowState, config=None) -> WorkflowState:
        """Execute the workflow using the compiled graph."""
        return self.graph.invoke(state, config=self._with_tracing(config))

    async def arun(self, state: WorkflowState, config=None) -> WorkflowState:
        """Execute the workflow asynchronously using the compiled graph."""
        try:
            return await self.graph.ainvoke(state, config=self._with_tracing(config))
        finally:
            await _aflush_langfuse()

    async def aresume(self, value, config):
        """Resume a previously interrupted graph with the user's response."""
        try:
            return await self.graph.ainvoke(Command(resume=value), config=self._with_tracing(config))
        finally:
            await _aflush_langfuse()

    async def aget_state(self, config):
        """Retrieve the current graph state for the given config (thread)."""
        return await self.graph.aget_state(config)

    async def invoke_stream(self, state: WorkflowState, config=None):
        try:
            async for message_chunk, metadata in self.graph.astream(
                state,
                config=self._with_tracing(config),
                stream_mode="messages",
            ):
                if message_chunk.content:
                    logger().logp(DEBUG, f"Streaming message chunk @ {datetime.datetime.now()}: {metadata}")
                    yield message_chunk.content
        finally:
            await _aflush_langfuse()
