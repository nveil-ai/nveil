"""Local trame wrapper for Apache ECharts.

Exposes:
- ``module`` — trame module definition (use with ``server.enable_module``).
- ``Chart`` — Python widget class wrapping the ``<v-chart>`` Vue component.
"""

from . import module
from .echarts import Chart

__all__ = ["Chart", "module"]
