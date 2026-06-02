# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Python-side wrapper for the ``<v-chart>`` component exposed by
``trame-echarts.js``.

Instantiate a ``Chart(...)`` inside a trame layout to mount a chart element,
call ``chart.update(option)`` to push a new option dict into trame state, and
call ``chart.clear()`` when the *next* update represents a fresh
visualization (new chat plot or history click). The Vue wrapper reactively
calls ``echarts.setOption()`` on option changes and ``chart.clear()`` before
the next ``setOption()`` whenever the clear counter advances.
"""
from trame_client.widgets.core import AbstractElement

from . import module as _module

try:
    from trame_client.encoders.numpy import encode as _numpy_encode
    _HAS_NUMPY_ENCODER = True
except ImportError:
    _HAS_NUMPY_ENCODER = False


def _encode(data):
    if _HAS_NUMPY_ENCODER:
        return _numpy_encode(data)
    return data


class Chart(AbstractElement):
    """A trame wrapper around ``<v-chart>``.

    Parameters
    ----------
    option:
        Optional initial ECharts option dict. May also be set later via
        :meth:`update`.
    theme:
        ECharts theme name (e.g. ``"dark"``). Server-side tokens are read
        by each mark builder via :func:`dive.builder.themes.get_echarts_theme_tokens`
        so this is usually left at ``"default"``.
    auto_resize:
        If True (default), the wrapper observes its container with
        ResizeObserver and calls ``chart.resize()``.
    state_variable_name:
        Override the auto-generated trame state key. Useful when multiple
        charts share data.
    """

    _next_id = 0

    def __init__(
        self,
        option=None,
        theme="default",
        auto_resize=True,
        not_merge=False,
        state_variable_name=None,
        **kwargs,
    ):
        if state_variable_name is None:
            Chart._next_id += 1
            state_variable_name = f"trame__echarts_option_{Chart._next_id}"
        self.__option_key = state_variable_name
        # Second state var carries a monotonic counter; the Vue watcher calls
        # chart.clear() before the next setOption() whenever it advances. That
        # happens on explicit ``chart.clear()`` calls from Python (new chat
        # plot, history click) and never on widget-driven updates (slider
        # drags, theme flips) so those still merge and preserve 3D camera.
        self.__clear_key = f"{state_variable_name}__clear"

        # Reactive binding to the option dict lives in trame state. Static
        # attributes (theme, autoresize, notMerge) flow through **kwargs →
        # trame attrs. ``notMerge`` defaults to False so echarts' native
        # diff handles smart updates on both 2D and 3D options — critical for
        # slider-driven re-renders that shouldn't reset the 3D camera.
        super().__init__(
            "v-chart",
            option=(state_variable_name,),
            clear_counter=(self.__clear_key,),
            theme=theme,
            autoresize=auto_resize,
            not_merge=not_merge,
            **kwargs,
        )

        if self.server:
            self.server.enable_module(_module)

        self.server.state.setdefault(self.__option_key, {})
        self.server.state.setdefault(self.__clear_key, 0)

        self._attr_names += [
            "option",
            "theme",
            "autoresize",
            ("init_options", "initOptions"),
            ("not_merge", "notMerge"),
            ("lazy_update", "lazyUpdate"),
            ("clear_counter", "clearCounter"),
        ]
        self._event_names += [
            "click",
            "dblclick",
            "mouseover",
            "mouseout",
            "mousemove",
            ("legend_select_changed", "legendselectchanged"),
            ("chart_ready", "chart-ready"),
        ]

        if option is not None:
            self.update(option)

    @property
    def key(self):
        """Return the name of the trame state variable holding the option."""
        return self.__option_key

    def update(self, option):
        """Push a new option dict to the client.

        ``option`` is written into trame state; the Vue wrapper watches the
        binding and calls ``echarts.setOption()``.
        """
        if option is None:
            return
        self.server.state[self.__option_key] = _encode(option)

    def clear(self):
        """Signal that the *next* ``update(option)`` starts a fresh chart.

        The Vue wrapper watches the clear counter; when it advances, it calls
        ``chart.clear()`` on the ECharts instance right before the next
        ``setOption()``. Use this when a new visualization replaces the
        current one (new chat plot, history button click) so stale series /
        visualMap / formatters from the previous chart don't leak through.

        Do *not* call this for widget-driven updates (slider drags, theme
        flips) — those should merge naturally so the 3D camera position
        stays put.
        """
        current = self.server.state[self.__clear_key] or 0
        self.server.state[self.__clear_key] = current + 1
