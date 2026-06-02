# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later


import numpy as np
import vtk


def to_vtk_string_array(strings):
    arr = vtk.vtkStringArray()
    arr.SetNumberOfValues(len(strings))
    for i, s in enumerate(strings):
        arr.SetValue(i, s)
    return arr


def rotate_camera_around_axis(axis, angle_deg, renderer):
    camera = renderer.GetActiveCamera()
    pos = np.array(camera.GetPosition())
    focal = np.array(camera.GetFocalPoint())
    view_up = np.array(camera.GetViewUp())
    direction = pos - focal

    # Rodrigues' rotation formula
    angle_rad = np.deg2rad(angle_deg)
    axis = axis / np.linalg.norm(axis)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    ux, uy, uz = axis
    R = np.array([
        [cos_a + ux*ux*(1-cos_a),      ux*uy*(1-cos_a)-uz*sin_a, ux*uz*(1-cos_a)+uy*sin_a],
        [uy*ux*(1-cos_a)+uz*sin_a, cos_a + uy*uy*(1-cos_a),      uy*uz*(1-cos_a)-ux*sin_a],
        [uz*ux*(1-cos_a)-uy*sin_a, uz*uy*(1-cos_a)+ux*sin_a, cos_a + uz*uz*(1-cos_a)]
    ])
    new_direction = R @ direction
    new_view_up = R @ view_up
    new_pos = focal + new_direction
    camera.SetPosition(*new_pos)
    camera.SetViewUp(*new_view_up)
    renderer.ResetCameraClippingRange()
