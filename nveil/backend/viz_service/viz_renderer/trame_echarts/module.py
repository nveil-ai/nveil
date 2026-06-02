# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Trame module definition for the embedded ECharts widget.

Load strategy is split into two tiers so 2D-only pages don't pay the
download cost of the 3D / custom-series extensions:

EAGER (loaded at page init, serially so ordering is guaranteed):
1. ``echarts.min.js`` — Apache ECharts 6.x UMD bundle.
2. ``trame-echarts.js`` — minimal Vue 3 wrapper that exposes a
   ``<v-chart>`` component via a Vue plugin at ``window.trame_echarts``.

LAZY (injected by ``trame-echarts.js`` on first chart that uses them):
3. ``echarts-gl.min.js`` — echarts-gl UMD extension, required for
   ``scatter3D`` / ``line3D`` / ``surface`` / ``flowGL`` series and
   other 3D types. ~640 KB.

Violin uses an inline ``__JSFN__`` renderItem (data-adaptive KDE) so
no external bundle is needed. Contour iso-lines are pre-computed
server-side in Python via ``skimage.measure.find_contours`` — again no
client-side bundle required.

Source of truth for the two echarts JS bundles lives in
``dive/builder/_echarts_assets/`` — dive is the library, it owns the
assets. The wrapper ``trame-echarts.js`` is viz-service-specific and
stays under ``serve/`` alongside this module. We expose the two
directories under different URL prefixes so trame's file server can
resolve each from its own source:

- ``__echarts/<bundle>.js``   → dive's package data
- ``__trame_echarts/trame-echarts.js`` → this module's sibling dir

trame-echarts.js inspects each option at setOption time and loads
only the bundles actually needed — a 2D-only chart never pays the 3D
GL cost.

IMPORTANT — ordering. Trame's client (``Ce`` in the main bundle) loads
plain entries from ``trame__scripts`` **in parallel** via
``Promise.all(... .map(loader))``. Only entries expressed as a
``(url, {"serial": group})`` tuple are serialised, and only within
their group. Without the ``serial`` tag the wrapper has sometimes
evaluated before echarts.min.js finished assigning ``window.echarts``.
Keep the two eager entries below on the same serial group so they
always load in the declared order.

Use via ``server.enable_module(trame_echarts.module)``.
"""
from pathlib import Path

# Viz-service-specific Vue wrapper.
_wrapper_dir = str(Path(__file__).with_name("serve").resolve())

# Source of truth for the echarts UMD bundles lives in dive's package
# data. Resolving via the package's __file__ avoids the importlib
# ``as_file()`` context-manager dance and works for editable installs
# and compiled wheels alike.
import dive.builder._echarts_assets as _dive_echarts_assets  # noqa: E402
_echarts_dir = str(Path(_dive_echarts_assets.__file__).parent)

serve = {
    "__trame_echarts": _wrapper_dir,
    "__echarts": _echarts_dir,
}

# Tuple form ``(url, {"serial": <group>})`` tells trame's client loader
# to execute these scripts sequentially rather than in parallel. The
# group name is arbitrary — it only needs to be unique enough not to
# collide with scripts from other modules. See core.py: the ``Ce``
# helper in the generated client bundle groups serial entries and
# awaits them one-by-one via ``So``.
_SERIAL = {"serial": "trame-echarts"}
scripts = [
    ("__echarts/echarts.min.js", _SERIAL),
    ("__trame_echarts/trame-echarts.js", _SERIAL),
]

vue_use = ["trame_echarts"]
