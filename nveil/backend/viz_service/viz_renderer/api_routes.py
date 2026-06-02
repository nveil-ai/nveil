# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Clément Baraille
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI routes for the visualization service command API."""
import json
import os
import signal
import httpx
from datetime import datetime
from pathlib import Path

from choregraph import Choregraph
from choregraph.connectors import DiveConnector
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from helpers import viewer_utils as helper
from trame.app import asynchronous
from logger import DEBUG, ERROR, INFO, WARNING, logger
from shared.workspace import workspace_path as get_workspace_path

from shared.security import safe_path, sanitize_filename, sanitize_file_path

from shared.secrets import get_secret

SERVER_HOST = get_secret("SERVER_HOST") or "localhost"
LOCAL = get_secret("LOCAL")


# Create router for viz API endpoints
router = APIRouter(prefix="/viz", tags=["viz"])


@router.get("/poweroff")
async def shutdown():
    """Shutdown the visualization server."""
    import threading

    def shutdown_servers():
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=shutdown_servers).start()
    return {"status": "shutting down"}


async def reload_kedro_viz(app):
    """Stop then restart the Kedro Viz server for the current workspace."""
    app._stop_kedro_viz()
    ctx = app.contexts.get("main")
    if ctx and ctx.workspace_path:
        ws = ctx.workspace_path
        cg_path = Path(ws) / "choregraph.xml"
        await app.run_kedro_viz(ws, choregraph_xml_path=cg_path if cg_path.exists() else None)


@router.post("/reload-kedro")
async def reload_kedro_endpoint(request: Request):
    """Explicitly trigger a reload of the Kedro Viz server."""
    app = request.app.state.trame_app
    await reload_kedro_viz(app)
    return {"status": "reloading"}


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


@router.get("/status")
async def pod_status(request: Request):
    """Combined status endpoint for server-side health checks and idle detection.

    Returns room context, idle time, and mode so the server pool manager can
    make all scheduling decisions without the pod needing to self-manage.
    """
    app = request.app.state.trame_app
    idle_seconds = (datetime.now() - app.last_activity).total_seconds()
    return {
        "room_id": app.room_id,
        "owner_id": app.owner_id,
        "idle_seconds": idle_seconds,
        "mode": app.mode,
        "kedro_ready": getattr(app, "_kedro_viz_ready", False),
    }


@router.get("/current-spec")
async def current_spec(request: Request):
    """Return the filename of the specification XML currently being displayed."""
    app = request.app.state.trame_app
    xml_path = app.current_xml_path
    filename = Path(xml_path).name if xml_path else None
    return {"current_xml_filename": filename}


@router.post("/export-spec")
async def export_spec(request: Request):
    """Bake the live widget state into the source XML and return its filename.

    Called by the server's ``export_panel`` flow. The viz pod parses the spec
    held in memory, mutates each mark with the current state values via
    ``apply_widget_state_to_spec`` (pydantic field-name convention), then
    overwrites the source XML in place so the next viz load reads the baked
    values back as the initial state. Dashboard panels render from this XML
    with no separate widget_state dict.
    """
    app = request.app.state.trame_app
    ctx = app.contexts.get("main")
    if ctx is None or ctx.vl is None or ctx.vl.vs is None or not ctx.current_xml_path:
        return JSONResponse({"error": "No active spec to export"}, status_code=400)

    from dive.builder.construction.apply_widget_state import apply_widget_state_to_spec
    from dive.xml.serializer import save_to_file

    # Collect every namespaced widget key the app knows about. WIDGET_KEYS lists
    # all "<tag>.<field>" entries; apply_widget_state_to_spec picks out only the
    # ones whose prefix matches a mark in the spec.
    widget_state = {}
    for key in type(app).WIDGET_KEYS:
        val = getattr(app.state, key, None)
        if val is not None:
            widget_state[key] = val

    apply_widget_state_to_spec(ctx.vl.vs, widget_state)
    save_to_file(ctx.vl.vs, ctx.current_xml_path)
    return {"spec_filename": Path(ctx.current_xml_path).name}


@router.post("/set_plot_theme")
async def set_plot_theme(request: Request):
    """Set the PlotTheme for all panels and rebuild visualizations."""
    app = request.app.state.trame_app
    data = await request.json()
    theme = data.get("theme", "deep_blue")
    if theme not in ("deep_blue", "white", "paper", "dark", "grey"):
        return {"status": "error", "detail": "Invalid theme"}

    rebuilt = 0
    for panel_id, ctx in app.contexts.items():
        key = ctx.state_key("PlotTheme")
        app.state[key] = theme
        if ctx.vl.currentFrame is not None:
            app.update_viz_for_context(ctx, notify=False)
            rebuilt += 1

    return {"status": "ok", "theme": theme, "rebuilt": rebuilt}


@router.options("/app/{full_path:path}")
async def viz_app_options(full_path: str):
    """Handle OPTIONS requests for /viz/app/* paths."""
    return Response(status_code=200, headers={"Allow": "GET,POST,OPTIONS"})


@router.get("/app/{full_path:path}")
async def viz_app_get(full_path: str):
    """Handle GET requests for /viz/app/* paths.

    Return an empty 200 response — the real Trame endpoints use POST/WS for RPC.
    """
    return Response(status_code=200, content="", media_type="text/html")


@router.post("/app/{full_path:path}")
async def viz_app_post(request: Request, full_path: str):
    """Permissive POST handler for /viz/app/* probes.

    Some Trame clients post to /viz/app/<name>/ during startup. If the
    application does not expose a POST route for the exact subpath, the
    browser console shows 405 Method Not Allowed. This handler accepts any
    POST to /viz/app/* and returns 200, keeping behavior non-intrusive.
    """
    try:
        # attempt to consume body if present to avoid connection resets
        await request.body()
    except Exception:
        pass
    return Response(status_code=200, content="", media_type="text/plain")


@router.post("/handle_command")
async def handle_command(request: Request):
    """Handle visualization commands from the server."""
    app = request.app.state.trame_app
    data = await request.json()
    cmd_room_token = data.get("room_token")

    # Reject stale commands targeting a room this pod no longer serves
    if cmd_room_token and app.room_token and cmd_room_token != app.room_token:
        logger().warning(
            f"Ignoring stale command: pod serves room {app.room_token[:8]}, "
            f"command targets {cmd_room_token[:8]}"
        )
        return JSONResponse({"status": "stale_room", "message": "Room context has changed"})

    app.room_token = cmd_room_token
    app.update_activity()

    await helper.notify_host(
        SERVER_HOST,
        app.room_token,
        "trame_state_update",
        {"state": "processing"},
        LOCAL == "1",
    )

    # Reset error only for build_viz
    if data.get("command") == "build_viz":
        app.state["viz_error"] = None

    generated_file = None
    saved_interval = await app._pause_refresh()
    try:
        if data.get("command") == "build_viz" and data.get("xml_path"):
            generated_file = app.build_viz_from_ui(data["xml_path"])
        else:
            app._record_viz_error(f"Unknown command: {data.get('command')}")
    except Exception as e:
        logger().error(f"Command execution failed: {e}")
        app._record_viz_error(f"Command execution failed: {e}")
    finally:
        app._resume_refresh(saved_interval)

    await helper.notify_host(
        SERVER_HOST,
        app.room_token,
        "trame_state_update",
        {"state": "idle"},
        LOCAL == "1",
    )
    status = "error" if app.state["viz_error"] else "ok"
    viz_log = app.state["viz_log"] or {}
    # Flatten messages/warnings/errors into a string for back-compat text consumers
    details_text = ""
    if isinstance(viz_log, dict):
        details_text = "\n".join(
            viz_log.get("messages", [])
            + [f"Warning: {w}" for w in viz_log.get("warnings", [])]
            + [f"Error: {e}" for e in viz_log.get("errors", [])]
        )
    else:
        details_text = str(viz_log)
    result = {
        "status": status,
        "details": details_text,
        "viz_log": viz_log,
        "error": app.state["viz_error"],
        "viz_file": generated_file,
    }
    # Back-compat: expose per-frame summaries (with embedded data_insights) as
    # the legacy `viz_summary` field that downstream consumers still read.
    if isinstance(viz_log, dict):
        frames_summary = viz_log.get("frames") or []
        if frames_summary and status == "ok":
            result["viz_summary"] = frames_summary
    try:
        wd = app._main_ctx.state_proxy["widget_descriptors"]
        if wd and wd != "[]":
            result["widget_descriptors"] = wd
    except Exception:
        pass
    return result


@router.post("/load_files")
async def load_files(request: Request):
    """Load project files and initialize Choregraph pipeline."""
    app = request.app.state.trame_app
    logger().logp(DEBUG, "[VIZ VIEWER] Received request to load files.")
    app.update_activity()
    data = await request.json()
    if not data.get("room_id") or not data.get("owner_id"):
        return {"status": "error", "details": "Missing room_id or owner_id"}

    room_id = data["room_id"]
    owner_id = data["owner_id"]
    project_dir = get_workspace_path(owner_id, room_id)

    # 1. Setup Choregraph
    cg_xml_path = project_dir / "choregraph.xml"
    spec_xml_path = project_dir / "specifications.xml"


    saved_interval = await app._pause_refresh()
    try:
        if app.choregraph is not None:
            app.choregraph.reset_spec()
            app.choregraph.load(str(cg_xml_path), workspace_path=project_dir)
        else:
            # First init
            app.choregraph = Choregraph(str(cg_xml_path), workspace_path=project_dir)
            app.vl.choregraph = app.choregraph

        # 2. Run Pipeline (Unified Mode)
        # This will:
        # - Read data from RAM if available (Instant)
        # - Update Viz Metadata (.viz/ json files)
        # - Save to disk (for Viz preview)
        run_success, run_error = app.choregraph.run(lazy=True)
        if not run_success:
            return {"status": "error", "details": run_error}

        # --- AUTO-PROMOTE LEAF DATASETS AS INPUTS ---
        # After running the pipeline, any transformation nodes (e.g., tidy_excel_data, extract_json_*)
        # will have produced parquet outputs. We promote these leaf datasets as inputs and remove
        # the transformation nodes, making the promoted datasets directly accessible.
        try:
            promoted = app.choregraph.promote_leaves(remove_source_nodes=True)
            if promoted:
                # Persist changes to choregraph.xml
                app.choregraph.export_to_xml(cg_xml_path)
                logger().logp(INFO, f"Promoted {len(promoted)} leaf datasets as inputs: {[name for _, name in promoted]}")
        except Exception as e:
            logger().logp(WARNING, f"Failed to auto-promote leaf datasets: {e}")
            import traceback
            logger().logp(DEBUG, traceback.format_exc())

        # 3. Update VisuSpec (Metadata)
        # This uses the RAM cache to be instant on 2nd run
        # Now that inputs are registered and moved, metadata extraction will succeed
        DiveConnector.from_choregraph(app.choregraph).update_visuspec_xml(save_to_path=str(spec_xml_path))
        # -----------------------------------

        # 4. Extract and save datasets metadata (including uniques) to metadata.json
        try:
            datasets_meta = app.choregraph.get_datasets_metadata()
            if datasets_meta:
                metadata_path = project_dir / "metadata.json"
                # Sanitize the metadata path to prevent directory traversal
                try:
                    sanitize_file_path(str(metadata_path), DIVE_PATH)
                except ValueError as e:
                    logger().logp(ERROR, f"Invalid metadata path: {e}")
                    raise HTTPException(status_code=400, detail="Invalid metadata path")

                metadata = {}
                if metadata_path.exists():
                    with open(metadata_path, "r") as f:
                        metadata = json.load(f)

                # Write full datasets structure
                metadata["datasets"] = datasets_meta

                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                logger().logp(INFO, f"[VIZ VIEWER] Saved datasets metadata to metadata.json")
        except Exception as e:
            logger().logp(WARNING, f"[VIZ VIEWER] Could not save datasets metadata: {e}")

    except Exception as e:
        logger().logp(ERROR, f"Choregraph Error: {e}")
        return {"status": "error", "details": str(e)}
    finally:
        app._resume_refresh(saved_interval)


    try:
        if app.vl.project is not None:
            app.vl.project.closeProject(False)
    except Exception as e:
        logger().logp(ERROR, f"[VIZ VIEWER] No existing project: {e}")

    # Initialize history list (no need to parse VisuSpec at upload — no marks yet)
    app.current_xml_path = str(project_dir / "specifications.xml")
    app.update_history_list()

    logger().logp(INFO, f"[VIZ VIEWER] Loaded files for room_id: {room_id}")
    return {"status": "ok"}


@router.post("/run_choregraph")
async def run_choregraph(request: Request):
    """Trigger Choregraph execution for a specific room."""
    app = request.app.state.trame_app
    data = await request.json()
    room_id = data.get("room_id")
    owner_id = data.get("owner_id")

    if not room_id or not owner_id:
        return {"status": "error", "details": "Missing room_id or owner_id"}

    app.update_activity()
    project_dir = get_workspace_path(owner_id, room_id)
    cg_path = project_dir / "choregraph.xml"

    saved_interval = await app._pause_refresh()
    try:
        if cg_path.exists():
            if not app.vl.choregraph:
                logger().logp(INFO, f"Initializing Choregraph from {cg_path}")
                app.vl.choregraph = Choregraph(str(cg_path), workspace_path=project_dir)
            else:
                app.vl.choregraph.load(str(cg_path), workspace_path=project_dir)

        logger().logp(INFO, f"Running Choregraph for room {room_id}...")
        run_success, run_error = app.vl.choregraph.run(lazy=True)
        if not run_success:
            logger().logp(ERROR, f"Choregraph run failed: {run_error}")
            return {"status": "error", "error": run_error}

        # Update specifications.xml with transformedData pointers
        spec_xml_path = project_dir / "specifications.xml"
        logger().logp(INFO, f"Updating {spec_xml_path} with transformation results...")
        DiveConnector.from_choregraph(app.vl.choregraph).update_visuspec_xml(save_to_path=str(spec_xml_path))

        # Notify frontend that pipeline data has been updated.
        # trigger_reload() is called internally by notify_kedro_viz_update(),
        # and the React postMessage is sent only after autoreload completes.
        app.notify_kedro_viz_update(updated=True)

        return {"status": "ok"}
    except Exception as e:
        logger().logp(ERROR, f"Choregraph Run Error: {e}")
        return {"status": "error", "details": str(e)}
    finally:
        app._resume_refresh(saved_interval)


@router.post("/refresh_url_sources")
async def refresh_url_sources(request: Request):
    """Re-fetch URL-based inputs and rebuild the visualization."""
    app = request.app.state.trame_app
    data = await request.json()
    room_id = data.get("room_id") or app.room_id
    owner_id = data.get("owner_id") or app.owner_id

    if not room_id or not owner_id:
        return {"status": "error", "details": "Missing room_id or owner_id"}

    project_dir = get_workspace_path(owner_id, room_id)

    try:
        cg = app.choregraph
        if cg is None:
            return {"status": "error", "details": "Choregraph not initialized"}

        # Re-fetch URL-based inputs
        from choregraph.fetcher import fetch_inputs
        url_inputs = [inp for inp in cg.spec.inputs if inp.url]
        if not url_inputs:
            return {"status": "ok", "details": "No URL sources to refresh"}

        fetched = fetch_inputs(cg.spec.inputs, project_dir)
        if fetched == 0:
            return {"status": "ok", "details": "No URL sources updated"}

        # Re-export choregraph.xml with updated locations
        cg_xml_path = project_dir / "choregraph.xml"
        cg.export_to_xml(cg_xml_path)
        cg._ensure_wrapper()

        # Re-run pipeline (lazy=True detects mtime change)
        run_success, run_error = cg.run(lazy=True)
        if not run_success:
            return {"status": "error", "details": run_error}

        # Update specifications.xml
        spec_xml_path = project_dir / "specifications.xml"
        DiveConnector.from_choregraph(cg).update_visuspec_xml(
            save_to_path=str(spec_xml_path)
        )

        # Rebuild viz if one exists
        if hasattr(app, "current_xml_path") and app.current_xml_path:
            app.build_viz_from_ui(app.current_xml_path)

        # Notify frontend
        await helper.notify_host(
            SERVER_HOST,
            app.room_token,
            "data_refreshed",
            {"source": "url_refresh", "fetched": fetched},
            LOCAL == "1",
        )

        return {"status": "ok", "fetched": fetched}
    except Exception as e:
        logger().logp(ERROR, f"URL refresh error: {e}")
        return {"status": "error", "details": str(e)}


@router.post("/set_refresh_interval")
async def set_refresh_interval(request: Request):
    """Set the auto-refresh interval for URL sources."""
    app = request.app.state.trame_app
    data = await request.json()
    interval = data.get("interval")

    # Validate: None/0 = disable, otherwise minimum 5 seconds
    if interval is not None and interval != 0:
        interval = max(int(interval), 5)
    else:
        interval = None

    app.set_refresh_interval(interval)
    return {"status": "ok", "interval": interval}


@router.post("/assign")
async def assign_to_room(request: Request):
    """Assign this pool pod to a room. Called by server after pool.acquire().

    Re-entrant: if already assigned to a room, performs a context switch.
    Synchronous: blocks until the pod is ready. The _assign_lock serializes
    concurrent requests so rapid switches are handled cleanly.
    """
    app = request.app.state.trame_app
    data = await request.json()
    mode = data.get("mode", "chat")
    is_switch = app.room_id is not None

    async with app._assign_lock:
        if is_switch:
            logger().logp(INFO, f"Re-entrant assign: switching from {app.room_id[:8]} to {data['room_id'][:8]}")

        app.room_token = data["room_token"]
        app.room_id = data["room_id"]
        app.owner_id = data["owner_id"]
        app.mode = mode
        app.update_activity()

        try:
            if is_switch:
                await app._do_context_switch(data)
            elif mode == "dashboard":
                app.init_dashboard_mode(data.get("panels", []))
            else:
                await app.start_choregraph(app.room_workspace_path)

            # Apply export features from server (resolved during room assignment)
            export_features = data.get("export_features")
            if export_features and mode == "chat":
                sp = app._main_ctx.state_proxy
                for fmt in ("png", "jpeg", "svg", "pdf"):
                    sp[f"export_{fmt}_disabled"] = not export_features.get(fmt, False)
                sp.dirty("export_png_disabled", "export_jpeg_disabled",
                         "export_svg_disabled", "export_pdf_disabled")

            logger().logp(INFO, f"Pod assigned: room={app.room_id[:8]}, owner={app.owner_id[:8]}, mode={mode}")
            return {"status": "ready", "room_id": app.room_id, "mode": mode}
        except Exception as e:
            logger().logp(ERROR, f"Assign failed: {e}")
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.post("/release_room")
async def release_room(request: Request):
    """Release the current room context without assigning a new one.

    Pod goes to idle state (assigned to user, no active room).
    """
    app = request.app.state.trame_app
    if app.room_id is None:
        return {"status": "already_idle"}

    old_room_id = app.room_id
    await app._pause_refresh()
    app.release_room()
    logger().logp(INFO, f"Room {old_room_id[:8]} released, pod now idle")
    return {"status": "released", "old_room_id": old_room_id}


@router.post("/refresh_panel/{panel_id}")
async def refresh_panel(request: Request, panel_id: str):
    """Re-fetch URL-based inputs and rebuild a specific dashboard panel."""
    app = request.app.state.trame_app

    if panel_id not in app.contexts:
        return {"status": "error", "details": f"Panel {panel_id} not found"}

    ctx = app.contexts[panel_id]
    if not ctx.choregraph or not ctx.workspace_path:
        return {"status": "error", "details": f"Panel {panel_id} not initialized"}

    try:
        from choregraph.fetcher import fetch_inputs
        from choregraph.connectors import DiveConnector

        url_inputs = [inp for inp in ctx.choregraph.spec.inputs if inp.url]
        if not url_inputs:
            return {"status": "ok", "details": "No URL sources to refresh"}

        fetched = fetch_inputs(ctx.choregraph.spec.inputs, ctx.workspace_path)
        if fetched == 0:
            return {"status": "ok", "details": "No URL sources updated"}

        cg_xml = ctx.workspace_path / "choregraph.xml"
        ctx.choregraph.export_to_xml(cg_xml)
        ctx.choregraph._ensure_wrapper()

        run_success, run_error = ctx.choregraph.run(lazy=False)
        if not run_success:
            return {"status": "error", "details": run_error}

        spec_xml = ctx.workspace_path / "specifications.xml"
        DiveConnector.from_choregraph(ctx.choregraph).update_visuspec_xml(
            save_to_path=str(spec_xml)
        )

        app.build_viz_for_context(ctx, str(spec_xml))
        return {"status": "ok", "fetched": fetched}
    except Exception as e:
        logger().logp(ERROR, f"Panel {panel_id} refresh error: {e}")
        return {"status": "error", "details": str(e)}


@router.post("/refresh_all")
async def refresh_all_panels(request: Request):
    """Re-fetch URL sources and rebuild all dashboard panels."""
    app = request.app.state.trame_app
    results = {}

    for panel_id, ctx in app.contexts.items():
        if panel_id == "main":
            continue
        if not ctx.choregraph or not ctx.workspace_path:
            results[panel_id] = "not_initialized"
            continue

        try:
            from choregraph.fetcher import fetch_inputs
            from choregraph.connectors import DiveConnector

            url_inputs = [inp for inp in ctx.choregraph.spec.inputs if inp.url]
            if not url_inputs:
                results[panel_id] = "no_url_sources"
                continue

            fetched = fetch_inputs(ctx.choregraph.spec.inputs, ctx.workspace_path)
            if fetched == 0:
                results[panel_id] = "no_changes"
                continue

            cg_xml = ctx.workspace_path / "choregraph.xml"
            ctx.choregraph.export_to_xml(cg_xml)
            ctx.choregraph._ensure_wrapper()

            run_success, run_error = ctx.choregraph.run(lazy=False)
            if not run_success:
                results[panel_id] = f"pipeline_error: {run_error}"
                continue

            spec_xml = ctx.workspace_path / "specifications.xml"
            DiveConnector.from_choregraph(ctx.choregraph).update_visuspec_xml(
                save_to_path=str(spec_xml)
            )

            app.build_viz_for_context(ctx, str(spec_xml))
            results[panel_id] = f"ok (fetched={fetched})"
        except Exception as e:
            results[panel_id] = f"error: {e}"

    return {"status": "ok", "panels": results}


# -----------------------------------------------------------------------------
# Kedro Viz Proxy Routes (CSS injection + label replacement)
# -----------------------------------------------------------------------------


@router.get("/kedro-viz/health")
async def kedro_viz_health(request: Request):
    """Check if Kedro Viz server is ready."""
    app = request.app.state.trame_app

    if hasattr(app, "kedro_viz_server") and app.kedro_viz_server:
        if await app.kedro_viz_server.is_ready():
            return {"status": "ready", "port": app.kedro_viz_server.port}

    return Response(
        content='{"status": "not_ready"}',
        status_code=503,
        media_type="application/json",
    )


@router.api_route("/kedro-viz/{path:path}")
async def kedro_viz_proxy(request: Request, path: str = ""):
    """Proxy to Kedro Viz with CSS injection and label replacement.

    - HTML responses: Inject custom CSS
    - JSON responses: Replace sanitized node names with labels (except /api/reload)
    """
    # deploy-viz-metadata only exists in Kedro Viz "load from file" mode, not "run from project"
    if path == "api/deploy-viz-metadata":
        return Response(
            content='{"timestamp": "16.02.2026 10:21:54", "version": "12.3.0"}',
            media_type="application/json",
        )

    import json as json_module
    app = request.app.state.trame_app
    if not hasattr(app, "kedro_viz_server") or not app.kedro_viz_server:
        logger().logp(WARNING, f"Kedro Viz server not configured")
        return Response(content="Kedro Viz server not configured", status_code=503)
    if app._kedro_viz_ready is False:
        if not await app.kedro_viz_server.is_ready():
            logger().logp(WARNING, f"Kedro Viz server not ready yet")
            return Response(content="Kedro Viz server not ready yet", status_code=503)
        app._kedro_viz_ready = True
    kedro_port = app.kedro_viz_server.port

    target_url = f"http://localhost:{kedro_port}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("Host", None)

    try:
        body = await request.body() if request.method in ["POST", "PUT"] else None
        # logger().logp(INFO, f"Kedro Viz proxy: {path}")
        response = await app.httpx_async_client.request(
            method=request.method, url=target_url, headers=headers, content=body, timeout=30.0
        )
        # logger().logp(INFO, f"Kedro Viz proxy response: {response.status_code}")

        content = response.content
        content_type = response.headers.get("content-type", "")
        modified = False
        # logger().logp(INFO, f"Content type: {content_type} {path}")
        # Inject CSS in HTML responses (index page)
        if "text/html" in content_type:
            # logger().logp(INFO, f"Injecting CSS in HTML response {path}")
            try:
                content_str = content.decode("utf-8")
                custom_css = app.kedro_viz_server.get_custom_css()
                css_style = f'<style id="nveil-custom-css">{custom_css}</style>'
                if (
                    "</head>" in content_str
                    and 'id="nveil-custom-css"' not in content_str
                ):
                    # logger().logp(INFO, f"Injecting CSS in HTML response2 {path}")
                    content_str = content_str.replace(
                        "</head>", f"{css_style}</head>"
                    )
                    content = content_str.encode("utf-8")
                    modified = True
            except Exception:
                logger().logp(ERROR, "Failed to inject CSS in HTML response")

        # Replace labels in JSON responses (except /api/reload - must stay unchanged for ETag)
        elif (
            "application/json" in content_type
            and path.startswith("api/")
            and "reload" not in path
        ):
            # Read label_mapping.json directly from workspace - always fresh
            label_mapping = {}
            if (
                hasattr(app, "choregraph")
                and app.choregraph
                and app.choregraph.workspace_path
            ):
                mapping_file = (
                    app.choregraph.workspace_path
                    / "pipeline"
                    / "label_mapping.json"
                )
                if mapping_file.exists():
                    try:
                        with open(mapping_file, "r", encoding="utf-8") as f:
                            label_mapping = json_module.load(f)
                    except Exception:
                        pass

            if label_mapping:
                try:
                    data = json_module.loads(content)
                    if "nodes" in data and isinstance(data["nodes"], list):
                        for node in data["nodes"]:
                            if isinstance(node, dict) and "name" in node:
                                sanitized_name = node["name"]
                                if sanitized_name in label_mapping:
                                    node["name"] = label_mapping[sanitized_name]

                    content = json_module.dumps(data).encode("utf-8")
                    modified = True
                except (json_module.JSONDecodeError, KeyError):
                    pass

        # Build response headers - exclude content-length if we modified content
        excluded = {"transfer-encoding"}
        if modified:
            excluded.add("content-length")

        resp_headers = {
            k: v for k, v in response.headers.items() if k.lower() not in excluded
        }

        # Prevent browser caching of API responses — stale data after a
        # room switch would show the previous room's graph.
        if path.startswith("api/"):
            resp_headers["Cache-Control"] = "no-store"

        return Response(
            content=content,
            status_code=response.status_code,
            headers=resp_headers,
        )

    except httpx.RequestError as e:
        # logger().logp(WARNING, f"Kedro Viz proxy error: {e}")
        return Response(content=f"Kedro Viz proxy error: {e}", status_code=502)
