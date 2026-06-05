# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Local trame wrapper for Apache ECharts.

Exposes:
- ``module`` — trame module definition (use with ``server.enable_module``).
- ``Chart`` — Python widget class wrapping the ``<v-chart>`` Vue component.
"""

from . import module
from .echarts import Chart

__all__ = ["Chart", "module"]
