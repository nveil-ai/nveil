# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Clément Baraille
# SPDX-License-Identifier: AGPL-3.0-or-later

"""VTK visualization backend — thin trame adapter over dive.builder.vtk."""
import time
import vtk
from logger import INFO, logger

DEBUG_FPS = False

_fps_last_time: float = 0.0
_fps_actor: "vtk.vtkTextActor | None" = None
_fps_observer_rw_id: int = 0


def _fps_end_event_callback(obj, event):
    global _fps_last_time, _fps_actor
    now = time.perf_counter()
    if _fps_last_time and _fps_actor is not None:
        elapsed = now - _fps_last_time
        if elapsed > 0:
            _fps_actor.SetInput(f"FPS: {1.0 / elapsed:.1f}")
    _fps_last_time = now


def _setup_fps_overlay(scene):
    global _fps_actor, _fps_observer_rw_id
    if _fps_actor is None:
        _fps_actor = vtk.vtkTextActor()
        _fps_actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
        _fps_actor.GetPositionCoordinate().SetValue(0.05, 0.95)
        prop = _fps_actor.GetTextProperty()
        prop.SetFontSize(14)
        prop.SetJustificationToLeft()
        prop.SetVerticalJustificationToBottom()
        prop.SetColor(0.0, 1.0, 0.0)
        prop.SetBold(True)
        _fps_actor.SetInput("FPS: --")
    scene.renderer.AddActor2D(_fps_actor)
    rw = scene.render_window
    if rw is not None and id(rw) != _fps_observer_rw_id:
        rw.AddObserver("EndEvent", _fps_end_event_callback)
        _fps_observer_rw_id = id(rw)


def ensure_vtk_initialized(ctx):
    """Complete VTK setup on first use (orientation widget, trackball style)."""
    scene = ctx._vtk_scene
    if scene.axes_actor is not None:
        return
    logger().logp(INFO, "[VIZ VIEWER] Completing VTK setup (deferred)...")
    scene.setup_orientation_widget()
    logger().logp(INFO, "[VIZ VIEWER] VTK setup complete.")


def show_vtk_viz(ctx, vizObject, cube_axes, scalar_bars, figure_title=""):
    """Render VTK visualization objects via VtkScene, then push to trame."""
    from dive.builder.clipping import cleanup_camera_observers
    cleanup_camera_observers()

    ensure_vtk_initialized(ctx)

    scene = ctx._vtk_scene
    scene.ctrl_view_update = ctx.ctrl_view_update
    scene.populate(
        vizObject,
        cube_axes=cube_axes,
        scalar_bars=scalar_bars,
        title=figure_title,
        clear=True,
        on_render_ctx=ctx._vtk_scene,
    )

    if DEBUG_FPS:
        _setup_fps_overlay(scene)

    # --- MPR sub-views ---
    has_volume = any(obj.get("volume") for obj in vizObject)
    volume_obj = next((obj for obj in vizObject if obj.get("volume")), None)
    sp = ctx.state_proxy
    show_mpr = bool(sp.get("voxel.showMPR", False))

    if has_volume and volume_obj and show_mpr and scene.mpr_views:
        img_data = volume_obj.get("image_data") or volume_obj["mapper"].GetInput()
        if img_data:
            mpr_ctrl = getattr(ctx, "_mpr_ctrl", {})
            scene.update_mpr(
                img_data, sp,
                transform=volume_obj.get("volume_transform"),
                volume_property=volume_obj.get("volume_property"),
                on_plane_updated=lambda p: mpr_ctrl.get(p, lambda: None)(),
            )

    # Reapply current clipping state after scene rebuild
    clip = scene.clipping
    if clip and clip.get("bounds") is not None:
        from dive.builder.clipping import apply_clipping, register_camera_clip_observer
        if clip["volume_mappers"]:
            apply_clipping(clip["volume_mappers"], clip["bounds"], sp,
                           renderer=scene.renderer, volume=True,
                           transform=clip["transform"])
            register_camera_clip_observer(
                scene.renderer, clip["volume_mappers"], clip["bounds"], sp,
                volume=True, transform=clip["transform"],
            )
        if clip["surface_mappers"]:
            apply_clipping(clip["surface_mappers"], clip["bounds"], sp,
                           renderer=scene.renderer, volume=False)
            register_camera_clip_observer(
                scene.renderer, clip["surface_mappers"], clip["bounds"], sp,
                volume=False,
            )

    scene.reset_camera(force=False)
    scene.render()

    if hasattr(ctx, "ctrl_view_update") and ctx.ctrl_view_update:
        ctx.ctrl_view_update()
    elif hasattr(ctx, "ctrl") and ctx.ctrl:
        ctx.ctrl.view_update()
