# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Viz pool configuration loader.

Resolution order (highest priority wins):
  1. K8s mounted secret  (/etc/secrets/{KEY})
  2. Environment variable
  3. YAML config file     (viz_pool_config.yaml)
  4. Code-level default

The YAML path is resolved from VIZ_POOL_CONFIG env var, falling back to
``viz_pool_config.yaml`` next to this file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from utils import get_secret
from logger import INFO, logger

_CONFIG_DIR = Path(__file__).parent
_DEFAULT_CONFIG_PATH = _CONFIG_DIR / "viz_pool_config.yaml"

_yaml_data: Optional[dict] = None
_loaded = False


def _load_yaml() -> dict:
    global _yaml_data, _loaded
    if _loaded:
        return _yaml_data or {}

    _loaded = True
    config_path = Path(os.getenv("VIZ_POOL_CONFIG", str(_DEFAULT_CONFIG_PATH)))
    if not config_path.exists():
        return {}

    try:
        import yaml
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        _yaml_data = raw.get("viz_pool", raw)
        logger().logp(INFO, f"Loaded viz pool config from {config_path}")
        return _yaml_data
    except ImportError:
        return {}
    except Exception as e:
        logger().logp(INFO, f"Could not load viz pool config ({config_path}): {e}")
        return {}


# ── env-var name → YAML key mapping ──────────────────────────────────────────

_ENV_TO_YAML = {
    "VIZ_IMAGE":                   "image",
    "DOCKER_NETWORK":              "docker_network",
    "SERVER_INTERNAL_HOST":        "server_host",
    "DIVE_VOLUME":                 "dive_volume",
    "CERT_VOLUME":                 "cert_volume",
    "CERT_HOST_DIR":               "cert_host_dir",
    "REPO_HOST_DIR":               "repo_host_dir",
    "VIZ_POOL_MIN_SIZE":           "min_size",
    "VIZ_POOL_BURST_SIZE":         "burst_size",
    "VIZ_POOL_BURST_BUFFER":       "burst_buffer",
    "VIZ_IDLE_TIMEOUT_MINUTES":    "idle_timeout_minutes",
    "VIZ_USER_IDLE_TIMEOUT_MINUTES": "user_idle_timeout_minutes",
    "VIZ_NODE_SELECTOR_ROLE":      "node_selector_role",
    "VIZ_POOL_TIER_AFFINITY":      "pool_tier_affinity",
    "VIZ_VOLUME_TYPE":             "volume_type",
    "VIZ_VOLUME_HOST_PATH":        "volume_host_path",
    "VIZ_TOLERATION_KEY":          "tolerations_key",
    "VIZ_TOLERATION_VALUE":        "tolerations_value",
    "VIZ_TOLERATION_EFFECT":       "tolerations_effect",
    "VIZ_POOL_CONSOLIDATION_MARGIN": "consolidation_margin",
    "VIZ_POOL_MAX_TERMINATING":    "max_terminating",
    "GCP":                         "gcp",
}


def _yaml_get(key: str) -> Optional[str]:
    """Look up *key* in the YAML ``viz_pool`` section."""
    cfg = _load_yaml()
    val = cfg.get(key)
    if val is None:
        return None
    return str(val)


def get(env_key: str, default: str = "") -> str:
    """Get a config value: K8s secret → env → YAML → default."""
    secret = get_secret(env_key)
    if secret is not None and secret != "":
        return secret

    yaml_key = _ENV_TO_YAML.get(env_key)
    if yaml_key:
        yaml_val = _yaml_get(yaml_key)
        if yaml_val is not None:
            return yaml_val

    return default


def get_int(env_key: str, default: int) -> int:
    val = get(env_key, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def get_tolerations() -> list[dict]:
    """Build tolerations list from config (YAML nested list or flat env vars)."""
    cfg = _load_yaml()
    yaml_tols = cfg.get("tolerations")
    if isinstance(yaml_tols, list) and yaml_tols:
        tol = yaml_tols[0]
        key = get_secret("VIZ_TOLERATION_KEY") or tol.get("key", "")
        if key:
            return [{
                "key": key,
                "operator": "Equal",
                "value": get_secret("VIZ_TOLERATION_VALUE") or tol.get("value", "viz"),
                "effect": get_secret("VIZ_TOLERATION_EFFECT") or tol.get("effect", "NoSchedule"),
            }]
        return []

    key = get("VIZ_TOLERATION_KEY")
    if key:
        return [{
            "key": key,
            "operator": "Equal",
            "value": get("VIZ_TOLERATION_VALUE", "viz"),
            "effect": get("VIZ_TOLERATION_EFFECT", "NoSchedule"),
        }]
    return []


def get_resources() -> Optional[dict]:
    """Return pod resource requests/limits from YAML (no env-var override)."""
    cfg = _load_yaml()
    return cfg.get("resources")
