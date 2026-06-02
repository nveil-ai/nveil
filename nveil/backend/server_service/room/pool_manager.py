# SPDX-FileCopyrightText: 2025 NVEIL SAS
# SPDX-FileContributor: Guillaume Franque
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import os
from utils import get_secret
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from logger import DEBUG, ERROR, INFO, SUCCESS, WARNING, logger
from . import viz_pool_config as cfg


@dataclass
class PooledPod:
    """Pod pré-provisionné disponible dans le pool."""
    name: str
    service_dns: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __str__(self):
        return (f"name: {self.name[:8]}, created at: {self.created_at}")


class VizPoolManager:
    """Warm pool of viz pods pre-provisioned on GKE, pod-per-user.

    Pod states (tracked via the ``status`` label):
        ``pending``        — Deployment created, container not yet ready.
        ``available``      — Ready, idle, waiting to be claimed.
        ``user-assigned``  — Claimed by a user (may or may not have an active room).
        ``used``           — Legacy alias of ``user-assigned`` still accepted.
        ``deleting``       — Marked for deletion; Deployment/Service teardown in flight.

    Node-pool tiering:
        Pods use node-affinity (``role=viz`` required) plus a soft preference on
        ``pool-tier``. The primary pool (``c3d-standard-4``) is preferred; when it
        cannot schedule, kube-scheduler silently falls back to ``pool-tier=fallback``
        (``t2d-standard-4``). The fallback pool autoscales from 0, so it costs
        nothing at rest.

    Bin-packing / consolidation:
        A soft ``podAffinity`` on ``app=viz-pool`` pulls new pods toward nodes that
        already host viz pods. Every maintenance cycle (60s) the leader additionally
        retires at most ONE ``available`` pod off the least-loaded node that hosts
        no user pods, letting cluster-autoscaler reclaim empty nodes.

    Safety invariants:
        * ``terminating_count`` is capped at ``VIZ_POOL_MAX_TERMINATING`` across
          every delete path — excess cleanup, stale-version draining, and
          consolidation. This prevents the "N pods Terminating at once starve
          acquisition" failure mode.
        * Consolidation only acts when ``available >= burst_buffer + margin``,
          so acquisition never races a retirement.
        * At most one pod is retired per maintenance cycle.

    Key env vars:
        ``VIZ_POOL_MIN_SIZE``              minimum warm pods (default 5)
        ``VIZ_POOL_BURST_BUFFER``          extras kept above current demand (5)
        ``VIZ_POOL_BURST_SIZE``            absolute ceiling during bursts (30)
        ``VIZ_POOL_TIER_AFFINITY``         preferred node pool-tier ("primary" / "fallback" / "")
        ``VIZ_POOL_CONSOLIDATION_MARGIN``  slack above burst_buffer before consolidating (2)
        ``VIZ_POOL_MAX_TERMINATING``       cap on concurrent deletions (2)
        ``VIZ_IDLE_TIMEOUT_MINUTES``       room idle timeout (15)
        ``VIZ_USER_IDLE_TIMEOUT_MINUTES``  user idle timeout (30)
    """

    def __init__(self, namespace: str = "viz-service"):
        self.namespace = namespace
        self._running = False

        # Long-lived pool for intra-cluster viz-pod calls.
        # Created in start() (requires a running event loop), closed in stop().
        self._http: Optional[httpx.AsyncClient] = None

        # Init K8s client
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

        self.viz_image = cfg.get("VIZ_IMAGE")
        self.server_host = cfg.get("SERVER_INTERNAL_HOST", "server-service-lb.server.svc.cluster.local")
        self.gcp = cfg.get("GCP", "0")
        self.room_idle_timeout = cfg.get_int("VIZ_IDLE_TIMEOUT_MINUTES", 15)
        self.user_idle_timeout = cfg.get_int("VIZ_USER_IDLE_TIMEOUT_MINUTES", 30)

        # Callbacks — set by room.py at startup
        self._on_room_idle_callback = None   # async def(room_id: str)
        self._on_user_idle_callback = None   # async def(owner_id: str)
        self._on_queue_wait_callback = None  # async def(room_id: str, owner_id: str)

        # Leader state — updated by maintenance loop, read by scale-out loop
        self._is_leader = False

        # Node scheduling — configurable for local K8s vs GKE
        self.node_selector_role = cfg.get("VIZ_NODE_SELECTOR_ROLE", "viz")
        self.preferred_tier = cfg.get("VIZ_POOL_TIER_AFFINITY", "")
        self.tolerations = cfg.get_tolerations()

        # Storage — PVC for GKE, hostPath for local
        self.volume_type = cfg.get("VIZ_VOLUME_TYPE")
        self.volume_host_path = cfg.get("VIZ_VOLUME_HOST_PATH")

        # Bin-packing / consolidation tunables
        self.consolidation_margin = cfg.get_int("VIZ_POOL_CONSOLIDATION_MARGIN", 2)
        self.max_terminating = cfg.get_int("VIZ_POOL_MAX_TERMINATING", 2)

        # In-memory routing table: populated by acquire(), cleared by release()
        # Avoids DB lookups on every proxied HTTP request (static assets, etc.)
        self._room_token_to_dns: dict[str, str] = {}  # room_token → pod_dns
        self._room_id_to_token: dict[str, str] = {}   # room_id → room_token
        self._room_token_to_info: dict[str, dict] = {}  # room_token → {dns, room_id, owner_id}



    def get_pod_dns_for_token(self, room_token: str) -> Optional[str]:
        """Return the pod DNS for a room token, or None if not assigned."""
        return self._room_token_to_dns.get(str(room_token))

    def get_room_info_for_token(self, room_token: str) -> Optional[dict]:
        """Return full routing info {dns, room_id, owner_id} for a room token."""
        return self._room_token_to_info.get(str(room_token))

    def get_room_info_for_room_id(self, room_id: str) -> Optional[dict]:
        """Return full routing info {dns, room_id, owner_id} for a room_id."""
        token = self._room_id_to_token.get(str(room_id))
        if token:
            return self._room_token_to_info.get(token)
        return None

    def print_k8s_info(self):
        logger().logp(INFO, f"number of pods: {self.get_pool_size()}", "; pending: ", self.get_pending_pods_size(), "; available: ", self.get_available_pods_size(), "; used: ", self.get_used_pods_size())

    def get_pool_size(self) -> int:
        try:
            api_response = self.v1.list_namespaced_pod(self.namespace)
            return len(api_response.items)
        except ApiException as e:
            logger().error("Exception when calling CoreV1Api->list_namespaced_pod:", e)
            return 0

    def get_available_pods_size(self) -> int:
        try:
            api_response = self.v1.list_namespaced_pod(self.namespace, label_selector='status=available')
            return len(api_response.items)
        except ApiException as e:
            logger().error("Exception when calling CoreV1Api->list_namespaced_pod:", e)
            return 0

    def get_pending_pods_size(self) -> int:
        try:
            api_response = self.v1.list_namespaced_pod(self.namespace, label_selector='status=pending')
            return len(api_response.items)
        except ApiException as e:
            logger().error("Exception when calling CoreV1Api->list_namespaced_pod:", e)
            return 0

    def get_used_pods_size(self) -> int:
        try:
            api_response = self.v1.list_namespaced_pod(self.namespace, label_selector='status=user-assigned')
            return len(api_response.items)
        except ApiException as e:
            logger().error("Exception when calling CoreV1Api->list_namespaced_pod:", e)
            return 0

    def get_pool_size_requested(self) -> int:
        min_size = cfg.get_int("VIZ_POOL_MIN_SIZE", 5)
        burst_size = cfg.get_int("VIZ_POOL_BURST_SIZE", 30)
        burst_buffer = cfg.get_int("VIZ_POOL_BURST_BUFFER", 5)
        used = self.get_used_pods_size()
        # Additive: always keep burst_buffer pods ready above current demand
        needed = max(min_size, used + burst_buffer)
        # Burst ceiling: allow exceeding max_size during spikes, up to burst_size
        return min(needed, burst_size)

    # ------------------------------------------------------------------
    # Lifecycle: start / stop with cancellable task
    # ------------------------------------------------------------------

    def start(self):
        """Start the pool manager: fast scale-out loop (5s) + slow maintenance loop (60s)."""
        self._running = True
        self._is_leader = False
        # Share one HTTP/2-capable async client across all pod calls; keeps TLS
        # sessions warm to viz-pool-*.viz-service.svc.cluster.local pods.
        self._http = httpx.AsyncClient(
            verify=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self._scale_out_task = asyncio.create_task(self._scale_out_loop())
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        logger().logp(INFO, f"🏊 VizPoolManager started (target={self.get_pool_size_requested()})")

    def stop(self):
        """Stop both loops immediately."""
        self._running = False
        self._is_leader = False
        for attr in ('_scale_out_task', '_maintenance_task'):
            task = getattr(self, attr, None)
            if task:
                task.cancel()
                setattr(self, attr, None)
        if self._http is not None:
            try:
                asyncio.create_task(self._http.aclose())
            except RuntimeError:
                pass
            self._http = None
        self._release_lease()
        logger().logp(INFO, "🏊 VizPoolManager stopped")

    # ------------------------------------------------------------------
    # K8s Lease-based leader election
    # ------------------------------------------------------------------

    _LEASE_NAME = "viz-pool-leader"
    _LEASE_DURATION_SEC = 40  # must be > reconcile interval (30s)

    def _get_holder_identity(self) -> str:
        return os.environ.get("HOSTNAME", "unknown")

    def _try_acquire_lease(self) -> bool:
        """Try to acquire or renew the leader lease. Returns True if we are leader."""
        coord = client.CoordinationV1Api()
        now = datetime.now(timezone.utc)
        identity = self._get_holder_identity()

        try:
            lease = coord.read_namespaced_lease(self._LEASE_NAME, self.namespace)
            holder = lease.spec.holder_identity
            renew_time = lease.spec.renew_time

            # Check if lease is held by us
            if holder == identity:
                lease.spec.renew_time = now
                coord.replace_namespaced_lease(self._LEASE_NAME, self.namespace, lease)
                return True

            # Check if lease is expired (holder crashed or old pod still draining)
            if renew_time:
                elapsed = (now - renew_time).total_seconds()
                if elapsed > self._LEASE_DURATION_SEC:
                    logger().logp(INFO, f"🏊 Lease expired (held by {holder}, {elapsed:.0f}s ago), taking over")
                    lease.spec.holder_identity = identity
                    lease.spec.renew_time = now
                    lease.spec.acquire_time = now
                    coord.replace_namespaced_lease(self._LEASE_NAME, self.namespace, lease)
                    return True

            return False

        except ApiException as e:
            if e.status == 404:
                # Lease doesn't exist yet — create it
                lease = client.V1Lease(
                    metadata=client.V1ObjectMeta(name=self._LEASE_NAME, namespace=self.namespace),
                    spec=client.V1LeaseSpec(
                        holder_identity=identity,
                        lease_duration_seconds=self._LEASE_DURATION_SEC,
                        acquire_time=now,
                        renew_time=now,
                    ),
                )
                try:
                    coord.create_namespaced_lease(self.namespace, lease)
                    logger().logp(INFO, f"🏊 Created leader lease (holder={identity})")
                    return True
                except ApiException:
                    return False  # race: another pod created it first
            logger().logp(ERROR, f"Lease error: {e}")
            return False

    def _release_lease(self):
        """Release the leader lease on shutdown so the next pod takes over immediately."""
        coord = client.CoordinationV1Api()
        identity = self._get_holder_identity()
        try:
            lease = coord.read_namespaced_lease(self._LEASE_NAME, self.namespace)
            if lease.spec.holder_identity == identity:
                # Set renew_time far in the past so the next pod sees it as expired
                lease.spec.renew_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
                coord.replace_namespaced_lease(self._LEASE_NAME, self.namespace, lease)
                logger().logp(INFO, "🏊 Leader lease released")
        except ApiException as e:
            logger().logp(WARNING, f"Could not release lease: {e}")

    # ------------------------------------------------------------------
    # Reconciliation loop
    # ------------------------------------------------------------------

    async def _scale_out_loop(self):
        """Fast loop (5s): fill the pool whenever available pods fall below target.

        Only runs when we hold the leader lease (updated by _maintenance_loop).
        This makes pool replenishment near-instant instead of waiting up to 30s.
        """
        while self._running:
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            if self._is_leader:
                await self._fill_pool()

    async def _maintenance_loop(self):
        """Slow loop (60s): leader election + cleanup + idle + excess trimming."""
        # Wait for leader lease before touching viz pods
        while self._running:
            if self._try_acquire_lease():
                self._is_leader = True
                logger().logp(INFO, "🏊 Acquired leader lease, starting pool maintenance")
                break
            logger().logp(INFO, "🏊 Waiting for leader lease (another server pod is active)...")
            await asyncio.sleep(5)

        if not self._running:
            return

        # On fresh leader acquisition in cloud mode, nuke all stale-version pool
        # resources immediately — the old server is down so no active sessions exist.
        await self._startup_version_flush()
        await self._fill_pool()

        while self._running:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            if not self._try_acquire_lease():
                self._is_leader = False
                logger().logp(WARNING, "🏊 Lost leader lease, pausing maintenance")
                continue
            self._is_leader = True
            self.print_k8s_info()
            await self._cleanup_dead_pods()
            await self._check_pod_idle()
            await self._cleanup_stale_version_pods()
            await self._cleanup_excess_pods()
            await self._consolidate_nodes()
            await self._fill_pool()

        self._is_leader = False
        self._release_lease()

    async def _fill_pool(self):
        """Crée des pods jusqu'à atteindre pool_size."""
        current_ready_or_pending = self.get_available_pods_size() + self.get_pending_pods_size()
        needed = self.get_pool_size_requested() - current_ready_or_pending

        for i in range(needed):
            pod = await self._create_pooled_pod()
            if pod:
                logger().logp(SUCCESS, f"✅ Pool pod ready: {pod.name}")

    async def _cleanup_dead_pods(self):
        """Supprime les pods du pool qui ne sont plus en Running phase."""
        try:
            # On liste tous les pods qui sont censés être dans le pool (available ou pending)
            api_response = self.v1.list_namespaced_pod(
                self.namespace,
                label_selector='status in (available, pending)'
            )
            for pod in api_response.items:
                pool_id = pod.metadata.labels.get("pool-id")
                if not pool_id:
                    continue
                
                # Si le pod est Failed, Succeeded ou Unknown, on nettoie
                if pod.status.phase in ["Failed", "Succeeded", "Unknown"]:
                    logger().logp(WARNING, f"🗑️ Cleaning up dead pod {pod.metadata.name} (phase={pod.status.phase})")
                    self._delete_pod_resources(pool_id)
                
                # Optionnel: On peut aussi vérifier si les containers ont crashé à répétition
                if pod.status.container_statuses:
                    for status in pod.status.container_statuses:
                        if status.restart_count > 5:
                            logger().logp(ERROR, f"❌ Pod {pod.metadata.name} is crashing (restarts={status.restart_count}), deleting.")
                            self._delete_pod_resources(pool_id)
                            break
        except Exception as e:
            logger().logp(ERROR, f"Error during _cleanup_dead_pods: {e}")

    async def _check_pod_idle(self):
        """Poll user-assigned pods via /viz/status and handle idle timeouts.

        Tier 1: Room idle → release room context, keep pod alive.
        Tier 2: No room for too long → kill pod entirely.
        """
        room_idle_secs = self.room_idle_timeout * 60
        user_idle_secs = self.user_idle_timeout * 60

        try:
            api_response = self.v1.list_namespaced_pod(
                self.namespace,
                label_selector='status in (used, user-assigned)'
            )
            for pod in api_response.items:
                pool_id = pod.metadata.labels.get("pool-id")
                if not pool_id:
                    continue

                pod_name = pod.metadata.name
                pod_dns = f"viz-pool-{pool_id}.{self.namespace}.svc.cluster.local"
                annotations = pod.metadata.annotations or {}

                try:
                    resp = await self._http.get(f"https://{pod_dns}:1024/viz/status", timeout=5.0)
                    data = resp.json()
                    pod_room_id = data.get("room_id")
                    pod_owner_id = data.get("owner_id")
                    idle = data.get("idle_seconds", 0)

                    # Tier 1: Room idle → release room context, keep pod
                    if pod_room_id and idle > room_idle_secs:
                        logger().logp(INFO,
                            f"Room idle timeout ({self.room_idle_timeout}min) on pod {pod_name}")
                        try:
                            await self._http.post(f"https://{pod_dns}:1024/viz/release_room", timeout=10.0)
                        except Exception as e:
                            logger().logp(WARNING, f"Failed to release room from pod {pod_name}: {e}")
                        # Update K8s labels
                        try:
                            body = {"metadata": {"labels": {"room-id": ""}}}
                            self.v1.patch_namespaced_pod(name=pod_name, namespace=self.namespace, body=body)
                        except Exception:
                            pass
                        if self._on_room_idle_callback:
                            try:
                                await self._on_room_idle_callback(pod_room_id)
                            except Exception as e:
                                logger().logp(WARNING, f"Room idle callback failed: {e}")

                    # Tier 2: No room for too long → kill pod
                    elif not pod_room_id:
                        idle_since_str = annotations.get("nveil/idle-since")
                        if idle_since_str:
                            try:
                                idle_since = datetime.fromisoformat(idle_since_str)
                                idle_duration = (datetime.utcnow() - idle_since).total_seconds()
                                if idle_duration > user_idle_secs:
                                    logger().logp(INFO,
                                        f"User idle timeout ({self.user_idle_timeout}min) on pod {pod_name}")
                                    if self._on_user_idle_callback and pod_owner_id:
                                        try:
                                            await self._on_user_idle_callback(pod_owner_id)
                                        except Exception as e:
                                            logger().logp(WARNING, f"User idle callback failed: {e}")
                                    self._delete_pod_resources(pool_id)
                            except (ValueError, TypeError):
                                pass
                        else:
                            # First time seeing no room — mark idle-since
                            try:
                                body = {"metadata": {"annotations": {"nveil/idle-since": datetime.utcnow().isoformat()}}}
                                self.v1.patch_namespaced_pod(name=pod_name, namespace=self.namespace, body=body)
                            except Exception:
                                pass

                    # Pod has a room and is active — clear idle-since if set
                    elif pod_room_id and annotations.get("nveil/idle-since"):
                        try:
                            body = {"metadata": {"annotations": {"nveil/idle-since": None}}}
                            self.v1.patch_namespaced_pod(name=pod_name, namespace=self.namespace, body=body)
                        except Exception:
                            pass

                except Exception as e:
                    # Pod unreachable — check if it's been unreachable too long
                    annotations = pod.metadata.annotations or {}
                    if not annotations.get("nveil/acquired-at"):
                        logger().logp(WARNING, f"Unreachable orphan pod {pod_name}, deleting")
                        self._delete_pod_resources(pool_id)

        except Exception as e:
            logger().logp(ERROR, f"Error during _check_pod_idle: {e}")

    async def _cleanup_excess_pods(self):
        """Supprime les pods excédentaires (pending d'abord, puis available)."""
        needed = self.get_pool_size_requested()
        pending_count = self.get_pending_pods_size()
        available_count = self.get_available_pods_size()
        total_ready_or_pending = pending_count + available_count
        
        excess = total_ready_or_pending - needed
        if excess <= 0:
            return
        
        logger().logp(INFO, f"🧹 Cleaning up {excess} excess pods (needed={needed}, pending={pending_count}, available={available_count})")
        
        deleted = 0
        
        # Get the set of pool-ids that are currently in use (status=user-assigned)
        used_pool_ids = set()
        try:
            used_pods = self.v1.list_namespaced_pod(
                self.namespace,
                label_selector='status=user-assigned'
            )
            for pod in used_pods.items:
                pool_id = pod.metadata.labels.get("pool-id", "")
                if pool_id:
                    used_pool_ids.add(pool_id)
        except ApiException as e:
            logger().logp(ERROR, f"Error listing used pods: {e}")
            return  # Don't proceed if we can't verify used pods
        
        logger().logp(DEBUG, f"🔒 Protected pool-ids (in use): {used_pool_ids}")
        
        # D'abord supprimer les pods pending
        if deleted < excess:
            try:
                pending_pods = self.v1.list_namespaced_pod(
                    self.namespace, 
                    label_selector='status=pending'
                )
                for pod in pending_pods.items:
                    if deleted >= excess:
                        break
                    if not self._can_delete_more():
                        return
                    pool_id = pod.metadata.labels.get("pool-id", "")
                    # Skip if this pool-id has any used pods
                    if pool_id and pool_id not in used_pool_ids:
                        logger().logp(INFO, f"🗑️ Deleting excess pending pod: {pool_id}")
                        self._delete_pod_resources(pool_id)
                        deleted += 1
                    elif pool_id in used_pool_ids:
                        logger().logp(WARNING, f"⚠️ Skipping {pool_id} - has used pods")
            except ApiException as e:
                logger().logp(ERROR, f"Error listing pending pods: {e}")
        
        # Ensuite supprimer les pods available si nécessaire
        if deleted < excess:
            try:
                available_pods = self.v1.list_namespaced_pod(
                    self.namespace, 
                    label_selector='status=available'
                )
                for pod in available_pods.items:
                    if deleted >= excess:
                        break
                    if not self._can_delete_more():
                        return
                    pool_id = pod.metadata.labels.get("pool-id", "")
                    # Skip if this pool-id has any used pods
                    if pool_id and pool_id not in used_pool_ids:
                        logger().logp(INFO, f"🗑️ Deleting excess available pod: {pool_id}")
                        self._delete_pod_resources(pool_id)
                        deleted += 1
                    elif pool_id in used_pool_ids:
                        logger().logp(WARNING, f"⚠️ Skipping {pool_id} - has used pods")
            except ApiException as e:
                logger().logp(ERROR, f"Error listing available pods: {e}")
        
        logger().logp(SUCCESS, f"✅ Cleaned up {deleted} excess pods")

    async def _startup_version_flush(self):
        """Cloud-only: on leader acquisition, immediately bulk-delete all viz-pool
        resources that are running a stale image.

        Bypasses the terminating cap and graceful drain because the old server is
        already down — there are no live user sessions to protect.
        """
        if self.gcp != "1":
            return

        try:
            deployments = self.apps_v1.list_namespaced_deployment(
                self.namespace, label_selector="app=viz-pool"
            )
        except ApiException as e:
            logger().logp(WARNING, f"🏊 startup flush: could not list deployments: {e}")
            return

        stale = [
            d for d in deployments.items
            if (d.spec.template.metadata.annotations or {}).get("nveil/image", "") != self.viz_image
        ]

        if not stale:
            logger().logp(INFO, "🏊 startup flush: all pool pods are current version, skipping")
            return

        logger().logp(WARNING,
            f"🏊 startup flush: bulk-deleting {len(stale)} stale-version deployments (fast path, no cap)")

        delete_opts = client.V1DeleteOptions(propagation_policy="Background", grace_period_seconds=0)
        deleted = 0
        for d in stale:
            name = d.metadata.name
            pool_id = (d.metadata.labels or {}).get("pool-id", "")
            try:
                self.apps_v1.delete_namespaced_deployment(
                    name=name, namespace=self.namespace, body=delete_opts
                )
                deleted += 1
            except ApiException as e:
                if e.status != 404:
                    logger().logp(WARNING, f"⚠️ startup flush: failed to delete deployment {name}: {e}")
            if pool_id:
                try:
                    self.v1.delete_namespaced_service(
                        name=f"viz-pool-{pool_id}", namespace=self.namespace,
                        body=client.V1DeleteOptions(grace_period_seconds=0)
                    )
                except ApiException as e:
                    if e.status != 404:
                        logger().logp(WARNING, f"⚠️ startup flush: failed to delete service viz-pool-{pool_id}: {e}")

        logger().logp(SUCCESS,
            f"✅ startup flush: {deleted}/{len(stale)} stale deployments deleted, new pool filling now")

    async def _cleanup_stale_version_pods(self):
        """Delete pods running an old image version.

        Available/pending pods are deleted immediately.
        User-assigned pods are drained first: release their room context
        so the user gets reassigned to a new-version pod on next action.
        """
        try:
            api_response = self.v1.list_namespaced_pod(
                self.namespace,
                label_selector='status in (available, pending, used, user-assigned)'
            )
            for pod in api_response.items:
                pool_id = pod.metadata.labels.get("pool-id")
                if not pool_id:
                    continue
                annotations = pod.metadata.annotations or {}
                pod_image = annotations.get("nveil/image", "")
                if pod_image == self.viz_image or not pod_image:
                    continue

                pod_name = pod.metadata.name
                pod_status = pod.metadata.labels.get("status", "")

                if pod_status in ("used", "user-assigned"):
                    # Drain: release room context before deleting
                    pod_dns = f"viz-pool-{pool_id}.{self.namespace}.svc.cluster.local"
                    try:
                        await self._http.post(f"https://{pod_dns}:1024/viz/release_room", timeout=5.0)
                    except Exception:
                        pass  # Pod may already be unhealthy — delete anyway
                    logger().logp(WARNING,
                        f"🔄 Draining stale-version USED pod {pod_name} "
                        f"(has={pod_image}, want={self.viz_image})")
                    self._delete_pod_resources(pool_id)
                else:
                    # Non-user pod: respect terminating cap to avoid starving
                    # acquisition during a rollout wave.
                    if not self._can_delete_more():
                        return
                    logger().logp(WARNING,
                        f"🔄 Draining stale-version pod {pod_name} "
                        f"(has={pod_image}, want={self.viz_image})")
                    self._delete_pod_resources(pool_id)
        except Exception as e:
            logger().logp(ERROR, f"Error during _cleanup_stale_version_pods: {e}")

    async def _create_pooled_pod(self) -> Optional[PooledPod]:
        """Crée un pod en mode pool."""
        import uuid
        pool_id = f"pool-{uuid.uuid4().hex[:8]}"

        deployment = self._build_deployment(pool_id)
        service = self._build_service(pool_id)

        try:
            self.v1.create_namespaced_service(namespace=self.namespace, body=service)
            self.apps_v1.create_namespaced_deployment(namespace=self.namespace, body=deployment)

            logger().logp(INFO, f"🚀 Pool pod deployment created: {pool_id} (status=pending)")
            return PooledPod(
                name=pool_id,
                service_dns=f"viz-pool-{pool_id}.{self.namespace}.svc.cluster.local"
            )
        except Exception as e:
            logger().logp(ERROR, f"❌ Failed to create pool pod: {e}")
            self._delete_pod_resources(pool_id)
            return None

    def mark_pod_available(self, pool_id: str) -> bool:
        """Marque un pod comme available après qu'il ait notifié le serveur."""
        try:
            # Trouver le pod avec ce pool-id
            pods = self.v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"pool-id={pool_id}"
            )
            if not pods.items:
                logger().logp(WARNING, f"⚠️ No pod found with pool-id={pool_id}")
                return False
            
            pod_name = pods.items[0].metadata.name
            
            # Patcher le pod pour le marquer comme available
            body = {
                "metadata": {
                    "labels": {
                        "status": "available"
                    }
                }
            }
            self.v1.patch_namespaced_pod(
                name=pod_name,
                namespace=self.namespace,
                body=body
            )
            logger().logp(SUCCESS, f"✅ Pod {pod_name} marked as available")
            return True
        except Exception as e:
            logger().logp(ERROR, f"❌ Failed to mark pod available: {e}")
            return False

    def _build_affinity(self) -> Optional[dict]:
        """Return the pod affinity block, or None when scheduling is unconstrained.

        The hard constraint is the node role; the soft preferences steer
        scheduling toward the preferred tier and toward nodes that already
        host viz pods (so the pool packs instead of spreading).
        """
        if not self.node_selector_role:
            return None

        node_affinity = {
            "requiredDuringSchedulingIgnoredDuringExecution": {
                "nodeSelectorTerms": [{
                    "matchExpressions": [
                        {"key": "role", "operator": "In", "values": [self.node_selector_role]},
                    ]
                }]
            },
        }
        if self.preferred_tier:
            node_affinity["preferredDuringSchedulingIgnoredDuringExecution"] = [{
                "weight": 100,
                "preference": {"matchExpressions": [
                    {"key": "pool-tier", "operator": "In", "values": [self.preferred_tier]},
                ]},
            }]

        return {
            "nodeAffinity": node_affinity,
            "podAffinity": {
                "preferredDuringSchedulingIgnoredDuringExecution": [{
                    "weight": 50,
                    "podAffinityTerm": {
                        "labelSelector": {"matchLabels": {"app": "viz-pool"}},
                        "topologyKey": "kubernetes.io/hostname",
                    },
                }]
            },
        }

    # ------------------------------------------------------------------
    # Terminating cap + consolidation
    # ------------------------------------------------------------------

    def _count_terminating(self) -> int:
        """Number of pool pods currently in the ``deleting`` state."""
        try:
            resp = self.v1.list_namespaced_pod(self.namespace, label_selector="status=deleting")
            return len(resp.items)
        except ApiException as e:
            logger().logp(WARNING, f"_count_terminating failed: {e}")
            return 0

    def _can_delete_more(self) -> bool:
        """Guard called before every delete path; prevents starving acquisition."""
        current = self._count_terminating()
        if current >= self.max_terminating:
            logger().logp(INFO,
                f"🏊 Terminating cap reached ({current}/{self.max_terminating}), deferring delete")
            return False
        return True

    async def _consolidate_nodes(self):
        """Retire one ``available`` pod off a viz node, biased toward the non-preferred tier.

        Lets cluster-autoscaler reclaim empty nodes without ever create/delete
        churning: the replacement is spawned by the next ``_fill_pool`` tick
        and biased toward the preferred tier (and fuller nodes) by the soft
        node- and podAffinity. All safety guards are documented on the class
        docstring.

        Draining priority:
            1. Non-preferred tier first (e.g. ``fallback``), so the warm pool
               migrates onto the cheaper/preferred ``primary`` tier when demand
               drops. Without this, a burst that spilled into ``fallback`` would
               remain stuck there indefinitely.
            2. Within a tier, emptiest node first — fewest pods to drain before
               cluster-autoscaler can reclaim the node.
        """
        burst_buffer = cfg.get_int("VIZ_POOL_BURST_BUFFER", 5)
        available_count = self.get_available_pods_size()
        if available_count < burst_buffer + self.consolidation_margin:
            return  # insufficient slack — preserve acquisition latency
        if self._count_terminating() > 0:
            return  # a prior delete is still in flight; avoid stacking
        if not self._can_delete_more():
            return

        try:
            all_pods = self.v1.list_namespaced_pod(
                self.namespace,
                label_selector="status in (available, pending, user-assigned, used)",
            ).items
        except ApiException as e:
            logger().logp(WARNING, f"_consolidate_nodes list failed: {e}")
            return

        # Fetch viz-node labels once so we can weight drain priority by pool-tier.
        node_tier: dict = {}
        if self.node_selector_role:
            try:
                node_items = self.v1.list_node(
                    label_selector=f"role={self.node_selector_role}"
                ).items
                node_tier = {
                    n.metadata.name: (n.metadata.labels or {}).get("pool-tier", "")
                    for n in node_items
                }
            except ApiException as e:
                logger().logp(WARNING, f"_consolidate_nodes list_node failed: {e}")

        nodes_with_users: set = set()
        nodes_pods: dict = {}
        for pod in all_pods:
            node = getattr(pod.spec, "node_name", None)
            if not node:
                continue
            status = (pod.metadata.labels or {}).get("status", "")
            if status in ("user-assigned", "used"):
                nodes_with_users.add(node)
            nodes_pods.setdefault(node, []).append(pod)

        candidate_nodes = [n for n in nodes_pods if n not in nodes_with_users]
        if len(candidate_nodes) < 2:
            return  # nothing to drain onto another node

        def _drain_priority(node: str) -> tuple:
            # Lower wins. Non-preferred tier drains first; within a tier, emptiest first.
            tier = node_tier.get(node, "")
            is_preferred = 1 if self.preferred_tier and tier == self.preferred_tier else 0
            return (is_preferred, len(nodes_pods[node]))

        candidate_nodes.sort(key=_drain_priority)
        target_node = candidate_nodes[0]

        # Retire exactly one available pod from that node.
        for pod in nodes_pods[target_node]:
            if (pod.metadata.labels or {}).get("status") != "available":
                continue
            pool_id = (pod.metadata.labels or {}).get("pool-id")
            if not pool_id:
                continue
            logger().logp(INFO,
                f"🏊 Consolidating: retiring {pool_id} on node {target_node} "
                f"(tier={node_tier.get(target_node, '?')}, "
                f"candidates={len(candidate_nodes)}, available={available_count})")
            self._delete_pod_resources(pool_id)
            return  # at most ONE retirement per cycle

    def _build_deployment(self, pool_id: str) -> dict:
        spec = {
            "serviceAccountName": "viz-workload",
            "priorityClassName": "viz-priority",
            "containers": [{
                "name": "viz",
                "image": self.viz_image,
                "imagePullPolicy": "IfNotPresent",
                "env": [
                    {"name": "SERVER_HOST", "value": self.server_host},
                    {"name": "POOL_MODE", "value": "1"},
                    {"name": "GCP", "value": self.gcp},
                    {"name": "TEST", "value": "0"},
                    {"name": "SSL_CERT_FILE", "value": "/etc/ssl/certs/ca-certificates.crt"},
                    {"name": "REQUESTS_CA_BUNDLE", "value": "/etc/ssl/certs/ca-certificates.crt"},
                    {"name": "SSL_KEYFILE", "value": "/certs/ma_cle_privee.key"},
                    {"name": "SSL_CERTFILE", "value": "/certs/mon_certificat.crt"},
                    {"name": "POD_IP", "valueFrom": {
                        "fieldRef": {"fieldPath": "status.podIP"}
                    }},
                    {"name": "POOL_ID", "value": pool_id},
                    {"name": "GOOGLE_API_KEY", "value": get_secret("GOOGLE_API_KEY", "")},
                ],
                "ports": [
                    {"containerPort": 1024, "name": "cmd"},
                    {"containerPort": 1025, "name": "viz"},
                    {"containerPort": 4141, "name": "kedro"},
                ],
                "resources": {
                    "requests": {"cpu": "250m", "memory": "1Gi", "ephemeral-storage": "1Gi"},
                    "limits": {"cpu": "4000m", "memory": "8Gi", "ephemeral-storage": "4Gi"},
                },
                "volumeMounts": [
                    {"name": "filestore", "mountPath": "/root/DIVE"},
                    {"name": "tls-certs", "mountPath": "/certs", "readOnly": True},
                ],
                "readinessProbe": {
                    "httpGet": {"path": "/viz/health", "port": 1024, "scheme": "HTTPS"},
                    "initialDelaySeconds": 10,
                    "periodSeconds": 5,
                }
            }],
            "volumes": [
                {
                    "name": "filestore",
                    **({"persistentVolumeClaim": {"claimName": "filestore-pvc"}} if self.volume_type == "pvc" else
                       {"hostPath": {"path": self.volume_host_path, "type": "DirectoryOrCreate"}})
                },
                {
                    "name": "tls-certs",
                    "secret": {"secretName": "nveil-internal-tls"}
                },
            ]
        }

        # Affinity + tolerations (replaces the old hard nodeSelector).
        #   * required: node must carry role=<role> (usually "viz").
        #   * preferred: node should be on the configured pool-tier (primary in
        #     normal operation; fallback only when kube-scheduler can't satisfy
        #     the preference on the primary pool).
        #   * podAffinity soft-prefers nodes already hosting viz-pool pods so
        #     that new pods pack into fuller nodes, not spread across empty ones.
        affinity = self._build_affinity()
        if affinity:
            spec["affinity"] = affinity
        if self.tolerations:
            spec["tolerations"] = self.tolerations

        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": f"viz-pool-{pool_id}",
                "namespace": self.namespace,
                "labels": {"app": "viz-pool", "pool-id": pool_id}
            },
            "spec": {
                "replicas": 1,
                "revisionHistoryLimit": 0,
                "selector": {"matchLabels": {"pool-id": pool_id}},
                "template": {
                    "metadata": {
                        "labels": {"app": "viz-pool", "pool-id": pool_id, "status": "pending"},
                        "annotations": {"nveil/image": self.viz_image},
                    },
                    "spec": spec
                }
            }
        }

    def _build_service(self, pool_id: str) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"viz-pool-{pool_id}",
                "namespace": self.namespace,
            },
            "spec": {
                "selector": {"pool-id": pool_id},
                "ports": [
                    {"name": "cmd", "port": 1024, "targetPort": 1024},
                    {"name": "viz", "port": 1025, "targetPort": 1025},
                    {"name": "kedro", "port": 4141, "targetPort": 4141},
                ],
                "type": "ClusterIP"
            }
        }

    def _delete_pod_resources(self, pool_id: str):
        """Supprime le deployment et le service d'un pod du pool."""
        # Extraire le pool_id si on reçoit un nom de pod complet
        # Ex: "viz-pool-pool-4266ef0d-5c95c4c645-sg9hs" -> "pool-4266ef0d"
        if pool_id.startswith("viz-pool-"):
            # C'est un nom de pod complet, extraire le pool_id
            parts = pool_id.split("-")
            if len(parts) >= 4:
                pool_id = f"{parts[2]}-{parts[3]}"  # "pool-4266ef0d"
        
        logger().logp(INFO, f"🗑️ Deleting pool resources: pool_id={pool_id}")
        try:
            pods = self.v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"pool-id={pool_id}"
            )
            if pods.items:
                pod_name = pods.items[0].metadata.name
                body = {"metadata": {"labels": {"status": "deleting",
                                    "room-id": "",
                                    "owner-id": "",
                                }}}
                self.v1.patch_namespaced_pod(
                    name=pod_name,
                    namespace=self.namespace,
                    body=body
                )
                logger().logp(DEBUG, f"🏷️ Pod {pod_name} marked as deleting")
        except Exception as e:
            logger().logp(WARNING, f"⚠️ Failed to mark pod as deleting: {e}")

        try:
            self.apps_v1.delete_namespaced_deployment(
                name=f"viz-pool-{pool_id}",
                namespace=self.namespace,
                propagation_policy="Background"
            )
            logger().logp(SUCCESS, f"✅ Deployment viz-pool-{pool_id} deleted")
        except ApiException as e:
            if e.status == 404:
                logger().logp(DEBUG, f"Deployment viz-pool-{pool_id} already deleted")
            else:
                logger().logp(WARNING, f"⚠️ Failed to delete deployment: {e}")
        except Exception as e:
            logger().logp(WARNING, f"⚠️ Failed to delete deployment: {e}")

        try:
            self.v1.delete_namespaced_service(
                name=f"viz-pool-{pool_id}",
                namespace=self.namespace
            )
            logger().logp(SUCCESS, f"✅ Service viz-pool-{pool_id} deleted")
        except ApiException as e:
            if e.status == 404:
                logger().logp(DEBUG, f"Service viz-pool-{pool_id} already deleted")
            else:
                logger().logp(WARNING, f"⚠️ Failed to delete service: {e}")
        except Exception as e:
            logger().logp(WARNING, f"⚠️ Failed to delete service: {e}")

    async def acquire(self, room_id: str, room_token: str, owner_id: str, timeout: int = 120, assign_extra: dict = None) -> Optional[str]:
        """Acquire a pod from the pool and assign it to a room.

        Pod-per-user: if the user already owns a pod, re-assign it (context switch).

        Returns:
            "already_serving" — pod already serving this exact room (no action).
            "switched"        — existing user pod context-switched to new room.
            "assigned"        — fresh pod assigned from pool.
            None              — acquisition failed.
        """
        # Already assigned to this exact room?
        user_pod_info = self.get_user_pod_info(owner_id)
        if user_pod_info and user_pod_info.get("room_id") == room_id:
            logger().logp(INFO, f"Pod already assigned to room {room_id[:8]}")
            return "already_serving"

        # Check if user already has a pod (pod-per-user reuse)
        if user_pod_info:
            pod_dns = user_pod_info["dns"]
            pod_name = user_pod_info["pod_name"]
            logger().logp(INFO, f"Reusing user pod {pod_name} for room {room_id[:8]}")
            try:
                payload = {"room_id": room_id, "room_token": room_token, "owner_id": owner_id}
                if assign_extra:
                    payload.update(assign_extra)
                resp = await self._http.post(f"https://{pod_dns}:1024/viz/assign", json=payload, timeout=120.0)
                if resp.status_code == 200:
                    resp_data = resp.json()
                    if resp_data.get("status") == "error":
                        logger().logp(WARNING, f"Pod {pod_name} assign returned error: {resp_data.get('message')}")
                    else:
                        body = {"metadata": {"labels": {"room-id": room_id}, "annotations": {"nveil/acquired-at": datetime.utcnow().isoformat()}}}
                        self.v1.patch_namespaced_pod(name=pod_name, namespace=self.namespace, body=body)
                        self._room_token_to_dns[room_token] = pod_dns
                        self._room_id_to_token[room_id] = room_token
                        self._room_token_to_info[room_token] = {"dns": pod_dns, "room_id": room_id, "owner_id": owner_id}
                        logger().logp(SUCCESS, f"User pod {pod_name} switched to room {room_id[:8]}")
                        return "switched"
            except Exception as e:
                logger().logp(WARNING, f"Failed to reuse user pod {pod_name}: {e}")

        start_time = asyncio.get_event_loop().time()
        attempted_pods = set()
        notified_queue = False

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                logger().logp(ERROR, f"Timeout waiting for available pod: room_id={room_id[:8]}, waited={elapsed:.1f}s")
                return None

            pod_dns = ""
            pod_name = ""
            pool_id = ""

            try:
                api_response = self.v1.list_namespaced_pod(
                    self.namespace, label_selector='status=available'
                )

                if api_response.items:
                    found_new_pod = False
                    for item in api_response.items:
                        if item.metadata.name not in attempted_pods:
                            pool_id = item.metadata.labels.get("pool-id", "")
                            pod_dns = f"viz-pool-{pool_id}.{self.namespace}.svc.cluster.local"
                            pod_name = item.metadata.name
                            found_new_pod = True
                            break

                    if not found_new_pod:
                        logger().logp(WARNING, f"All available pods failed, waiting: room_id={room_id[:8]}")
                        attempted_pods.clear()
                        await asyncio.sleep(5)
                        continue
                else:
                    pending_count = self.get_pending_pods_size()
                    if pending_count > 0:
                        logger().logp(INFO, f"No available pod, {pending_count} pending: room_id={room_id[:8]}")
                    else:
                        logger().logp(WARNING, f"No pods, triggering fill: room_id={room_id[:8]}")
                        asyncio.create_task(self._fill_pool())
                    # Notify user once via WebSocket that they are queued
                    if not notified_queue and self._on_queue_wait_callback:
                        asyncio.create_task(self._on_queue_wait_callback(room_id, owner_id))
                        notified_queue = True
                    await asyncio.sleep(2)
                    continue

            except ApiException as e:
                logger().logp(ERROR, f"Exception listing pods: {e}")
                await asyncio.sleep(2)
                continue

            if not pool_id or not pod_name:
                await asyncio.sleep(2)
                continue

            attempted_pods.add(pod_name)

            try:
                self.v1.read_namespaced_service(name=f"viz-pool-{pool_id}", namespace=self.namespace)
            except Exception as e:
                logger().logp(WARNING, f"Service not found for pod {pod_name}, skipping: {e}")
                await asyncio.sleep(1)
                continue

            try:
                payload = {"room_id": room_id, "room_token": room_token, "owner_id": owner_id}
                if assign_extra:
                    payload.update(assign_extra)
                resp = await self._http.post(f"https://{pod_dns}:1024/viz/assign", json=payload, timeout=120.0)
                if resp.status_code == 200:
                    resp_data = resp.json()
                    if resp_data.get("status") == "error":
                        logger().logp(WARNING, f"Pod {pod_name} assign error: {resp_data.get('message')}")
                        await asyncio.sleep(1)
                        continue
                    body = {
                        "metadata": {
                            "labels": {
                                "status": "user-assigned",
                                "room-id": room_id,
                                "owner-id": owner_id,
                            },
                            "annotations": {
                                "nveil/acquired-at": datetime.utcnow().isoformat(),
                            }
                        }
                    }
                    self.v1.patch_namespaced_pod(name=pod_name, namespace=self.namespace, body=body)
                    self._room_token_to_dns[room_token] = pod_dns
                    self._room_id_to_token[room_id] = room_token
                    self._room_token_to_info[room_token] = {"dns": pod_dns, "room_id": room_id, "owner_id": owner_id}
                    logger().logp(SUCCESS, f"Pod {pod_name} assigned to room {room_id[:8]}")
                    asyncio.create_task(self._fill_pool())
                    return "assigned"
                else:
                    logger().logp(WARNING, f"Pod {pod_name} returned {resp.status_code}, trying another")
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                logger().logp(WARNING, f"Failed to assign pod {pod_name}: {e}")
                await asyncio.sleep(1)
                continue

        return None

    async def release(self, room_id: str):
        """Release a room from its pod. Pod stays alive (user-assigned, idle)."""
        token = self._room_id_to_token.pop(room_id, None)
        if token:
            self._room_token_to_dns.pop(token, None)
            self._room_token_to_info.pop(token, None)
        logger().logp(INFO, f"Releasing room {room_id[:8]} from pod (pod stays alive)")

        try:
            api_response = self.v1.list_namespaced_pod(
                self.namespace, label_selector=f'room-id={room_id}'
            )
            if api_response.items:
                pod = api_response.items[0]
                pod_name = pod.metadata.name
                pool_id = pod.metadata.labels.get("pool-id", "")
                pod_dns = f"viz-pool-{pool_id}.{self.namespace}.svc.cluster.local"

                # Notify viz pod to clear room context
                try:
                    await self._http.post(f"https://{pod_dns}:1024/viz/release_room", timeout=10.0)
                except Exception as e:
                    logger().logp(WARNING, f"Failed to notify pod of room release: {e}")

                # Clear room-id label but keep owner-id and user-assigned status
                body = {"metadata": {"labels": {"room-id": ""}}}
                self.v1.patch_namespaced_pod(name=pod_name, namespace=self.namespace, body=body)
                logger().logp(INFO, f"Pod {pod_name} released from room {room_id[:8]}, still user-assigned")
            else:
                logger().logp(WARNING, f"No pod found for room {room_id[:8]}")
        except ApiException as e:
            logger().logp(ERROR, f"Exception releasing pod for room: {e}")

    async def release_user(self, owner_id: str):
        """Kill the pod assigned to a user. Used for logout, guest cleanup, restart."""
        logger().logp(INFO, f"Releasing user pod for owner {owner_id[:8]}")
        try:
            api_response = self.v1.list_namespaced_pod(
                self.namespace, label_selector=f'owner-id={owner_id}'
            )
            if api_response.items:
                pod = api_response.items[0]
                room_id = pod.metadata.labels.get("room-id", "")
                if room_id:
                    token = self._room_id_to_token.pop(room_id, None)
                    if token:
                        self._room_token_to_dns.pop(token, None)
                        self._room_token_to_info.pop(token, None)
                pool_id = pod.metadata.labels.get("pool-id", "")
                if pool_id:
                    self._delete_pod_resources(pool_id)
                    logger().logp(SUCCESS, f"User pod deleted for owner {owner_id[:8]}")
            else:
                logger().logp(WARNING, f"No pod found for owner {owner_id[:8]}")
        except ApiException as e:
            logger().logp(ERROR, f"Exception releasing user pod: {e}")

    def get_user_pod_info(self, owner_id: str) -> Optional[dict]:
        """Return pod info for the user's assigned pod."""
        try:
            api_response = self.v1.list_namespaced_pod(
                self.namespace, label_selector=f'owner-id={owner_id},status=user-assigned'
            )
            if api_response.items:
                pod = api_response.items[0]
                pool_id = pod.metadata.labels.get("pool-id", "")
                return {
                    "pod_name": pod.metadata.name,
                    "pool_id": pool_id,
                    "dns": f"viz-pool-{pool_id}.{self.namespace}.svc.cluster.local",
                    "room_id": pod.metadata.labels.get("room-id", ""),
                }
        except ApiException:
            pass
        return None

# Singleton instance
_pool_instance: Optional[VizPoolManager] = None


def get_pool() -> VizPoolManager:
    """Retourne l'instance singleton du VizPoolManager."""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = VizPoolManager()
    return _pool_instance
