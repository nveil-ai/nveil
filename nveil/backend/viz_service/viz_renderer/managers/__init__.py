# Lazy imports to avoid loading heavy deps at module level.


def __getattr__(name):
    if name == "HistoryManager":
        from .history_manager import HistoryManager
        return HistoryManager
    if name == "KedroVizManager":
        from .kedro_manager import KedroVizManager
        return KedroVizManager
    if name == "URLRefreshManager":
        from .refresh_manager import URLRefreshManager
        return URLRefreshManager
    if name == "VizBuilder":
        from .viz_builder import VizBuilder
        return VizBuilder
    if name == "DashboardManager":
        from .dashboard_manager import DashboardManager
        return DashboardManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
