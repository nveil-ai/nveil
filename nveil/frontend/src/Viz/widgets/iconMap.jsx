// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Clément Baraille
// SPDX-License-Identifier: AGPL-3.0-or-later

import {
    MdGradient, MdHighQuality, MdBlurOn, MdScatterPlot,
    MdCropFree, MdBrightness6, MdTune, MdOpacity,
    MdSwapVert, MdFlip, MdInfo, MdBarChart, MdGridOn,
    MdAutoGraph, MdTimeline, MdBubbleChart, MdDonutSmall,
    MdMap, MdHub, MdLayers, Md3dRotation,
    MdAddLocationAlt, MdDelete, MdMyLocation,
    MdCenterFocusWeak, MdNavigation, MdPlayArrow, MdSpeed,
    MdContrast, MdBrightness4, MdLooks, MdShowChart,
    MdAccountTree,
} from 'react-icons/md';
import { IoColorPaletteOutline, IoResizeOutline } from 'react-icons/io5';
import { TbAxisX, TbAxisY } from 'react-icons/tb';

const ICON_MAP = {
    'gradient': MdGradient,
    'hd': MdHighQuality,
    'blur': MdBlurOn,
    'scatter': MdScatterPlot,
    'clip': MdCropFree,
    'clip-x': MdCropFree,
    'clip-y': MdCropFree,
    'clip-z': MdCropFree,
    'clip-camera': MdCenterFocusWeak,
    'diameter': MdBrightness6,
    'palette': IoColorPaletteOutline,
    'tune': MdTune,
    'opacity': MdOpacity,
    'level': MdSwapVert,
    'flip': MdFlip,
    'info': MdInfo,
    'resize': IoResizeOutline,
    'histogram': MdBarChart,
    'grid': MdGridOn,
    'bell-curve': MdAutoGraph,
    'line': MdTimeline,
    'point': MdBubbleChart,
    'contour': MdLayers,
    'donut': MdDonutSmall,
    'map': MdMap,
    'node': MdHub,
    '3d': Md3dRotation,
    'axis-x': TbAxisX,
    'axis-y': TbAxisY,
    'axis-z': Md3dRotation,
    'marker-plus': MdAddLocationAlt,
    'delete': MdDelete,
    'probe': MdMyLocation,
    'arrow': MdNavigation,
    'play': MdPlayArrow,
    'speed': MdSpeed,
    'contrast': MdContrast,
    'brightness': MdBrightness4,
    'looks': MdLooks,
    'smooth': MdShowChart,
    'cluster': MdAccountTree,
};

export function getIcon(name, size = 18) {
    const Icon = ICON_MAP[name];
    if (!Icon) return null;
    return <Icon size={size} />;
}

export default ICON_MAP;
