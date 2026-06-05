# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-License-Identifier: AGPL-3.0-or-later

from kedro.config import OmegaConfigLoader

CONFIG_LOADER_CLASS = OmegaConfigLoader
CONFIG_LOADER_ARGS = {"base_env": "base", "default_run_env": "local"}

# 1. Standard Hooks: defined here ONCE.
# They will be picked up automatically by any KedroSession.
try:
    from kedro_viz.integrations.kedro.hooks import DatasetStatsHook, PipelineRunStatusHook
    HOOKS = (DatasetStatsHook(), PipelineRunStatusHook())
except ImportError:
    HOOKS = ()