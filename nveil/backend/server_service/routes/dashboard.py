# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Dashboard management routes: create, list, export panel, layout, start."""

import asyncio
import json
import os

from shared.security import sanitize_filename
from shared.service_client import ServiceClient
from database.core.database import db
from database.core.dependencies import get_dashboard_service, get_room_service
from database.models import user
from database.models.room import RoomType
from database.services.dashboard_service import DashboardService
from database.services.room_service import RoomService
from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse
from logger import DEBUG, ERROR, INFO, WARNING, logger
from pydantic import BaseModel
from room.room import ensure_viz, safe_stop_viz, stop_viz
from user_management.authentification import get_current_user
from user_management.guest_utils import get_shared_dashboard_id
from shared.workspace import workspace_path as get_workspace_path

TEST = os.getenv("TEST")

_viz_client = ServiceClient(verify=True)

router = APIRouter(prefix="/server/dashboards", tags=["dashboards"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateDashboardRequest(BaseModel):
    name: str = None


class RenameDashboardRequest(BaseModel):
    name: str


class ExportPanelRequest(BaseModel):
    source_room_id: str
    title: str = "Untitled"
    spec_filename: str | None = None


class RenamePanelRequest(BaseModel):
    title: str


class UpdateLayoutRequest(BaseModel):
    layout: str  # JSON string of serialized layout


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/create")
async def create_dashboard(
    body: CreateDashboardRequest = None,
    current_user: user.User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    """Create a new dashboard room."""
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guests cannot create dashboards")
    name = body.name if body else None
    dashboard = await dashboard_service.create_dashboard(str(current_user.id), name=name)
    logger().logp(INFO, f"Dashboard created: {str(dashboard.id)[:8]} by user {str(current_user.id)[:8]}")

    return {
        "id": str(dashboard.id),
        "token": str(dashboard.token),
        "name": dashboard.name,
        "type": "dashboard",
        "panel_count": 0,
        "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        "last_activity": dashboard.last_activity.isoformat() if dashboard.last_activity else None,
    }


@router.get("/list")
async def list_dashboards(
    current_user: user.User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
):
    """List all dashboards for the current user. Guests see the shared dashboard."""
    if current_user.is_guest:
        shared_id = await get_shared_dashboard_id(room_service.session)
        if shared_id:
            shared_room = await room_service.room_repo.get_by_id(shared_id)
            if shared_room:
                panel_count = await dashboard_service.panel_repo.count_panels(shared_id)
                return [{
                    "id": shared_id,
                    "token": str(shared_room.token),
                    "name": shared_room.name,
                    "panel_count": panel_count,
                    "created_at": shared_room.created_at.isoformat() if shared_room.created_at else None,
                    "last_activity": shared_room.last_activity.isoformat() if shared_room.last_activity else None,
                }]
        return []

    rooms = await room_service.get_user_rooms(str(current_user.id))
    dashboards = [r for r in rooms if r.type == RoomType.DASHBOARD]

    result = []
    for d in dashboards:
        panel_count = await dashboard_service.panel_repo.count_panels(str(d.id))
        result.append({
            "id": str(d.id),
            "token": str(d.token),
            "name": d.name,
            "panel_count": panel_count,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "last_activity": d.last_activity.isoformat() if d.last_activity else None,
        })
    return result


@router.post("/{dashboard_id}/export-panel")
async def export_panel(
    dashboard_id: str,
    body: ExportPanelRequest,
    current_user: user.User = Depends(get_current_user),
):
    """Copy a source room's workspace into a new dashboard panel."""
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guests cannot export panels")

    # Phase 1 — short DB read: memberships + source room lookup
    async with db.session() as session:
        room_service = RoomService(session)
        membership = await room_service.room_member_repo.get_membership(dashboard_id, str(current_user.id))
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this dashboard")
        src_membership = await room_service.room_member_repo.get_membership(
            body.source_room_id, str(current_user.id))
        if not src_membership:
            raise HTTPException(status_code=403, detail="Not a member of source room")
        source_room = await room_service.room_repo.get_by_id(body.source_room_id)
        src_host = source_room.host if source_room else None
        src_cmd_port = source_room.cmd_port if source_room else None

    # Phase 2 — resolve spec_filename.
    # If the client provided the spec filename (from the message's data-spec-filename),
    # use it directly — the file already exists on disk with the correct state.
    # Otherwise fall back to calling /viz/export-spec on the active viz pod (legacy path).
    spec_filename = None
    if body.spec_filename:
        spec_filename = sanitize_filename(body.spec_filename)
        logger().logp(DEBUG, f"Source room exported spec (from request): {spec_filename}")
    elif src_host and src_cmd_port:
        base_url = f"https://{src_host}:{src_cmd_port}"
        try:
            r = await _viz_client.post(f"{base_url}/viz/export-spec", timeout=10.0)
            if r.ok and isinstance(r.data, dict):
                spec_filename = r.data.get("spec_filename")
                logger().logp(DEBUG, f"Source room exported spec: {spec_filename}")
        except Exception as e:
            logger().logp(WARNING, f"Could not export spec from source viz: {e}")

    # Phase 3 — short DB write: add the panel
    async with db.session() as session:
        dashboard_service = DashboardService(session)
        try:
            panel = await dashboard_service.add_panel(
                dashboard_room_id=dashboard_id,
                source_room_id=body.source_room_id,
                title=body.title,
                spec_filename=spec_filename,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        panel_id = panel.panel_id
        panel_title = panel.title

    logger().logp(INFO, f"Panel {panel_id} exported to dashboard {dashboard_id[:8]}")
    return {
        "panel_id": panel_id,
        "title": panel_title,
        "dashboard_id": dashboard_id,
    }


@router.get("/{dashboard_id}/panels")
async def list_panels(
    dashboard_id: str,
    current_user: user.User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    room_service: RoomService = Depends(get_room_service),
):
    """List all panels in a dashboard."""
    # Guests can access the shared dashboard panels
    if current_user.is_guest:
        shared_id = await get_shared_dashboard_id(room_service.session)
        if dashboard_id != shared_id:
            raise HTTPException(status_code=403, detail="Guests can only access the shared dashboard")
    else:
        membership = await room_service.room_member_repo.get_membership(dashboard_id, str(current_user.id))
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this dashboard")

    panels = await dashboard_service.get_panels(dashboard_id)
    return [
        {
            "panel_id": p.panel_id,
            "title": p.title,
            "source_room_id": str(p.source_room_id) if p.source_room_id else None,
            "order_index": p.order_index,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in panels
    ]


@router.put("/{dashboard_id}/panels/{panel_id}/rename")
async def rename_panel(
    dashboard_id: str,
    panel_id: str,
    body: RenamePanelRequest,
    current_user: user.User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    room_service: RoomService = Depends(get_room_service),
):
    """Rename a panel in a dashboard."""
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guests cannot rename panels")
    membership = await room_service.room_member_repo.get_membership(dashboard_id, str(current_user.id))
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this dashboard")

    try:
        await dashboard_service.rename_panel(dashboard_id, panel_id, body.title.strip()[:255])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"status": "ok", "panel_id": panel_id, "title": body.title.strip()[:255]}


@router.delete("/{dashboard_id}/panels/{panel_id}")
async def delete_panel(
    dashboard_id: str,
    panel_id: str,
    current_user: user.User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    room_service: RoomService = Depends(get_room_service),
):
    """Remove a panel from a dashboard."""
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guests cannot delete panels")
    membership = await room_service.room_member_repo.get_membership(dashboard_id, str(current_user.id))
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this dashboard")

    deleted = await dashboard_service.remove_panel(dashboard_id, panel_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Panel not found")

    return {"status": "deleted", "panel_id": panel_id}


@router.put("/{dashboard_id}/layout")
async def update_layout(
    dashboard_id: str,
    body: UpdateLayoutRequest,
    current_user: user.User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    room_service: RoomService = Depends(get_room_service),
):
    """Save the FlexLayout serialized layout."""
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guests cannot update layouts")
    membership = await room_service.room_member_repo.get_membership(dashboard_id, str(current_user.id))
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this dashboard")

    await dashboard_service.update_layout(dashboard_id, body.layout)
    return {"status": "ok"}


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: str,
    current_user: user.User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    room_service: RoomService = Depends(get_room_service),
):
    """Delete a dashboard and all its panels."""
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guests cannot delete dashboards")
    room = await room_service.room_repo.get_by_id(dashboard_id)
    if not room or room.type != RoomType.DASHBOARD:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if str(room.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Only owner can delete dashboard")

    # Stop viz container if running
    if room.viz_port:
        asyncio.create_task(safe_stop_viz(room))

    try:
        await dashboard_service.delete_dashboard(dashboard_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger().logp(INFO, f"Dashboard {dashboard_id[:8]} deleted by user {str(current_user.id)[:8]}")
    return {"status": "deleted"}


@router.put("/{dashboard_id}/rename")
async def rename_dashboard(
    dashboard_id: str,
    body: RenameDashboardRequest,
    current_user: user.User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    room_service: RoomService = Depends(get_room_service),
):
    """Rename a dashboard."""
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guests cannot rename dashboards")
    room = await room_service.room_repo.get_by_id(dashboard_id)
    if not room or room.type != RoomType.DASHBOARD:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    if str(room.owner_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Only owner can rename dashboard")

    await dashboard_service.rename_dashboard(dashboard_id, body.name.strip()[:255])
    return {"status": "ok", "name": body.name.strip()[:255]}


@router.post("/{dashboard_id}/start")
async def start_dashboard(
    dashboard_id: str,
    room_token: str = Cookie(None),
    current_user: user.User = Depends(get_current_user),
):
    """Start a dashboard room — acquire a viz container and pass panel info."""
    secure = TEST != "1"

    # --- Guest path: shared dashboard panels, guest's own dashboard room for pod ---
    if current_user.is_guest:
        # Phase 1 — DB reads in a single short session
        async with db.session() as session:
            room_service = RoomService(session)
            dashboard_service = DashboardService(session)

            shared_id = await get_shared_dashboard_id(session)
            if not shared_id or dashboard_id != shared_id:
                raise HTTPException(status_code=403, detail="Guests can only start the shared dashboard")

            shared_room = await room_service.room_repo.get_by_id(shared_id)
            if not shared_room:
                raise HTTPException(status_code=404, detail="Shared dashboard not found")

            panels = await dashboard_service.get_panels(shared_id)
            saved_layout = await dashboard_service.get_layout(shared_id)

            # Find or create a dashboard room owned by the guest.
            # Using a separate room (vs the guest's chat room) gives the pool a
            # different room_id so context switches happen naturally.
            guest_id = str(current_user.id)
            all_guest_rooms = await room_service.get_user_rooms(guest_id)
            guest_dash_room = next(
                (r for r in all_guest_rooms if hasattr(r, "type") and r.type == RoomType.DASHBOARD),
                None,
            )
            if not guest_dash_room:
                guest_dash_room = await dashboard_service.create_dashboard(guest_id, name="Guest Dashboard")

            shared_owner_id = str(shared_room.owner_id)
            guest_dash_room_token = str(guest_dash_room.token)

        # Phase 2 — pure compute, no session needed
        panel_list = [{"panel_id": p.panel_id, "title": p.title} for p in panels]
        panels_data = [
            {
                "panel_id": p.panel_id,
                "title": p.title,
                "workspace_path": str(get_workspace_path(shared_owner_id, shared_id) / "panels" / p.panel_id),
            }
            for p in panels
        ]

        # Phase 3 — pod allocation with no DB session held
        viz_status = await ensure_viz(guest_dash_room, assign_extra={"mode": "dashboard", "panels": panels_data})
        if viz_status == "failed":
            raise HTTPException(status_code=500, detail="Failed to start visualization")

        content = {
            "status": "room_ready",
            "room_token": guest_dash_room_token,
            "panels": panel_list,
            "saved_layout": saved_layout,
        }
        resp = JSONResponse(content=content)
        resp.set_cookie(key="room_token", value=guest_dash_room_token, httponly=True, secure=secure, samesite="strict")
        return resp

    # --- Regular user path ---
    # Phase 1 — DB reads in a single short session
    async with db.session() as session:
        room_service = RoomService(session)
        dashboard_service = DashboardService(session)

        room = await room_service.room_repo.get_by_id(dashboard_id)
        if not room or room.type != RoomType.DASHBOARD:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        membership = await room_service.room_member_repo.get_membership(dashboard_id, str(current_user.id))
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this dashboard")

        panels = await dashboard_service.get_panels(dashboard_id)
        saved_layout = await dashboard_service.get_layout(dashboard_id)

        room_owner_id = str(room.owner_id)
        room_token_str = str(room.token)

    # Phase 2 — pure compute
    panel_list = [{"panel_id": p.panel_id, "title": p.title} for p in panels]
    panels_data = [
        {
            "panel_id": p.panel_id,
            "title": p.title,
            "workspace_path": str(get_workspace_path(room_owner_id, dashboard_id) / "panels" / p.panel_id),
        }
        for p in panels
    ]

    # Phase 3 — pod allocation with no DB session held
    viz_status = await ensure_viz(room, assign_extra={"mode": "dashboard", "panels": panels_data})
    if viz_status == "failed":
        raise HTTPException(status_code=500, detail="Failed to start visualization")

    content = {
        "status": "room_ready",
        "room_token": room_token_str,
        "panels": panel_list,
        "saved_layout": saved_layout,
    }
    resp = JSONResponse(content=content)
    resp.set_cookie(key="room_token", value=room_token_str, httponly=True, secure=secure, samesite="strict")
    return resp
