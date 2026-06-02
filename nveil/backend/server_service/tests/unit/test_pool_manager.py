# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for VizPoolManager — affinity shape, consolidation, terminating cap.

K8s clients are mocked; no cluster required.
"""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("kubernetes", reason="kubernetes not installed")


@pytest.fixture(autouse=True)
def _restore_env():
    """Restore os.environ between tests so env overrides don't bleed across cases."""
    saved = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(saved)


def _make_manager(env=None):
    """Build a VizPoolManager with the K8s config + API stubbed.

    Env vars are written directly to ``os.environ`` (not wrapped in a scoped
    ``patch.dict``) so that ``get_secret`` calls made from the manager's
    *methods* — not just its constructor — see the overrides. The autouse
    ``_restore_env`` fixture undoes these mutations between tests.
    """
    env = env or {}
    defaults = {
        "VIZ_IMAGE": "viz:test",
        "VIZ_POOL_MIN_SIZE": "5",
        "VIZ_POOL_BURST_BUFFER": "5",
        "VIZ_POOL_BURST_SIZE": "30",
        "VIZ_POOL_CONSOLIDATION_MARGIN": "2",
        "VIZ_POOL_MAX_TERMINATING": "2",
        "VIZ_NODE_SELECTOR_ROLE": "viz",
    }
    defaults.update(env)
    os.environ.update(defaults)
    with patch("kubernetes.config.load_incluster_config", side_effect=Exception), \
         patch("kubernetes.config.load_kube_config"), \
         patch("kubernetes.client.CoreV1Api") as core_cls, \
         patch("kubernetes.client.AppsV1Api") as apps_cls:
        from room.pool_manager import VizPoolManager
        mgr = VizPoolManager(namespace="viz-service")
    mgr.v1 = MagicMock()
    mgr.apps_v1 = MagicMock()
    return mgr


def _pod(pool_id, status, node=None):
    labels = {"pool-id": pool_id, "status": status, "app": "viz-pool"}
    meta = SimpleNamespace(name=f"viz-pool-{pool_id}", labels=labels, annotations={})
    spec = SimpleNamespace(node_name=node)
    return SimpleNamespace(metadata=meta, spec=spec, status=SimpleNamespace(phase="Running", container_statuses=None))


# ---------------------------------------------------------------- pool sizing

def test_pool_size_requested_burst():
    mgr = _make_manager()
    mgr.get_used_pods_size = lambda: 10
    assert mgr.get_pool_size_requested() == 15  # max(5, 10+5) capped at 30


def test_pool_size_requested_respects_ceiling():
    mgr = _make_manager({"VIZ_POOL_BURST_SIZE": "12"})
    mgr.get_used_pods_size = lambda: 20
    assert mgr.get_pool_size_requested() == 12


# ----------------------------------------------------------------- affinity

def test_affinity_required_role_viz():
    mgr = _make_manager({"VIZ_POOL_TIER_AFFINITY": "primary"})
    dep = mgr._build_deployment("abc")
    aff = dep["spec"]["template"]["spec"]["affinity"]["nodeAffinity"]
    term = aff["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"][0]
    expr = term["matchExpressions"][0]
    assert expr == {"key": "role", "operator": "In", "values": ["viz"]}


def test_affinity_prefers_primary_tier():
    mgr = _make_manager({"VIZ_POOL_TIER_AFFINITY": "primary"})
    aff = mgr._build_deployment("abc")["spec"]["template"]["spec"]["affinity"]
    pref = aff["nodeAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"][0]
    assert pref["preference"]["matchExpressions"][0]["values"] == ["primary"]


def test_tier_affinity_flip_to_fallback():
    mgr = _make_manager({"VIZ_POOL_TIER_AFFINITY": "fallback"})
    aff = mgr._build_deployment("abc")["spec"]["template"]["spec"]["affinity"]
    pref = aff["nodeAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"][0]
    assert pref["preference"]["matchExpressions"][0]["values"] == ["fallback"]
    req = aff["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
    assert req["nodeSelectorTerms"][0]["matchExpressions"][0]["values"] == ["viz"]


def test_pod_affinity_present_for_packing():
    mgr = _make_manager({"VIZ_POOL_TIER_AFFINITY": "primary"})
    aff = mgr._build_deployment("abc")["spec"]["template"]["spec"]["affinity"]
    term = aff["podAffinity"]["preferredDuringSchedulingIgnoredDuringExecution"][0]
    assert term["podAffinityTerm"]["labelSelector"]["matchLabels"] == {"app": "viz-pool"}
    assert term["podAffinityTerm"]["topologyKey"] == "kubernetes.io/hostname"


# ------------------------------------------------------------ consolidation

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def _stub_list(mgr, available=0, terminating=0, all_pods=None):
    def list_pods(namespace, label_selector=None, **kw):
        if label_selector == "status=available":
            return SimpleNamespace(items=[_pod(f"a{i}", "available") for i in range(available)])
        if label_selector == "status=deleting":
            return SimpleNamespace(items=[_pod(f"d{i}", "deleting") for i in range(terminating)])
        if label_selector == "status=pending":
            return SimpleNamespace(items=[])
        if label_selector == "status=user-assigned":
            return SimpleNamespace(items=[])
        if label_selector and "status in" in label_selector:
            return SimpleNamespace(items=all_pods or [])
        return SimpleNamespace(items=all_pods or [])
    mgr.v1.list_namespaced_pod.side_effect = list_pods


def _stub_nodes(mgr, node_tiers):
    """Stub ``v1.list_node``. ``node_tiers``: {'n1': 'primary', 'n2': 'fallback', ...}."""
    items = [
        SimpleNamespace(metadata=SimpleNamespace(
            name=name, labels={"role": "viz", "pool-tier": tier}))
        for name, tier in node_tiers.items()
    ]
    mgr.v1.list_node.return_value = SimpleNamespace(items=items)


def test_consolidation_noop_when_single_node():
    mgr = _make_manager()
    mgr._delete_pod_resources = MagicMock()
    pods = [_pod("p1", "available", node="n1"), _pod("p2", "available", node="n1")]
    _stub_list(mgr, available=8, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    mgr._delete_pod_resources.assert_not_called()


def test_consolidation_noop_when_user_assigned_on_all_nodes():
    mgr = _make_manager()
    mgr._delete_pod_resources = MagicMock()
    pods = [
        _pod("u1", "user-assigned", node="n1"),
        _pod("p1", "available", node="n1"),
        _pod("u2", "user-assigned", node="n2"),
        _pod("p2", "available", node="n2"),
    ]
    _stub_list(mgr, available=8, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    mgr._delete_pod_resources.assert_not_called()


def test_consolidation_picks_emptiest_node():
    mgr = _make_manager()
    mgr._delete_pod_resources = MagicMock()
    pods = (
        [_pod(f"n1-{i}", "available", node="n1") for i in range(5)]
        + [_pod(f"n2-{i}", "available", node="n2") for i in range(3)]
        + [_pod("lonely", "available", node="n3")]
    )
    _stub_list(mgr, available=9, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    mgr._delete_pod_resources.assert_called_once_with("lonely")


def test_consolidation_respects_terminating_cap():
    mgr = _make_manager()
    mgr._delete_pod_resources = MagicMock()
    pods = [
        _pod("n1-0", "available", node="n1"),
        _pod("n1-1", "available", node="n1"),
        _pod("n2-0", "available", node="n2"),
    ]
    _stub_list(mgr, available=9, terminating=2, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    mgr._delete_pod_resources.assert_not_called()


def test_consolidation_respects_margin():
    mgr = _make_manager()  # burst_buffer=5, margin=2 → need >=7 available
    mgr._delete_pod_resources = MagicMock()
    pods = [
        _pod("n1-0", "available", node="n1"),
        _pod("n2-0", "available", node="n2"),
    ]
    _stub_list(mgr, available=5, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    mgr._delete_pod_resources.assert_not_called()


def test_consolidation_deletes_at_most_one_per_cycle():
    mgr = _make_manager()
    mgr._delete_pod_resources = MagicMock()
    pods = [
        _pod(f"n1-{i}", "available", node="n1") for i in range(4)
    ] + [
        _pod("a", "available", node="n2"),
        _pod("b", "available", node="n2"),
    ]
    _stub_list(mgr, available=9, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    assert mgr._delete_pod_resources.call_count == 1


# -------------------------------------------------- tier-priority consolidation

def test_consolidation_prefers_draining_fallback_tier():
    mgr = _make_manager({"VIZ_POOL_TIER_AFFINITY": "primary"})
    mgr._delete_pod_resources = MagicMock()
    pods = [
        _pod("p-0", "available", node="n1"),
        _pod("p-1", "available", node="n1"),
        _pod("f-0", "available", node="n2"),
        _pod("f-1", "available", node="n2"),
    ]
    _stub_nodes(mgr, {"n1": "primary", "n2": "fallback"})
    _stub_list(mgr, available=9, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    # Equal pod counts → tie broken by tier → fallback drained first.
    mgr._delete_pod_resources.assert_called_once()
    assert mgr._delete_pod_resources.call_args[0][0].startswith("f-")


def test_consolidation_drains_fallback_even_when_primary_is_emptier():
    mgr = _make_manager({"VIZ_POOL_TIER_AFFINITY": "primary"})
    mgr._delete_pod_resources = MagicMock()
    pods = (
        [_pod("p-0", "available", node="n1")]
        + [_pod(f"f-{i}", "available", node="n2") for i in range(5)]
    )
    _stub_nodes(mgr, {"n1": "primary", "n2": "fallback"})
    _stub_list(mgr, available=9, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    # Tier wins over emptiness: fallback node drained despite having 5× more pods.
    mgr._delete_pod_resources.assert_called_once()
    assert mgr._delete_pod_resources.call_args[0][0].startswith("f-")


def test_consolidation_within_tier_picks_emptiest():
    mgr = _make_manager({"VIZ_POOL_TIER_AFFINITY": "primary"})
    mgr._delete_pod_resources = MagicMock()
    pods = (
        [_pod(f"a-{i}", "available", node="n1") for i in range(5)]
        + [_pod(f"b-{i}", "available", node="n2") for i in range(3)]
        + [_pod("c-0", "available", node="n3")]
    )
    _stub_nodes(mgr, {"n1": "fallback", "n2": "fallback", "n3": "fallback"})
    _stub_list(mgr, available=9, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    # All three are fallback → tier ties → emptiest (n3 with 1 pod) wins.
    mgr._delete_pod_resources.assert_called_once_with("c-0")


def test_consolidation_falls_back_to_emptiness_when_preferred_tier_unset():
    mgr = _make_manager({"VIZ_POOL_TIER_AFFINITY": ""})
    mgr._delete_pod_resources = MagicMock()
    pods = (
        [_pod(f"a-{i}", "available", node="n1") for i in range(5)]
        + [_pod("lonely", "available", node="n2")]
    )
    _stub_nodes(mgr, {"n1": "primary", "n2": "fallback"})
    _stub_list(mgr, available=9, terminating=0, all_pods=pods)
    asyncio.run(mgr._consolidate_nodes())
    # No preferred tier → every node ties on tier → pure emptiness wins.
    mgr._delete_pod_resources.assert_called_once_with("lonely")


# ------------------------------------------------------- terminating cap in excess cleanup

def test_terminating_cap_blocks_excess_cleanup():
    mgr = _make_manager({"VIZ_POOL_MAX_TERMINATING": "2"})
    mgr._delete_pod_resources = MagicMock()
    # 10 available, need only 5 → 5 excess; but 2 already terminating → 0 more
    mgr.get_pool_size_requested = lambda: 5
    mgr.get_pending_pods_size = lambda: 0
    mgr.get_available_pods_size = lambda: 10

    pending_pods = SimpleNamespace(items=[])
    available_pods = SimpleNamespace(items=[_pod(f"p{i}", "available") for i in range(10)])
    used_pods = SimpleNamespace(items=[])
    deleting_pods = SimpleNamespace(items=[_pod("d1", "deleting"), _pod("d2", "deleting")])

    def list_pods(namespace, label_selector=None, **kw):
        if label_selector == "status=user-assigned":
            return used_pods
        if label_selector == "status=pending":
            return pending_pods
        if label_selector == "status=available":
            return available_pods
        if label_selector == "status=deleting":
            return deleting_pods
        return SimpleNamespace(items=[])

    mgr.v1.list_namespaced_pod.side_effect = list_pods
    asyncio.run(mgr._cleanup_excess_pods())
    mgr._delete_pod_resources.assert_not_called()


def test_count_terminating_reads_deleting_label():
    mgr = _make_manager()
    mgr.v1.list_namespaced_pod.return_value = SimpleNamespace(
        items=[_pod("d1", "deleting"), _pod("d2", "deleting"), _pod("d3", "deleting")]
    )
    assert mgr._count_terminating() == 3
